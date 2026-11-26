from __future__ import annotations

from math import hypot

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy_extras import view3d_utils

from .preferences import get_prefs

_PREV_FACE_CENTER: dict[int, bool] = {}


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


class MAYA_UX_OT_pick_walk(bpy.types.Operator):
    """Navigate hierarchy Parent/Child/Siblings like Maya Pick Walk (Arrow keys)."""

    bl_idname = "maya_ux.pick_walk"
    bl_label = "Maya Pick Walk"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        name="Direction",
        items=[
            ("UP", "Parent (Up)", "Select parent object"),
            ("DOWN", "Child (Down)", "Select first child object"),
            ("LEFT", "Prev Sibling (Left)", "Select previous sibling"),
            ("RIGHT", "Next Sibling (Right)", "Select next sibling"),
        ],
        default="UP",
    )

    def execute(self, context):
        active = context.active_object
        if active is None:
            return {"CANCELLED"}

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
            if resolved == "GROW":
                bpy.ops.mesh.select_more(use_face_step=True)
            else:
                bpy.ops.mesh.select_less(use_face_step=True)
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
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
