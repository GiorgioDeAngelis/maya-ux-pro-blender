from __future__ import annotations

from math import hypot

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from .preferences import get_prefs

_PREV_FACE_CENTER: dict[int, bool] = {}
_GROW_HISTORY: dict[tuple, list[tuple[tuple, tuple]]] = {}
_PICKWALK_STATE: dict[str, dict] = {}
_EDGE_LOOP_ORIGIN: dict[str, dict] = {}
_MAX_GROW_HISTORY = 64


def sync_face_center_overlay(enabled: bool, context=None):
    """Show Maya-style face center dots (size 5) across 3D Viewports, or restore prior state."""
    ctx = context or bpy.context
    prefs_root = getattr(ctx, "preferences", None)
    if prefs_root is not None and prefs_root.themes:
        prefs_root.themes[0].view_3d.facedot_size = 5 if enabled else 3

    wm = getattr(ctx, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            sp = area.spaces.active
            if sp is None:
                continue
            ptr = sp.as_pointer()
            if enabled:
                if ptr not in _PREV_FACE_CENTER:
                    _PREV_FACE_CENTER[ptr] = bool(sp.overlay.show_face_center)
                sp.overlay.show_face_center = True
            else:
                sp.overlay.show_face_center = _PREV_FACE_CENTER.pop(ptr, False)
            area.tag_redraw()


def pick_face_by_center_2d(candidates, mouse_xy: tuple[float, float], hit_radius_px: float = 10.0):
    """Select the closest-depth candidate whose projected center dot is within hit_radius_px."""
    mx, my = mouse_xy
    best_item = None
    best_score = None
    for item, px, py, depth in candidates:
        dist_px = hypot(px - mx, py - my)
        if dist_px <= hit_radius_px:
            score = (float(depth), float(dist_px))
            if best_score is None or score < best_score:
                best_score = score
                best_item = item
    return best_item


def pick_face_by_center(context, mouse_xy: tuple[float, float], hit_radius_px: float = 10.0):
    """Return (obj, bmesh_face) only if the click lands on a visible face's center handle."""
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    space = getattr(context, "space_data", None)
    if region is None or rv3d is None or space is None:
        return None

    xray = bool(getattr(space.shading, "show_xray", False)) or getattr(space.shading, "type", "SOLID") == "WIREFRAME"
    scene = context.scene
    depsgraph = context.evaluated_depsgraph_get()
    mx, my = mouse_xy

    objs = [o for o in (getattr(context, "objects_in_mode", None) or ()) if o is not None and o.type == "MESH"]
    if not objs:
        active_obj = getattr(context, "active_object", None)
        if active_obj is not None and active_obj.type == "MESH":
            objs = [active_obj]

    candidates = []
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        mat_world = obj.matrix_world
        rot_world = mat_world.to_3x3()
        for face in bm.faces:
            if face.hide:
                continue
            world_center = mat_world @ face.calc_center_median()
            pt2d = view3d_utils.location_3d_to_region_2d(region, rv3d, world_center)
            if pt2d is None:
                continue
            if hypot(pt2d.x - mx, pt2d.y - my) > hit_radius_px:
                continue

            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, (pt2d.x, pt2d.y))
            ray_vec = world_center - ray_origin
            ray_dist = ray_vec.length
            ray_dir = (
                ray_vec.normalized()
                if ray_dist > 1e-6
                else view3d_utils.region_2d_to_vector_3d(region, rv3d, (pt2d.x, pt2d.y))
            )

            if not xray:
                world_norm = (rot_world @ face.normal).normalized()
                if world_norm.dot(ray_dir) > 0.05:
                    continue
                if ray_dist > 1e-3:
                    hit, hit_loc, _norm, _idx, _hit_obj, _mat = scene.ray_cast(
                        depsgraph, ray_origin, ray_dir, distance=max(0.0, ray_dist - 1e-3)
                    )
                    if hit and (hit_loc - world_center).length > 1e-2:
                        continue

            candidates.append(((obj, face.index), float(pt2d.x), float(pt2d.y), float(ray_dist)))

    return pick_face_by_center_2d(candidates, mouse_xy, hit_radius_px=hit_radius_px)


def apply_face_center_selection(
    objs,
    hit: tuple[bpy.types.Object, int] | None,
    *,
    toggle: bool = False,
    deselect: bool = False,
):
    """Apply plain/toggle/deselect face selection using (obj, face_index) with live BMesh wrappers."""
    bm_map = {obj: bmesh.from_edit_mesh(obj.data) for obj in objs}
    for bm in bm_map.values():
        bm.faces.ensure_lookup_table()

    if hit is None:
        if not toggle and not deselect:
            for obj, bm in bm_map.items():
                for f in bm.faces:
                    f.select_set(False)
                bm.faces.active = None
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return

    hit_obj, hit_idx = hit
    hit_bm = bm_map.get(hit_obj)
    if hit_bm is None or not (0 <= hit_idx < len(hit_bm.faces)):
        return
    hit_face = hit_bm.faces[hit_idx]

    if not toggle and not deselect:
        for bm in bm_map.values():
            for f in bm.faces:
                f.select_set(False)
            bm.faces.active = None
        hit_face.select_set(True)
        hit_bm.faces.active = hit_face
    elif toggle:
        new_state = not hit_face.select
        hit_face.select_set(new_state)
        if new_state:
            hit_bm.faces.active = hit_face
    else:
        hit_face.select_set(False)

    for obj, bm in bm_map.items():
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


class MAYA_UX_OT_select_face_center(bpy.types.Operator):
    """Maya Face Selection: faces can only be selected by clicking their center dot handle."""

    bl_idname = "maya_ux.select_face_center"
    bl_label = "Maya Select Face Center"
    bl_options = {"REGISTER", "UNDO"}

    toggle: BoolProperty(name="Toggle", default=False)
    deselect: BoolProperty(name="Deselect", default=False)

    def invoke(self, context, event):
        prefs = get_prefs(context)
        if not bool(getattr(prefs, "maya_face_center_select", True)):
            return {"PASS_THROUGH"}
        if getattr(context, "mode", "") != "EDIT_MESH":
            return {"PASS_THROUGH"}
        if tuple(context.tool_settings.mesh_select_mode) != (False, False, True):
            return {"PASS_THROUGH"}

        region = getattr(context, "region", None)
        rv3d = getattr(context, "region_data", None)
        space = getattr(context, "space_data", None)
        if region is None or rv3d is None or space is None:
            return {"PASS_THROUGH"}

        ui_scale = float(getattr(context.preferences.system, "ui_scale", 1.0))
        radius = float(getattr(prefs, "face_center_hit_radius", 10.0)) * ui_scale
        mouse_xy = (float(event.mouse_region_x), float(event.mouse_region_y))

        hit = pick_face_by_center(context, mouse_xy, hit_radius_px=radius)

        objs = [o for o in (getattr(context, "objects_in_mode", None) or ()) if o is not None and o.type == "MESH"]
        if not objs and context.active_object is not None and context.active_object.type == "MESH":
            objs = [context.active_object]

        apply_face_center_selection(objs, hit, toggle=self.toggle, deselect=self.deselect)
        return {"FINISHED"}


class MAYA_UX_OT_convert_selection(bpy.types.Operator):
    """Convert current mesh selection to Vertex, Edge, or Face (Maya Ctrl+F9/F10/F11)."""

    bl_idname = "maya_ux.convert_selection"
    bl_label = "Convert Selection"
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(
        name="Target",
        items=[
            ("VERT", "Vertices", "Convert selection to vertices"),
            ("EDGE", "Edges", "Convert selection to edges"),
            ("FACE", "Faces", "Convert selection to faces"),
        ],
        default="VERT",
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, "Select a Mesh object")
            return {"CANCELLED"}

        if context.mode != "EDIT_MESH":
            bpy.ops.object.mode_set(mode="EDIT")

        bpy.ops.mesh.select_mode(use_extend=False, use_expand=True, type=self.target)
        return {"FINISHED"}


def _select_edge_loop_multi():
    """Select full edge loops compatible with both Blender 5.3+ and 4.2-5.2."""
    if hasattr(bpy.ops.mesh, "select_edge_loop_multi"):
        return bpy.ops.mesh.select_edge_loop_multi()
    return bpy.ops.mesh.loop_multi_select(ring=False)


def compute_parallel_edge_loops(bm, frontier_indices: set[int]) -> list[frozenset[int]]:
    """Return opposite parallel edge-loop index sets on each connected quad side of frontier_indices."""
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    frontier_edges = {bm.edges[i] for i in frontier_indices if 0 <= i < len(bm.edges)}
    if not frontier_edges:
        return []

    quads = {f for e in frontier_edges for f in e.link_faces if not f.hide and len(f.verts) == 4}
    visited = set()
    sides: list[frozenset[int]] = []

    for start_f in quads:
        if start_f in visited:
            continue
        stack = [start_f]
        comp = []
        visited.add(start_f)
        while stack:
            f = stack.pop()
            comp.append(f)
            for e in f.edges:
                if e in frontier_edges:
                    continue
                for nf in e.link_faces:
                    if nf in quads and nf not in visited:
                        visited.add(nf)
                        stack.append(nf)
        opp_indices = set()
        for f in comp:
            for lp in f.loops:
                if lp.edge in frontier_edges:
                    opp_e = lp.link_loop_next.link_loop_next.edge
                    if not opp_e.hide:
                        opp_indices.add(opp_e.index)
        if opp_indices:
            sides.append(frozenset(opp_indices))

    return sides


def _edge_group_world_center(bm, edge_indices: set[int] | frozenset[int], mat_world) -> Vector:
    bm.edges.ensure_lookup_table()
    total = Vector((0.0, 0.0, 0.0))
    count = 0
    for idx in edge_indices:
        if 0 <= idx < len(bm.edges):
            e = bm.edges[idx]
            total += mat_world @ ((e.verts[0].co + e.verts[1].co) * 0.5)
            count += 1
    return (total / count) if count else Vector((0.0, 0.0, 0.0))


def _rank_sides_for_direction(context, bm, mat_world, frontier: set[int], sides: list[frozenset[int]], direction: str) -> frozenset[int] | None:
    if not sides:
        return None
    if len(sides) == 1:
        return sides[0]

    base_center = _edge_group_world_center(bm, frontier, mat_world)
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    base_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, base_center) if (region and rv3d) else None

    def _score(side: frozenset[int]):
        c3 = _edge_group_world_center(bm, side, mat_world)
        if base_2d is not None:
            c2 = view3d_utils.location_3d_to_region_2d(region, rv3d, c3)
            if c2 is not None:
                return (round(float(c2.y - base_2d.y), 4), round(float(c3.z - base_center.z), 5), round(float(c3.y - base_center.y), 5), round(float(c3.x - base_center.x), 5))
        return (round(float(c3.z - base_center.z), 5), round(float(c3.y - base_center.y), 5), round(float(c3.x - base_center.x), 5))

    return max(sides, key=_score) if direction == "UP" else min(sides, key=_score)


def _pick_walk_edge_loop(context, obj: bpy.types.Object, direction: str, extend: bool) -> bool:
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    cur_sel = frozenset(e.index for e in bm.edges if e.select and not e.hide)
    if not cur_sel:
        return False

    state = _PICKWALK_STATE.get(obj.name)
    state_valid = (
        state is not None
        and state.get("edge_count") == len(bm.edges)
        and state.get("all_selected") == cur_sel
        and state.get("extend") == extend
    )

    opp_dir = "UP" if direction == "DOWN" else "DOWN"
    target: frozenset[int] | None = None

    if state_valid and extend:
        ends = state.get("ends", {})
        frontier, prev = ends.get(direction, (set(cur_sel), set()))
        sides = compute_parallel_edge_loops(bm, set(frontier))
        candidates = [s for s in sides if not (s & prev)]
        if not candidates:
            return False
        target = candidates[0] if len(candidates) == 1 else _rank_sides_for_direction(context, bm, obj.matrix_world, set(frontier), candidates, direction)
        if target is None:
            return False
        new_sel = frozenset(cur_sel | target)
        ends[direction] = (target, set(frontier))
        _PICKWALK_STATE[obj.name] = {
            "edge_count": len(bm.edges),
            "all_selected": new_sel,
            "extend": True,
            "ends": ends,
        }
    elif state_valid and not extend:
        frontier = set(state["frontier"])
        prev = set(state["prev_loop"])
        sides = compute_parallel_edge_loops(bm, frontier)
        if not sides:
            return False
        if direction == state["last_dir"]:
            candidates = [s for s in sides if not (s & prev)]
            if not candidates:
                return False
            target = candidates[0] if len(candidates) == 1 else _rank_sides_for_direction(context, bm, obj.matrix_world, frontier, candidates, direction)
        else:
            back_sides = [s for s in sides if s & prev]
            target = back_sides[0] if back_sides else _rank_sides_for_direction(context, bm, obj.matrix_world, frontier, sides, direction)
        if target is None:
            return False
        new_sel = target
        _PICKWALK_STATE[obj.name] = {
            "edge_count": len(bm.edges),
            "all_selected": new_sel,
            "extend": False,
            "frontier": target,
            "prev_loop": frozenset(frontier),
            "last_dir": direction,
        }
    else:
        sides = compute_parallel_edge_loops(bm, set(cur_sel))
        if not sides:
            return False
        target = _rank_sides_for_direction(context, bm, obj.matrix_world, set(cur_sel), sides, direction)
        if target is None:
            return False
        if extend:
            new_sel = frozenset(cur_sel | target)
            _PICKWALK_STATE[obj.name] = {
                "edge_count": len(bm.edges),
                "all_selected": new_sel,
                "extend": True,
                "ends": {
                    direction: (target, set(cur_sel)),
                    opp_dir: (cur_sel, set(target)),
                },
            }
        else:
            new_sel = target
            _PICKWALK_STATE[obj.name] = {
                "edge_count": len(bm.edges),
                "all_selected": new_sel,
                "extend": False,
                "frontier": target,
                "prev_loop": cur_sel,
                "last_dir": direction,
            }

    _EDGE_LOOP_ORIGIN.pop(obj.name, None)
    return _restore_edit_mesh_selection([obj], "edges", ((obj.name, len(bm.edges), new_sel),))


class MAYA_UX_OT_pick_walk(bpy.types.Operator):
    """Maya Pick Walk: hierarchy navigation in Object Mode and Edge Loop stepping in Edit Mesh."""

    bl_idname = "maya_ux.pick_walk"
    bl_label = "Maya Pick Walk"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        name="Direction",
        items=[
            ("UP", "Up / Prev Loop", "Select parent object or step parallel edge loop up"),
            ("DOWN", "Down / Next Loop", "Select first child object or step parallel edge loop down"),
            ("LEFT", "Prev / Return or Deselect Loop", "Select previous sibling, return to seed edge, or deselect edge loop"),
            ("RIGHT", "Next / Select Edge Loop", "Select next sibling or full edge loop"),
        ],
        default="UP",
    )
    extend: BoolProperty(
        name="Extend Selection",
        description="Keep previously selected edge loops when walking with Shift+Up/Down",
        default=False,
    )

    def execute(self, context):
        active = context.active_object
        if active is None:
            return {"CANCELLED"}

        if context.mode == "EDIT_MESH":
            if active.type != "MESH" or not bool(context.tool_settings.mesh_select_mode[1]):
                return {"PASS_THROUGH"}
            bm = bmesh.from_edit_mesh(active.data)
            bm.edges.ensure_lookup_table()
            cur_sel = frozenset(e.index for e in bm.edges if e.select and not e.hide)
            if not cur_sel:
                return {"CANCELLED"}
            edge_count = len(bm.edges)
            if self.direction == "RIGHT":
                _select_edge_loop_multi()
                after_bm = bmesh.from_edit_mesh(active.data)
                after_bm.edges.ensure_lookup_table()
                after_sel = frozenset(e.index for e in after_bm.edges if e.select and not e.hide)
                _PICKWALK_STATE.pop(active.name, None)
                if len(cur_sel) == 1 and len(after_sel) > 1:
                    _EDGE_LOOP_ORIGIN[active.name] = {
                        "edge_count": edge_count,
                        "seed": cur_sel,
                        "loop": after_sel,
                    }
                elif after_sel != cur_sel:
                    _EDGE_LOOP_ORIGIN.pop(active.name, None)
                return {"FINISHED"}
            if self.direction == "LEFT":
                _PICKWALK_STATE.pop(active.name, None)
                origin = _EDGE_LOOP_ORIGIN.pop(active.name, None)
                if origin is not None and origin["edge_count"] == edge_count and origin["loop"] == cur_sel:
                    _restore_edit_mesh_selection([active], "edges", ((active.name, edge_count, origin["seed"]),))
                else:
                    _restore_edit_mesh_selection([active], "edges", ((active.name, edge_count, frozenset()),))
                return {"FINISHED"}
            _pick_walk_edge_loop(context, active, self.direction, self.extend)
            return {"FINISHED"}

        if context.mode != "OBJECT":
            return {"PASS_THROUGH"}

        target = None
        if self.direction == "UP":
            target = active.parent
        elif self.direction == "DOWN":
            children = sorted((o for o in bpy.data.objects if o.parent == active), key=lambda o: o.name)
            target = children[0] if children else None
        else:
            if active.parent is not None:
                siblings = sorted(
                    (o for o in bpy.data.objects if o.parent == active.parent and o.name in context.view_layer.objects),
                    key=lambda o: o.name,
                )
            else:
                col = active.users_collection[0] if active.users_collection else context.scene.collection
                siblings = sorted(
                    (o for o in col.objects if o.parent is None and o.name in context.view_layer.objects),
                    key=lambda o: o.name,
                )
            if active in siblings and len(siblings) > 1:
                idx = siblings.index(active)
                step = -1 if self.direction == "LEFT" else 1
                target = siblings[(idx + step) % len(siblings)]

        if target is None or target.name not in context.view_layer.objects:
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        context.view_layer.objects.active = target
        return {"FINISHED"}


class MAYA_UX_OT_toggle_soft_select(bpy.types.Operator):
    """Toggle Maya Soft Selection (Proportional Editing) with B."""

    bl_idname = "maya_ux.toggle_soft_select"
    bl_label = "Toggle Soft Selection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ts = context.scene.tool_settings
        if context.mode == "EDIT_MESH":
            ts.use_proportional_edit = not ts.use_proportional_edit
            state = ts.use_proportional_edit
        else:
            ts.use_proportional_edit_objects = not ts.use_proportional_edit_objects
            state = ts.use_proportional_edit_objects
        self.report({"INFO"}, f"Soft Selection: {'ON' if state else 'OFF'}")
        return {"FINISHED"}


class MAYA_UX_OT_soft_select_radius(bpy.types.Operator):
    """Adjust Soft Selection (Proportional Editing) brush radius."""

    bl_idname = "maya_ux.soft_select_radius"
    bl_label = "Adjust Soft Selection Radius"
    bl_options = {"REGISTER"}

    factor: FloatProperty(name="Scale Factor", default=1.25, min=0.1, max=10.0)

    def execute(self, context):
        ts = context.scene.tool_settings
        ts.proportional_size = max(0.01, min(1000.0, ts.proportional_size * self.factor))
        self.report({"INFO"}, f"Soft Select Radius: {ts.proportional_size:.2f}")
        return {"FINISHED"}


class MAYA_UX_OT_smart_delete(bpy.types.Operator):
    """Maya-style Delete: dissolves edges cleanly without leaving orphaned verts or deletes verts/faces."""

    bl_idname = "maya_ux.smart_delete"
    bl_label = "Maya Smart Delete"
    bl_options = {"REGISTER", "UNDO"}

    delete_verts: BoolProperty(
        name="Delete Orphan Vertices",
        description="Also remove vertices when dissolving edges (Maya Ctrl+Backspace)",
        default=False,
    )

    def execute(self, context):
        if context.mode == "OBJECT":
            if not context.selected_objects:
                return {"CANCELLED"}
            bpy.ops.object.delete(use_global=False)
            return {"FINISHED"}

        if context.mode == "EDIT_MESH":
            v_mode, e_mode, f_mode = tuple(context.tool_settings.mesh_select_mode)
            if e_mode and not f_mode:
                bpy.ops.mesh.dissolve_edges(use_verts=self.delete_verts)
            elif f_mode and not v_mode and not e_mode:
                bpy.ops.mesh.delete(type="FACE")
            elif f_mode:
                bpy.ops.mesh.delete(type="FACE")
            else:
                bpy.ops.mesh.delete(type="VERT")
            return {"FINISHED"}

        return {"PASS_THROUGH"}


def resolve_grow_shrink_action(action: str, event=None) -> str | None:
    """Resolve Grow (>) vs Shrink (<) from explicit enum or ISO/Mac/US keyboard event."""
    if action in {"GROW", "SHRINK"}:
        return action
    if event is None:
        return None
    char = getattr(event, "unicode", "") or getattr(event, "ascii", "")
    if char == ">":
        return "GROW"
    if char == "<":
        return "SHRINK"
    if getattr(event, "type", "") == "GRLESS":
        return "GROW" if bool(getattr(event, "shift", False)) else "SHRINK"
    return None


def _active_mesh_elem_kind(context) -> str:
    v_mode, e_mode, f_mode = tuple(context.tool_settings.mesh_select_mode)
    if f_mode and not v_mode and not e_mode:
        return "faces"
    if e_mode and not v_mode and not f_mode:
        return "edges"
    return "verts"


def _get_edit_mesh_objects(context) -> list[bpy.types.Object]:
    objs = [o for o in (getattr(context, "objects_in_mode", None) or ()) if o is not None and o.type == "MESH"]
    if not objs:
        active = getattr(context, "active_object", None)
        if active is not None and active.type == "MESH":
            objs = [active]
    return objs


def _capture_edit_mesh_selection(objs: list[bpy.types.Object], elem_kind: str) -> tuple:
    snap = []
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        seq = getattr(bm, elem_kind)
        seq.ensure_lookup_table()
        snap.append((obj.name, len(seq), frozenset(el.index for el in seq if el.select)))
    return tuple(snap)


def _restore_edit_mesh_selection(objs: list[bpy.types.Object], elem_kind: str, snapshot: tuple) -> bool:
    if len(objs) != len(snapshot):
        return False
    bm_seq_pairs = []
    for obj, (snap_name, snap_len, indices) in zip(objs, snapshot):
        if obj.name != snap_name:
            return False
        bm = bmesh.from_edit_mesh(obj.data)
        seq = getattr(bm, elem_kind)
        seq.ensure_lookup_table()
        if len(seq) != snap_len:
            return False
        bm_seq_pairs.append((obj, bm, seq, indices))

    for obj, bm, seq, indices in bm_seq_pairs:
        for group in (bm.verts, bm.edges, bm.faces):
            for el in group:
                el.select = False
        for idx in indices:
            if 0 <= idx < len(seq):
                seq[idx].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    return True


def _shrink_open_boundary(objs: list[bpy.types.Object], elem_kind: str) -> bool:
    """Peel outer open-boundary components when all elements on an open island are selected."""
    next_snapshot = []
    changed = False
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        seq = getattr(bm, elem_kind)
        seq.ensure_lookup_table()
        selected_indices = []
        kept_indices = []
        for el in seq:
            if not el.select:
                continue
            selected_indices.append(el.index)
            if elem_kind == "faces":
                on_boundary = any(e.is_boundary for e in el.edges)
            else:
                on_boundary = bool(el.is_boundary)
            if not on_boundary:
                kept_indices.append(el.index)
        if len(kept_indices) < len(selected_indices):
            changed = True
        next_snapshot.append((obj.name, len(seq), frozenset(kept_indices)))
    if not changed:
        return False
    return _restore_edit_mesh_selection(objs, elem_kind, tuple(next_snapshot))


class MAYA_UX_OT_grow_shrink_selection(bpy.types.Operator):
    """Maya Grow (>) / Shrink (<) selection across Mesh components, Curve, and UV Editor."""

    bl_idname = "maya_ux.grow_shrink_selection"
    bl_label = "Maya Grow / Shrink Selection"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        name="Action",
        items=[
            ("AUTO", "Auto", "Detect < or > from keyboard event"),
            ("GROW", "Grow (>)", "Grow component selection"),
            ("SHRINK", "Shrink (<)", "Shrink component selection"),
        ],
        default="AUTO",
    )

    def _run_action(self, context, resolved: str):
        area = getattr(context, "area", None)
        area_type = getattr(area, "type", "") if area is not None else ""
        if area_type == "IMAGE_EDITOR":
            if resolved == "GROW":
                bpy.ops.uv.select_more()
            else:
                bpy.ops.uv.select_less()
            return {"FINISHED"}

        mode = getattr(context, "mode", "")
        if mode == "EDIT_MESH":
            v_mode, e_mode, f_mode = tuple(context.tool_settings.mesh_select_mode)
            # Only Face-only mode steps across face rings; Vert/Edge/Multi step strictly 1 hop in active component.
            face_step = bool(f_mode and not v_mode and not e_mode)
            elem_kind = _active_mesh_elem_kind(context)
            objs = _get_edit_mesh_objects(context)
            hist_key = (tuple(o.name for o in objs), elem_kind)
            before = _capture_edit_mesh_selection(objs, elem_kind)

            if resolved == "GROW":
                bpy.ops.mesh.select_more(use_face_step=face_step)
                after = _capture_edit_mesh_selection(objs, elem_kind)
                if after != before:
                    stack = _GROW_HISTORY.setdefault(hist_key, [])
                    if stack and stack[-1][1] != before:
                        stack.clear()
                    stack.append((before, after))
                    if len(stack) > _MAX_GROW_HISTORY:
                        stack.pop(0)
            else:
                bpy.ops.mesh.select_less(use_face_step=face_step)
                after = _capture_edit_mesh_selection(objs, elem_kind)
                stack = _GROW_HISTORY.get(hist_key)
                if after != before:
                    if stack and stack[-1][1] == before:
                        stack.pop()
                else:
                    if stack and stack[-1][1] == before:
                        prev_snap, _ = stack.pop()
                        _restore_edit_mesh_selection(objs, elem_kind, prev_snap)
                    else:
                        _shrink_open_boundary(objs, elem_kind)
            return {"FINISHED"}

        if mode == "EDIT_CURVE":
            if resolved == "GROW":
                bpy.ops.curve.select_more()
            else:
                bpy.ops.curve.select_less()
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def invoke(self, context, event):
        resolved = resolve_grow_shrink_action(self.action, event)
        if resolved is None:
            return {"PASS_THROUGH"}
        return self._run_action(context, resolved)

    def execute(self, context):
        resolved = resolve_grow_shrink_action(self.action, None)
        if resolved is None:
            return {"CANCELLED"}
        return self._run_action(context, resolved)


CLASSES = (
    MAYA_UX_OT_select_face_center,
    MAYA_UX_OT_convert_selection,
    MAYA_UX_OT_pick_walk,
    MAYA_UX_OT_toggle_soft_select,
    MAYA_UX_OT_soft_select_radius,
    MAYA_UX_OT_smart_delete,
    MAYA_UX_OT_grow_shrink_selection,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    sync_face_center_overlay(bool(getattr(get_prefs(), "maya_face_center_select", True)))


def unregister():
    sync_face_center_overlay(False)
    _PREV_FACE_CENTER.clear()
    _GROW_HISTORY.clear()
    _PICKWALK_STATE.clear()
    _EDGE_LOOP_ORIGIN.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
