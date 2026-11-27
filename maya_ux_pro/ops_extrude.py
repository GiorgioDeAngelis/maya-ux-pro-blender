from __future__ import annotations

from collections import deque

import bmesh
import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from mathutils import Euler, Matrix, Vector

from .preferences import get_prefs

_EXTRUDE_SESSION_ACTIVE: bool = False
_PRE_EXTRUDE_TOOL: str = "builtin.select_box"
_PRE_EXTRUDE_ORIENT: str = "GLOBAL"
_EXTRUDE_MSGBUS_OWNER = object()


def is_extrude_session_active() -> bool:
    """Return True while the all-in-one Extrude Transform manipulator session is active."""
    return _EXTRUDE_SESSION_ACTIVE


def get_pre_extrude_tool() -> str:
    """Return the non-transform tool saved before entering Extrude mode."""
    return _PRE_EXTRUDE_TOOL if _PRE_EXTRUDE_TOOL != "builtin.transform" else "builtin.select_box"


def _set_view3d_tool_safe(context, tool_id: str):
    """Switch active 3D View tool and ensure permanent multi-gizmo overlay flags stay disabled."""
    ctx = context or bpy.context
    wm = getattr(ctx, "window_manager", None)
    if wm is not None:
        for win in wm.windows:
            for area in win.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                sp = area.spaces.active
                if sp is not None:
                    sp.show_gizmo = True
                    sp.show_gizmo_tool = True
                    sp.show_gizmo_object_translate = False
                    sp.show_gizmo_object_rotate = False
                    sp.show_gizmo_object_scale = False
                    area.tag_redraw()

    if bpy.app.background:
        return

    space_data = getattr(ctx, "space_data", None)
    if space_data is not None and space_data.type == "VIEW_3D":
        try:
            bpy.ops.wm.tool_set_by_id(name=tool_id)
            return
        except (RuntimeError, AttributeError):
            pass

    if wm is not None:
        for win in wm.windows:
            for area in win.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                reg = next((r for r in area.regions if r.type == "WINDOW"), None)
                if reg is None or not hasattr(ctx, "temp_override"):
                    continue
                try:
                    with ctx.temp_override(window=win, area=area, region=reg):
                        bpy.ops.wm.tool_set_by_id(name=tool_id)
                    return
                except (RuntimeError, AttributeError):
                    pass


def start_extrude_session(context, space: str):
    """Enter Extrude session and activate all-in-one Transform gizmo only for Extrude."""
    global _EXTRUDE_SESSION_ACTIVE, _PRE_EXTRUDE_TOOL, _PRE_EXTRUDE_ORIENT
    from . import ops_viewport

    ctx = context or bpy.context
    scene = getattr(ctx, "scene", None)
    if not _EXTRUDE_SESSION_ACTIVE:
        cur_tool = ops_viewport._get_active_tool_id(ctx)
        _PRE_EXTRUDE_TOOL = cur_tool if cur_tool != "builtin.transform" else "builtin.select_box"
        slots = getattr(scene, "transform_orientation_slots", None) if scene is not None else None
        _PRE_EXTRUDE_ORIENT = slots[0].type if (slots and len(slots) > 0) else "GLOBAL"

    _EXTRUDE_SESSION_ACTIVE = True
    if scene is not None:
        slots = getattr(scene, "transform_orientation_slots", None)
        if slots and len(slots) > 0:
            slots[0].type = "NORMAL" if space == "LOCAL" else "GLOBAL"

    if bool(getattr(get_prefs(ctx), "extrude_activate_gizmo", True)):
        _set_view3d_tool_safe(ctx, "builtin.transform")


def end_extrude_session(context=None, restore_tool: bool = True):
    """Exit Extrude session, restore orientation, and exit the all-in-one Transform gizmo."""
    global _EXTRUDE_SESSION_ACTIVE
    if not _EXTRUDE_SESSION_ACTIVE:
        return
    _EXTRUDE_SESSION_ACTIVE = False
    ctx = context or bpy.context
    scene = getattr(ctx, "scene", None)
    if scene is not None:
        slots = getattr(scene, "transform_orientation_slots", None)
        if slots and len(slots) > 0:
            try:
                slots[0].type = _PRE_EXTRUDE_ORIENT
            except (TypeError, ValueError):
                slots[0].type = "GLOBAL"
    if restore_tool:
        _set_view3d_tool_safe(ctx, get_pre_extrude_tool())


def _on_extrude_context_change():
    if _EXTRUDE_SESSION_ACTIVE:
        end_extrude_session(bpy.context, restore_tool=True)


def _vec_norm(v: Vector, fallback: Vector) -> Vector:
    return v.normalized() if v.length > 1e-8 else fallback.copy()


def _orthonormal_basis_from_z(z_dir: Vector, hint_x: Vector | None = None) -> Matrix:
    """Build right-handed orthonormal 3x3 Matrix with column Z = z_dir."""
    z = _vec_norm(z_dir, Vector((0.0, 0.0, 1.0)))
    if hint_x is not None and hint_x.length > 1e-8:
        cand = hint_x - z * hint_x.dot(z)
    else:
        cand = Vector((0.0, 0.0, 0.0))
    if cand.length <= 1e-6:
        ref = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        cand = ref - z * ref.dot(z)
    x = cand.normalized()
    y = z.cross(x).normalized()
    return Matrix((x, y, z)).transposed()


def detect_extrude_component(context, bm: bmesh.types.BMesh) -> str:
    """Return 'FACE', 'EDGE', 'VERT', or '' matching active Edit Mesh selection mode."""
    ts = getattr(context, "tool_settings", None)
    v_mode, e_mode, f_mode = tuple(bool(x) for x in ts.mesh_select_mode) if ts is not None else (False, False, True)
    has_f = any(f.select and not f.hide for f in bm.faces)
    has_e = any(e.select and not e.hide for e in bm.edges)
    has_v = any(v.select and not v.hide for v in bm.verts)

    if f_mode and has_f:
        return "FACE"
    if e_mode and has_e:
        return "EDGE"
    if v_mode and has_v:
        return "VERT"
    if has_f:
        return "FACE"
    if has_e:
        return "EDGE"
    if has_v:
        return "VERT"
    return ""


def _compute_group_frame(
    obj: bpy.types.Object,
    verts: list[bmesh.types.BMVert],
    normals: dict[bmesh.types.BMVert, Vector],
    hint_x: Vector | None,
    space: str,
) -> tuple[Vector, Matrix]:
    """Compute (pivot_local, basis_3x3_local) for LOCAL or WORLD space extrusion."""
    if not verts:
        return Vector((0.0, 0.0, 0.0)), Matrix.Identity(3)
    pivot = sum((v.co for v in verts), Vector((0.0, 0.0, 0.0))) / len(verts)

    if space == "WORLD":
        inv3 = obj.matrix_world.inverted_safe().to_3x3()
        basis = Matrix((
            _vec_norm(inv3 @ Vector((1.0, 0.0, 0.0)), Vector((1.0, 0.0, 0.0))),
            _vec_norm(inv3 @ Vector((0.0, 1.0, 0.0)), Vector((0.0, 1.0, 0.0))),
            _vec_norm(inv3 @ Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, 1.0))),
        )).transposed()
        return pivot, basis

    avg_n = sum((normals.get(v, v.normal) for v in verts), Vector((0.0, 0.0, 0.0)))
    return pivot, _orthonormal_basis_from_z(avg_n, hint_x=hint_x)


def _even_vertex_normals(cap_verts: list[bmesh.types.BMVert], cap_faces: set[bmesh.types.BMFace]) -> dict[bmesh.types.BMVert, Vector]:
    """Per-vertex normals scaled for even Thickness across angled corner faces."""
    out: dict[bmesh.types.BMVert, Vector] = {}
    for v in cap_verts:
        adj = [f for f in v.link_faces if f in cap_faces and f.normal.length > 1e-8]
        if not adj:
            out[v] = _vec_norm(v.normal, Vector((0.0, 0.0, 1.0)))
            continue
        avg = sum((f.normal for f in adj), Vector((0.0, 0.0, 0.0))).normalized()
        avg_dot = sum(max(0.2, avg.dot(f.normal)) for f in adj) / len(adj)
        factor = min(2.5, 1.0 / avg_dot)
        out[v] = avg * factor
    return out


def _inward_face_miters(
    cap_verts: list[bmesh.types.BMVert],
    cap_faces: set[bmesh.types.BMFace],
) -> dict[bmesh.types.BMVert, Vector]:
    """Compute inward XY miter vectors for boundary vertices (+Offset = Maya inward inset)."""
    inward_dirs: dict[bmesh.types.BMVert, list[Vector]] = {v: [] for v in cap_verts}
    for f in cap_faces:
        fn = _vec_norm(f.normal, Vector((0.0, 0.0, 1.0)))
        for loop in f.loops:
            edge = loop.edge
            adj_cap = sum(1 for af in edge.link_faces if af in cap_faces)
            if adj_cap != 1:
                continue
            tang = loop.link_loop_next.vert.co - loop.vert.co
            if tang.length <= 1e-8:
                continue
            inw = fn.cross(tang.normalized())
            if inw.length <= 1e-8:
                continue
            inw.normalize()
            inward_dirs[loop.vert].append(inw)
            inward_dirs[loop.link_loop_next.vert].append(inw)

    miters: dict[bmesh.types.BMVert, Vector] = {}
    for v in cap_verts:
        dirs = inward_dirs.get(v, [])
        if not dirs:
            miters[v] = Vector((0.0, 0.0, 0.0))
            continue
        bis = sum(dirs, Vector((0.0, 0.0, 0.0)))
        if bis.length <= 1e-8:
            miters[v] = Vector((0.0, 0.0, 0.0))
            continue
        bis.normalize()
        dot = max(0.25, sum(max(0.25, bis.dot(d)) for d in dirs) / len(dirs))
        miters[v] = bis * min(2.5, 1.0 / dot)
    return miters


def _inward_edge_miters(edges: list[bmesh.types.BMEdge], edge_normals: dict[bmesh.types.BMVert, Vector]) -> dict[bmesh.types.BMVert, Vector]:
    """Compute perpendicular coplanar offset vectors for edge extrusions (+Offset = widen/inset)."""
    verts = list({v for e in edges for v in e.verts})
    if not verts:
        return {}
    centroid = sum((v.co for v in verts), Vector((0.0, 0.0, 0.0))) / len(verts)
    dirs: dict[bmesh.types.BMVert, list[Vector]] = {v: [] for v in verts}
    for e in edges:
        v0, v1 = e.verts[0], e.verts[1]
        tang = v1.co - v0.co
        if tang.length <= 1e-8:
            continue
        tang.normalize()
        mid = (v0.co + v1.co) * 0.5
        n_avg = _vec_norm(edge_normals.get(v0, Vector((0, 0, 1))) + edge_normals.get(v1, Vector((0, 0, 1))), Vector((0, 0, 1)))
        perp = n_avg.cross(tang)
        if perp.length <= 1e-8:
            continue
        perp.normalize()
        if perp.dot(centroid - mid) < 0.0:
            perp = -perp
        dirs[v0].append(perp)
        dirs[v1].append(perp)

    out: dict[bmesh.types.BMVert, Vector] = {}
    for v in verts:
        dlist = dirs[v]
        if not dlist:
            out[v] = Vector((0.0, 0.0, 0.0))
            continue
        bis = sum(dlist, Vector((0.0, 0.0, 0.0)))
        out[v] = bis.normalized() if bis.length > 1e-8 else Vector((0.0, 0.0, 0.0))
    return out


def _extract_ordered_curve_points_local(context, mesh_obj: bpy.types.Object, curve_obj: bpy.types.Object) -> list[Vector]:
    """Sample ordered polyline vertices from an evaluated Curve object in mesh_obj local space."""
    depsgraph = context.evaluated_depsgraph_get()
    ev = curve_obj.evaluated_get(depsgraph)
    c_mesh = ev.to_mesh()
    try:
        if c_mesh is None or len(c_mesh.vertices) < 2:
            return []
        to_local = mesh_obj.matrix_world.inverted_safe() @ curve_obj.matrix_world
        adj: dict[int, list[int]] = {i: [] for i in range(len(c_mesh.vertices))}
        for e in c_mesh.edges:
            a, b = int(e.vertices[0]), int(e.vertices[1])
            adj[a].append(b)
            adj[b].append(a)

        endpoints = [i for i, nbrs in adj.items() if len(nbrs) == 1]
        start = endpoints[0] if endpoints else next((i for i, nbrs in adj.items() if nbrs), 0)
        ordered_indices: list[int] = [start]
        visited = {start}
        cur = start
        while True:
            nxt = next((n for n in adj[cur] if n not in visited), None)
            if nxt is None:
                break
            visited.add(nxt)
            ordered_indices.append(nxt)
            cur = nxt
        if len(ordered_indices) < 2:
            return [to_local @ v.co for v in c_mesh.vertices]
        return [to_local @ c_mesh.vertices[idx].co for idx in ordered_indices]
    finally:
        ev.to_mesh_clear()


def sample_curve_frames_local(
    context,
    mesh_obj: bpy.types.Object,
    curve_obj: bpy.types.Object,
    divisions: int,
) -> list[tuple[Vector, Matrix]]:
    """Resample curve into (divisions + 1) arc-length positions & parallel-transport frames."""
    pts = _extract_ordered_curve_points_local(context, mesh_obj, curve_obj)
    if len(pts) < 2:
        return []

    cum_len = [0.0]
    for i in range(1, len(pts)):
        cum_len.append(cum_len[-1] + (pts[i] - pts[i - 1]).length)
    total = cum_len[-1]
    if total <= 1e-8:
        return []

    samples: list[Vector] = []
    segs = max(1, int(divisions))
    seg_idx = 0
    for k in range(segs + 1):
        target_d = total * (k / segs)
        while seg_idx < len(pts) - 2 and cum_len[seg_idx + 1] < target_d:
            seg_idx += 1
        span = cum_len[seg_idx + 1] - cum_len[seg_idx]
        frac = (target_d - cum_len[seg_idx]) / span if span > 1e-8 else 0.0
        samples.append(pts[seg_idx].lerp(pts[seg_idx + 1], frac))

    frames: list[tuple[Vector, Matrix]] = []
    prev_z = _vec_norm(samples[1] - samples[0], Vector((0.0, 0.0, 1.0)))
    basis0 = _orthonormal_basis_from_z(prev_z)
    prev_x = basis0.col[0].copy()

    for k in range(len(samples)):
        if k == 0:
            tan = _vec_norm(samples[1] - samples[0], prev_z)
        elif k == len(samples) - 1:
            tan = _vec_norm(samples[-1] - samples[-2], prev_z)
        else:
            tan = _vec_norm(samples[k + 1] - samples[k - 1], prev_z)

        x_proj = prev_x - tan * prev_x.dot(tan)
        if x_proj.length <= 1e-6:
            basis = _orthonormal_basis_from_z(tan)
            x_axis = basis.col[0].copy()
        else:
            x_axis = x_proj.normalized()
        y_axis = tan.cross(x_axis).normalized()
        basis = Matrix((x_axis, y_axis, tan)).transposed()
        frames.append((samples[k], basis))
        prev_z = tan
        prev_x = x_axis
    return frames


def _transform_step_coord(
    base_pos: Vector,
    miter: Vector,
    even_norm: Vector,
    pivot: Vector,
    basis: Matrix,
    basis_inv: Matrix,
    t: float,
    thickness: float,
    local_translate: Vector,
    offset: float,
    taper: float,
    twist: float,
    local_scale: Vector,
    local_rotate: Vector,
    curve_frames: list[tuple[Vector, Matrix]] | None,
    step_idx: int,
) -> Vector:
    """Compute extruded vertex position at normalized fraction t in [0, 1]."""
    p_off = base_pos + miter * (offset * t)
    rel = basis_inv @ (p_off - pivot)

    s_taper = 1.0 + (taper - 1.0) * t
    sx = s_taper * (1.0 + (local_scale.x - 1.0) * t)
    sy = s_taper * (1.0 + (local_scale.y - 1.0) * t)
    sz = 1.0 + (local_scale.z - 1.0) * t
    rel = Vector((rel.x * sx, rel.y * sy, rel.z * sz))

    rot_e = Euler(
        (local_rotate.x * t, local_rotate.y * t, local_rotate.z * t + twist * t),
        "XYZ",
    )
    rel = rot_e.to_matrix() @ rel

    if curve_frames and step_idx < len(curve_frames):
        c0_pos, _c0_basis = curve_frames[0]
        ck_pos, ck_basis = curve_frames[step_idx]
        pos = pivot + (ck_pos - c0_pos) + ck_basis @ rel
        if abs(local_translate.x) > 1e-8 or abs(local_translate.y) > 1e-8 or abs(local_translate.z) > 1e-8:
            pos = pos + ck_basis @ (local_translate * t)
        if abs(thickness) > 1e-8:
            pos = pos + even_norm * (thickness * t)
        return pos

    return pivot + basis @ rel + even_norm * (thickness * t) + basis @ (local_translate * t)


def _connected_face_islands(faces: list[bmesh.types.BMFace]) -> list[list[bmesh.types.BMFace]]:
    """Group faces into connected edge-adjacent islands (for Maya Keep Faces Together)."""
    remaining = set(faces)
    islands: list[list[bmesh.types.BMFace]] = []
    for seed in faces:
        if seed not in remaining:
            continue
        island: list[bmesh.types.BMFace] = []
        queue = deque([seed])
        remaining.remove(seed)
        while queue:
            cur = queue.popleft()
            island.append(cur)
            for e in cur.edges:
                for af in e.link_faces:
                    if af in remaining:
                        remaining.remove(af)
                        queue.append(af)
        islands.append(island)
    return islands


def _map_extruded_verts(old_verts: list[bmesh.types.BMVert], new_vert_set: set[bmesh.types.BMVert]) -> dict[bmesh.types.BMVert, bmesh.types.BMVert]:
    """Map each pre-extrude cap vertex cleanly to its unique post-extrude cap vertex."""
    mapping: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}
    for ov in old_verts:
        if ov in new_vert_set:
            mapping[ov] = ov
            continue
        for e in ov.link_edges:
            other = e.other_vert(ov)
            if other in new_vert_set:
                mapping[ov] = other
                break
    return mapping


def extrude_faces_maya(
    bm: bmesh.types.BMesh,
    obj: bpy.types.Object,
    sel_faces: list[bmesh.types.BMFace],
    *,
    space: str = "LOCAL",
    keep_faces_together: bool = True,
    thickness: float = 0.0,
    local_translate: Vector = Vector((0.0, 0.0, 0.0)),
    offset: float = 0.0,
    divisions: int = 1,
    taper: float = 1.0,
    twist: float = 0.0,
    local_scale: Vector = Vector((1.0, 1.0, 1.0)),
    local_rotate: Vector = Vector((0.0, 0.0, 0.0)),
    curve_frames: list[tuple[Vector, Matrix]] | None = None,
) -> list[bmesh.types.BMFace]:
    """Extrude polygon faces with full Maya polyExtrudeFace attributes."""
    groups = _connected_face_islands(sel_faces) if keep_faces_together else [[f] for f in sel_faces]
    divs = max(1, int(divisions))
    final_faces: list[bmesh.types.BMFace] = []

    for group in groups:
        cap_set = set(group)
        cap_verts = list({v for f in group for v in f.verts})
        even_norms = _even_vertex_normals(cap_verts, cap_set)
        miters = _inward_face_miters(cap_verts, cap_set)
        hint_x = None
        for e in group[0].edges:
            d = e.verts[1].co - e.verts[0].co
            if d.length > 1e-8:
                hint_x = d.normalized()
                break
        pivot, basis = _compute_group_frame(obj, cap_verts, even_norms, hint_x, space)
        basis_inv = basis.inverted_safe()

        # Store analytical vertex data keyed by initial seed vertex
        seed_info = {
            v: (v.co.copy(), miters[v].copy(), even_norms[v].copy())
            for v in cap_verts
        }
        cur_to_seed: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {v: v for v in cap_verts}
        cur_faces = list(group)

        for step in range(1, divs + 1):
            t = step / divs
            cur_verts = list({v for f in cur_faces for v in f.verts})
            if keep_faces_together:
                cur_edges = list({e for f in cur_faces for e in f.edges})
                res = bmesh.ops.extrude_face_region(bm, geom=cur_faces + cur_edges + cur_verts)
                new_faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace) and g.is_valid]
            else:
                res = bmesh.ops.extrude_discrete_faces(bm, faces=cur_faces)
                new_faces = [f for f in res["faces"] if f.is_valid]

            new_vset = {v for f in new_faces for v in f.verts}
            vmap = _map_extruded_verts(cur_verts, new_vset)
            next_to_seed: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}

            for old_v, new_v in vmap.items():
                seed_v = cur_to_seed.get(old_v)
                if seed_v is None:
                    continue
                next_to_seed[new_v] = seed_v
                base_co, miter, even_n = seed_info[seed_v]
                new_v.co = _transform_step_coord(
                    base_co,
                    miter,
                    even_n,
                    pivot,
                    basis,
                    basis_inv,
                    t,
                    thickness,
                    local_translate,
                    offset,
                    taper,
                    twist,
                    local_scale,
                    local_rotate,
                    curve_frames,
                    step,
                )
            cur_faces = new_faces
            cur_to_seed = next_to_seed

        final_faces.extend(cur_faces)

    for grp in (bm.verts, bm.edges, bm.faces):
        for el in grp:
            el.select = False
    for f in final_faces:
        if f.is_valid:
            f.select_set(True)
    bm.normal_update()
    bm.select_flush_mode()
    return final_faces


def extrude_edges_maya(
    bm: bmesh.types.BMesh,
    obj: bpy.types.Object,
    sel_edges: list[bmesh.types.BMEdge],
    *,
    space: str = "LOCAL",
    keep_faces_together: bool = True,
    thickness: float = 0.0,
    local_translate: Vector = Vector((0.0, 0.0, 0.0)),
    offset: float = 0.0,
    divisions: int = 1,
    taper: float = 1.0,
    twist: float = 0.0,
    local_scale: Vector = Vector((1.0, 1.0, 1.0)),
    local_rotate: Vector = Vector((0.0, 0.0, 0.0)),
    curve_frames: list[tuple[Vector, Matrix]] | None = None,
) -> list[bmesh.types.BMEdge]:
    """Extrude polygon edges with full Maya polyExtrudeEdge attributes."""
    groups = [list(sel_edges)] if keep_faces_together else [[e] for e in sel_edges]
    divs = max(1, int(divisions))
    final_edges: list[bmesh.types.BMEdge] = []

    for group in groups:
        cap_verts = list({v for e in group for v in e.verts})
        vert_normals: dict[bmesh.types.BMVert, Vector] = {}
        for v in cap_verts:
            fn = sum((f.normal for f in v.link_faces if f.normal.length > 1e-8), Vector((0.0, 0.0, 0.0)))
            vert_normals[v] = _vec_norm(fn, _vec_norm(v.normal, Vector((0.0, 0.0, 1.0))))
        miters = _inward_edge_miters(group, vert_normals)

        hint_x = None
        for e in group:
            d = e.verts[1].co - e.verts[0].co
            if d.length > 1e-8:
                hint_x = d.normalized()
                break
        pivot, basis = _compute_group_frame(obj, cap_verts, vert_normals, hint_x, space)
        basis_inv = basis.inverted_safe()

        seed_info = {
            v: (v.co.copy(), miters[v].copy(), vert_normals[v].copy())
            for v in cap_verts
        }
        cur_to_seed: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {v: v for v in cap_verts}
        cur_edges = list(group)

        for step in range(1, divs + 1):
            t = step / divs
            cur_verts = list({v for e in cur_edges for v in e.verts})
            res = bmesh.ops.extrude_edge_only(bm, edges=cur_edges)
            new_edges = [g for g in res["geom"] if isinstance(g, bmesh.types.BMEdge) and g.is_valid]
            new_vset = {v for e in new_edges for v in e.verts}
            vmap = _map_extruded_verts(cur_verts, new_vset)
            next_to_seed: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}

            for old_v, new_v in vmap.items():
                seed_v = cur_to_seed.get(old_v)
                if seed_v is None:
                    continue
                next_to_seed[new_v] = seed_v
                base_co, miter, even_n = seed_info[seed_v]
                new_v.co = _transform_step_coord(
                    base_co,
                    miter,
                    even_n,
                    pivot,
                    basis,
                    basis_inv,
                    t,
                    thickness,
                    local_translate,
                    offset,
                    taper,
                    twist,
                    local_scale,
                    local_rotate,
                    curve_frames,
                    step,
                )
            cur_edges = new_edges
            cur_to_seed = next_to_seed

        final_edges.extend(cur_edges)

    for grp in (bm.verts, bm.edges, bm.faces):
        for el in grp:
            el.select = False
    for e in final_edges:
        if e.is_valid:
            e.select_set(True)
    bm.normal_update()
    bm.select_flush_mode()
    return final_edges


def extrude_vertices_maya(
    bm: bmesh.types.BMesh,
    sel_verts: list[bmesh.types.BMVert],
    *,
    vertex_length: float = 0.25,
    vertex_width: float = 0.20,
    divisions: int = 1,
    taper: float = 1.0,
) -> list[bmesh.types.BMVert]:
    """Extrude vertices like Maya polyExtrudeVertex (bevel base of Width -> multi-step Divisions -> Length apex)."""
    divs = max(1, int(divisions))
    width = max(1e-4, float(vertex_width))
    snapshots = [
        (v, v.co.copy(), _vec_norm(v.normal, Vector((0.0, 0.0, 1.0))), bool(v.link_faces))
        for v in sel_verts
        if v.is_valid
    ]
    apex_verts: list[bmesh.types.BMVert] = []

    for vert, orig_co, orig_norm, has_faces in snapshots:
        if not vert.is_valid:
            continue
        if not has_faces:
            cur_v = vert
            for step in range(1, divs + 1):
                res = bmesh.ops.extrude_vert_indiv(bm, verts=[cur_v])
                nvs = [nv for nv in res.get("verts", []) if nv.is_valid]
                if not nvs:
                    break
                cur_v = nvs[0]
                cur_v.co = orig_co + orig_norm * (vertex_length * (step / divs))
            if cur_v.is_valid:
                apex_verts.append(cur_v)
            continue

        bev = bmesh.ops.bevel(
            bm,
            geom=[vert],
            offset=width,
            offset_type="OFFSET",
            segments=1,
            profile=0.5,
            affect="VERTICES",
            clamp_overlap=True,
        )
        base_faces = [f for f in bev.get("faces", []) if f.is_valid]
        if not base_faces:
            continue
        cur_face = base_faces[0]
        ring_base = {v: v.co.copy() for v in cur_face.verts}
        ring_center = sum(ring_base.values(), Vector((0.0, 0.0, 0.0))) / max(1, len(ring_base))
        cur_to_ring = {v: v for v in cur_face.verts}

        for step in range(1, divs):
            t = step / divs
            cur_verts = list(cur_face.verts)
            res_ex = bmesh.ops.extrude_discrete_faces(bm, faces=[cur_face])
            new_fs = [f for f in res_ex.get("faces", []) if f.is_valid]
            if not new_fs:
                break
            next_face = new_fs[0]
            new_vset = set(next_face.verts)
            vmap = _map_extruded_verts(cur_verts, new_vset)
            scale = max(0.05, (1.0 - t) * (1.0 + (taper - 1.0) * t))
            next_to_ring: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}
            for old_v, new_v in vmap.items():
                rv = cur_to_ring.get(old_v)
                if rv is None:
                    continue
                next_to_ring[new_v] = rv
                radial = ring_base[rv] - ring_center
                new_v.co = ring_center + radial * scale + orig_norm * (vertex_length * t)
            cur_face = next_face
            cur_to_ring = next_to_ring

        if cur_face.is_valid:
            poke_res = bmesh.ops.poke(bm, faces=[cur_face])
            p_verts = [pv for pv in poke_res.get("verts", []) if pv.is_valid]
            if p_verts:
                apex = p_verts[0]
                apex.co = orig_co + orig_norm * vertex_length
                apex_verts.append(apex)

    for grp in (bm.verts, bm.edges, bm.faces):
        for el in grp:
            el.select = False
    for av in apex_verts:
        if av.is_valid:
            av.select_set(True)
    bm.normal_update()
    bm.select_flush_mode()
    return apex_verts


class MAYA_UX_OT_maya_extrude(bpy.types.Operator):
    """Maya Edit Mesh > Extrude (Face / Edge / Vertex / Curve) with Keep Faces Together & Local/World space."""

    bl_idname = "maya_ux.maya_extrude"
    bl_label = "Maya Extrude"
    bl_options = {"REGISTER", "UNDO"}

    space: EnumProperty(
        name="Space",
        description="Switch transformation frame between component Local Normals and World axes",
        items=[
            ("LOCAL", "Local", "Extrude along component Local Normal axes"),
            ("WORLD", "World", "Extrude along Global World X / Y / Z axes"),
        ],
        default="LOCAL",
    )
    keep_faces_together: BoolProperty(
        name="Keep Faces Together",
        description="Extrude adjacent faces or edges as a unified region (ON) or individually per component (OFF)",
        default=True,
    )
    thickness: FloatProperty(
        name="Thickness",
        description="Extrude distance along component vertex/face normals",
        default=0.0,
        step=5,
        unit="LENGTH",
    )
    local_translate: FloatVectorProperty(
        name="Translate",
        description="Translate extruded components along Local or World X, Y, Z",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype="TRANSLATION",
    )
    offset: FloatProperty(
        name="Offset",
        description="Inset (+) or expand (-) the extruded boundary uniformly",
        default=0.0,
        step=5,
        unit="LENGTH",
    )
    divisions: IntProperty(
        name="Divisions",
        description="Number of subdivision segments along the extrusion",
        default=1,
        min=1,
        max=64,
    )
    taper: FloatProperty(
        name="Taper",
        description="Scale factor applied along the extrusion length (1.0 = straight)",
        default=1.0,
        min=0.0,
        max=5.0,
        step=5,
    )
    twist: FloatProperty(
        name="Twist",
        description="Twist angle around the extrusion Z axis",
        default=0.0,
        subtype="ANGLE",
    )
    local_scale: FloatVectorProperty(
        name="Local Scale",
        description="Scale extruded cap around its pivot (X, Y, Z)",
        size=3,
        default=(1.0, 1.0, 1.0),
        subtype="XYZ",
    )
    local_rotate: FloatVectorProperty(
        name="Local Rotate",
        description="Rotate extruded cap around its pivot (X, Y, Z)",
        size=3,
        default=(0.0, 0.0, 0.0),
        subtype="EULER",
    )
    vertex_length: FloatProperty(
        name="Length",
        description="Apex length along vertex normal (Vertex Extrude)",
        default=0.25,
        step=5,
        unit="LENGTH",
    )
    vertex_width: FloatProperty(
        name="Width",
        description="Base bevel width around extruded vertex (Vertex Extrude)",
        default=0.20,
        min=0.001,
        step=5,
        unit="LENGTH",
    )
    use_curve: BoolProperty(
        name="Use Curve Path",
        description="Extrude along a selected or assigned Bezier/NURBS curve path",
        default=False,
    )
    curve_name: StringProperty(
        name="Curve",
        description="Target Curve object name for Extrude Along Curve",
        default="",
    )
    show_advanced: BoolProperty(
        name="Transform & Curve Options",
        description="Show Taper, Twist, Local Scale/Rotate, Translate X/Y, and Curve Path controls",
        default=False,
    )

    _last_comp_mode: str = "FACE"

    def _resolve_curve_object(self, context, mesh_obj: bpy.types.Object) -> bpy.types.Object | None:
        if not self.use_curve:
            return None
        if self.curve_name and self.curve_name in bpy.data.objects:
            cand = bpy.data.objects[self.curve_name]
            if cand != mesh_obj and cand.type == "CURVE":
                return cand
        for o in getattr(context, "selected_objects", ()) or ():
            if o != mesh_obj and o.type == "CURVE":
                return o
        scene_curve = getattr(context.scene, "maya_ux_extrude_curve", None)
        if scene_curve is not None and scene_curve != mesh_obj and scene_curve.type == "CURVE":
            return scene_curve
        return None

    def invoke(self, context, event):
        self.thickness = 0.0
        self.local_translate = (0.0, 0.0, 0.0)
        self.offset = 0.0
        self.divisions = 1
        self.taper = 1.0
        self.twist = 0.0
        self.local_scale = (1.0, 1.0, 1.0)
        self.local_rotate = (0.0, 0.0, 0.0)
        self.vertex_length = 0.25
        self.vertex_width = 0.20

        scene = context.scene
        self.keep_faces_together = bool(getattr(scene, "maya_ux_keep_faces_together", True))
        self.space = getattr(scene, "maya_ux_extrude_space", "LOCAL")

        mesh_obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
        sel_curve = next(
            (o for o in (getattr(context, "selected_objects", ()) or ()) if o != mesh_obj and o.type == "CURVE"),
            None,
        )
        if sel_curve is not None:
            self.use_curve = True
            self.curve_name = sel_curve.name
            self.divisions = 8
            self.show_advanced = True
        else:
            self.use_curve = False
            self.curve_name = ""

        return self.execute(context)

    def execute(self, context):
        if context.mode != "EDIT_MESH":
            self.report({"WARNING"}, "Switch to Edit Mode with Faces, Edges, or Vertices selected")
            return {"CANCELLED"}

        obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
        if obj is None or obj.type != "MESH" or obj.data is None:
            self.report({"WARNING"}, "Select a Mesh object in Edit Mode")
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        comp_mode = detect_extrude_component(context, bm)
        if not comp_mode:
            self.report({"WARNING"}, "Select at least one Face, Edge, or Vertex to extrude")
            return {"CANCELLED"}

        MAYA_UX_OT_maya_extrude._last_comp_mode = comp_mode
        scene = context.scene
        scene.maya_ux_keep_faces_together = bool(self.keep_faces_together)
        scene.maya_ux_extrude_space = self.space

        curve_obj = self._resolve_curve_object(context, obj)
        curve_frames = sample_curve_frames_local(context, obj, curve_obj, self.divisions) if curve_obj is not None else None

        if comp_mode == "FACE":
            sel_faces = [f for f in bm.faces if f.select and not f.hide]
            res = extrude_faces_maya(
                bm,
                obj,
                sel_faces,
                space=self.space,
                keep_faces_together=self.keep_faces_together,
                thickness=self.thickness,
                local_translate=Vector(self.local_translate),
                offset=self.offset,
                divisions=self.divisions,
                taper=self.taper,
                twist=self.twist,
                local_scale=Vector(self.local_scale),
                local_rotate=Vector(self.local_rotate),
                curve_frames=curve_frames,
            )
            count = len(res)
            lbl = "Face"
        elif comp_mode == "EDGE":
            sel_edges = [e for e in bm.edges if e.select and not e.hide]
            res = extrude_edges_maya(
                bm,
                obj,
                sel_edges,
                space=self.space,
                keep_faces_together=self.keep_faces_together,
                thickness=self.thickness,
                local_translate=Vector(self.local_translate),
                offset=self.offset,
                divisions=self.divisions,
                taper=self.taper,
                twist=self.twist,
                local_scale=Vector(self.local_scale),
                local_rotate=Vector(self.local_rotate),
                curve_frames=curve_frames,
            )
            count = len(res)
            lbl = "Edge"
        else:
            sel_verts = [v for v in bm.verts if v.select and not v.hide]
            res = extrude_vertices_maya(
                bm,
                sel_verts,
                vertex_length=self.vertex_length,
                vertex_width=self.vertex_width,
                divisions=self.divisions,
                taper=self.taper,
            )
            count = len(res)
            lbl = "Vertex"

        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)

        # Maya Show Manipulator: activate all-in-one Transform gizmo strictly for this Extrude session
        start_extrude_session(context, self.space)

        self.report({"INFO"}, f"Maya Extrude ({lbl}, {count}): KeepTogether={'ON' if self.keep_faces_together else 'OFF'}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        comp_mode = MAYA_UX_OT_maya_extrude._last_comp_mode

        if comp_mode == "VERT":
            col = layout.column(align=True)
            col.label(text="Poly Extrude Vertex", icon="VERTEXSEL")
            col.prop(self, "vertex_length", text="Length")
            col.prop(self, "vertex_width", text="Width")
            col.prop(self, "divisions", text="Divisions")
            col.prop(self, "taper", text="Taper")
            return

        row_sp = layout.row(align=True)
        row_sp.prop(self, "space", expand=True)

        col = layout.column(align=True)
        col.prop(self, "thickness", text="Thickness")
        z_lbl = "Local Translate Z" if self.space == "LOCAL" else "World Translate Z"
        col.prop(self, "local_translate", index=2, text=z_lbl)
        col.prop(self, "offset", text="Offset")
        col.prop(self, "divisions", text="Divisions")
        layout.prop(self, "keep_faces_together", text="Keep Faces Together")

        adv_box = layout.box()
        adv_box.prop(self, "show_advanced", icon="TRIA_DOWN" if self.show_advanced else "TRIA_RIGHT", emboss=False)
        if self.show_advanced:
            acol = adv_box.column(align=True)
            acol.prop(self, "local_translate", index=0, text="Translate X")
            acol.prop(self, "local_translate", index=1, text="Translate Y")
            acol.separator()
            acol.prop(self, "taper", text="Taper")
            acol.prop(self, "twist", text="Twist")
            acol.prop(self, "local_scale", text="Scale")
            acol.prop(self, "local_rotate", text="Rotate")
            acol.separator()
            acol.prop(self, "use_curve", text="Extrude Along Curve")
            if self.use_curve:
                acol.prop_search(self, "curve_name", bpy.data, "objects", text="Curve")


class MAYA_UX_OT_toggle_keep_faces_together(bpy.types.Operator):
    """Toggle Maya Edit Mesh > Keep Faces Together (Ctrl+Shift+E)."""

    bl_idname = "maya_ux.toggle_keep_faces_together"
    bl_label = "Keep Faces Together"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        new_val = not bool(getattr(scene, "maya_ux_keep_faces_together", True))
        scene.maya_ux_keep_faces_together = new_val
        self.report({"INFO"}, f"Keep Faces Together: {'ON' if new_val else 'OFF'}")
        return {"FINISHED"}


class MAYA_UX_OT_toggle_extrude_space(bpy.types.Operator):
    """Toggle Maya Extrude Coordinate Space between Local (Normal) and World."""

    bl_idname = "maya_ux.toggle_extrude_space"
    bl_label = "Toggle Extrude Local/World"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        cur = getattr(scene, "maya_ux_extrude_space", "LOCAL")
        nxt = "WORLD" if cur == "LOCAL" else "LOCAL"
        scene.maya_ux_extrude_space = nxt
        if _EXTRUDE_SESSION_ACTIVE:
            slots = getattr(scene, "transform_orientation_slots", None)
            if slots and len(slots) > 0:
                slots[0].type = "NORMAL" if nxt == "LOCAL" else "GLOBAL"
        self.report({"INFO"}, f"Extrude Space: {nxt.title()}")
        return {"FINISHED"}


class MAYA_UX_OT_extrude_along_curve(bpy.types.Operator):
    """Extrude selected polygon faces or edges along the selected or assigned Curve path."""

    bl_idname = "maya_ux.extrude_along_curve"
    bl_label = "Extrude Along Curve"
    bl_options = {"REGISTER", "UNDO"}

    divisions: IntProperty(name="Divisions", default=8, min=1, max=64)
    taper: FloatProperty(name="Taper", default=1.0, min=0.0, max=5.0)
    twist: FloatProperty(name="Twist", default=0.0, subtype="ANGLE")

    def execute(self, context):
        if context.mode != "EDIT_MESH":
            self.report({"WARNING"}, "Enter Edit Mode and select faces or edges first")
            return {"CANCELLED"}

        mesh_obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
        curve_obj = next(
            (o for o in (getattr(context, "selected_objects", ()) or ()) if o != mesh_obj and o.type == "CURVE"),
            None,
        )
        if curve_obj is None:
            scene_curve = getattr(context.scene, "maya_ux_extrude_curve", None)
            if scene_curve is not None and scene_curve.type == "CURVE":
                curve_obj = scene_curve
        if curve_obj is None:
            self.report({"WARNING"}, "Select a Curve in Outliner or pick one in N -> Maya -> Extrude Curve")
            return {"CANCELLED"}

        return bpy.ops.maya_ux.maya_extrude(
            space=getattr(context.scene, "maya_ux_extrude_space", "LOCAL"),
            keep_faces_together=bool(getattr(context.scene, "maya_ux_keep_faces_together", True)),
            divisions=self.divisions,
            taper=self.taper,
            twist=self.twist,
            use_curve=True,
            curve_name=curve_obj.name,
            show_advanced=True,
        )


CLASSES = (
    MAYA_UX_OT_maya_extrude,
    MAYA_UX_OT_toggle_keep_faces_together,
    MAYA_UX_OT_toggle_extrude_space,
    MAYA_UX_OT_extrude_along_curve,
)


def _poll_curve(self, obj):
    return obj.type == "CURVE"


def register():
    bpy.types.Scene.maya_ux_keep_faces_together = BoolProperty(
        name="Keep Faces Together",
        description="Extrude adjacent selected faces/edges as one continuous shell (Maya Edit Mesh > Keep Faces Together)",
        default=True,
    )
    bpy.types.Scene.maya_ux_extrude_space = EnumProperty(
        name="Extrude Space",
        items=[("LOCAL", "Local", "Local Component Normal axes"), ("WORLD", "World", "Global World axes")],
        default="LOCAL",
    )
    bpy.types.Scene.maya_ux_extrude_curve = PointerProperty(
        name="Extrude Curve",
        description="Curve path used by Maya Extrude Along Curve",
        type=bpy.types.Object,
        poll=_poll_curve,
    )
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=_EXTRUDE_MSGBUS_OWNER,
        args=(),
        notify=_on_extrude_context_change,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.ToolSettings, "mesh_select_mode"),
        owner=_EXTRUDE_MSGBUS_OWNER,
        args=(),
        notify=_on_extrude_context_change,
    )


def unregister():
    bpy.msgbus.clear_by_owner(_EXTRUDE_MSGBUS_OWNER)
    end_extrude_session(bpy.context, restore_tool=True)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    for attr in ("maya_ux_extrude_curve", "maya_ux_extrude_space", "maya_ux_keep_faces_together"):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
