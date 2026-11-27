from __future__ import annotations

import math
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
from bpy_extras import view3d_utils
from mathutils import Euler, Matrix, Vector

from .preferences import get_prefs

_EXTRUDE_SESSION_ACTIVE: bool = False
_EXTRUDE_SESSION_SEL_MODE: tuple[bool, bool, bool] | None = None
_PRE_EXTRUDE_TOOL: str = "builtin.select_box"
_PRE_EXTRUDE_ORIENT: str = "GLOBAL"
_EXTRUDE_MSGBUS_OWNER = object()


def _extrude_session_header(space: str) -> str:
    return (
        f"Maya Extrude [{space.title()}]: Blue Arrow = Normal Push | "
        "Center Cube = Uniform Scale | G = Repeat Extrude | Q/W/E/R = Exit"
    )


def is_extrude_session_active() -> bool:
    """Return True while the Maya Extrude Show Manipulator session is active."""
    return _EXTRUDE_SESSION_ACTIVE


def get_pre_extrude_tool() -> str:
    """Return the non-transform tool saved before entering Extrude mode."""
    return _PRE_EXTRUDE_TOOL if _PRE_EXTRUDE_TOOL != "builtin.transform" else "builtin.select_box"


def _set_view3d_header_text(context, text: str | None):
    ctx = context or bpy.context
    wm = getattr(ctx, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.header_text_set(text)
                area.tag_redraw()


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
    """Enter Extrude session and show the dedicated Maya Extrude 3D Show Manipulator."""
    global _EXTRUDE_SESSION_ACTIVE, _EXTRUDE_SESSION_SEL_MODE, _PRE_EXTRUDE_TOOL, _PRE_EXTRUDE_ORIENT
    from . import ops_viewport

    ctx = context or bpy.context
    scene = getattr(ctx, "scene", None)
    if not _EXTRUDE_SESSION_ACTIVE:
        cur_tool = ops_viewport._get_active_tool_id(ctx)
        _PRE_EXTRUDE_TOOL = cur_tool if cur_tool != "builtin.transform" else "builtin.select_box"
        slots = getattr(scene, "transform_orientation_slots", None) if scene is not None else None
        _PRE_EXTRUDE_ORIENT = slots[0].type if (slots and len(slots) > 0) else "GLOBAL"

    _EXTRUDE_SESSION_ACTIVE = True
    ts = getattr(ctx, "tool_settings", None)
    _EXTRUDE_SESSION_SEL_MODE = tuple(bool(x) for x in ts.mesh_select_mode) if ts is not None else None
    if scene is not None:
        slots = getattr(scene, "transform_orientation_slots", None)
        if slots and len(slots) > 0:
            slots[0].type = "NORMAL" if space == "LOCAL" else "GLOBAL"

    if bool(getattr(get_prefs(ctx), "extrude_activate_gizmo", True)):
        # Hide overlapping toolbar Move/Rotate/Scale gizmo while custom 3D Extrude Manipulator is visible.
        _set_view3d_tool_safe(ctx, "builtin.select_box")
    _set_view3d_header_text(ctx, _extrude_session_header(space))


def end_extrude_session(context=None, restore_tool: bool = True):
    """Exit Extrude session, hide Extrude manipulator, and restore prior tool & orientation."""
    global _EXTRUDE_SESSION_ACTIVE, _EXTRUDE_SESSION_SEL_MODE
    if not _EXTRUDE_SESSION_ACTIVE:
        return
    _EXTRUDE_SESSION_ACTIVE = False
    _EXTRUDE_SESSION_SEL_MODE = None
    ctx = context or bpy.context
    scene = getattr(ctx, "scene", None)
    if scene is not None:
        slots = getattr(scene, "transform_orientation_slots", None)
        if slots and len(slots) > 0:
            try:
                slots[0].type = _PRE_EXTRUDE_ORIENT
            except (TypeError, ValueError):
                slots[0].type = "GLOBAL"
    _set_view3d_header_text(ctx, None)
    if restore_tool:
        _set_view3d_tool_safe(ctx, get_pre_extrude_tool())


def _on_extrude_context_change():
    if not _EXTRUDE_SESSION_ACTIVE:
        return
    ctx = bpy.context
    if getattr(ctx, "mode", "") != "EDIT_MESH":
        end_extrude_session(ctx, restore_tool=True)
        return
    ts = getattr(ctx, "tool_settings", None)
    if ts is not None and _EXTRUDE_SESSION_SEL_MODE is not None:
        if tuple(bool(x) for x in ts.mesh_select_mode) != _EXTRUDE_SESSION_SEL_MODE:
            end_extrude_session(ctx, restore_tool=True)


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


def _map_extruded_verts(
    old_verts: list[bmesh.types.BMVert],
    new_vert_set: set[bmesh.types.BMVert],
    old_cos: dict[bmesh.types.BMVert, Vector] | None = None,
) -> dict[bmesh.types.BMVert, bmesh.types.BMVert]:
    """Map each pre-extrude cap vertex cleanly to its unique post-extrude cap vertex."""
    mapping: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}
    for ov in old_verts:
        if not ov.is_valid:
            continue
        if ov in new_vert_set:
            mapping[ov] = ov
            continue
        for e in ov.link_edges:
            other = e.other_vert(ov)
            if other.is_valid and other in new_vert_set:
                mapping[ov] = other
                break
    # Interior vertices of multi-face islands are replaced rather than linked by a strut edge
    if old_cos is not None and len(mapping) < len(old_verts):
        used = set(mapping.values())
        unused = [nv for nv in new_vert_set if nv.is_valid and nv not in used]
        for ov in old_verts:
            if ov in mapping or ov not in old_cos or not unused:
                continue
            ref = old_cos[ov]
            best = min(unused, key=lambda nv: (nv.co - ref).length_squared)
            mapping[ov] = best
            unused.remove(best)
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
        group = [f for f in group if f.is_valid]
        if not group:
            continue
        cap_set = set(group)
        cap_verts = list({v for f in group for v in f.verts if v.is_valid})
        if not cap_verts:
            continue
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
            cur_faces = [f for f in cur_faces if f.is_valid]
            if not cur_faces:
                break
            cur_verts = list({v for f in cur_faces for v in f.verts if v.is_valid})
            old_cos = {v: v.co.copy() for v in cur_verts}
            if keep_faces_together:
                cur_edges = list({e for f in cur_faces for e in f.edges if e.is_valid})
                res = bmesh.ops.extrude_face_region(bm, geom=cur_faces + cur_edges + cur_verts)
                new_faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace) and g.is_valid]
            else:
                res = bmesh.ops.extrude_discrete_faces(bm, faces=cur_faces)
                new_faces = [f for f in res["faces"] if f.is_valid]

            new_vset = {v for f in new_faces for v in f.verts if v.is_valid}
            vmap = _map_extruded_verts(cur_verts, new_vset, old_cos=old_cos)
            next_to_seed: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}

            for old_v, new_v in vmap.items():
                if not new_v.is_valid:
                    continue
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
            cur_edges = [e for e in cur_edges if e.is_valid]
            if not cur_edges:
                break
            cur_verts = list({v for e in cur_edges for v in e.verts if v.is_valid})
            old_cos = {v: v.co.copy() for v in cur_verts}
            res = bmesh.ops.extrude_edge_only(bm, edges=cur_edges)
            new_edges = [g for g in res["geom"] if isinstance(g, bmesh.types.BMEdge) and g.is_valid]
            new_vset = {v for e in new_edges for v in e.verts if v.is_valid}
            vmap = _map_extruded_verts(cur_verts, new_vset, old_cos=old_cos)
            next_to_seed: dict[bmesh.types.BMVert, bmesh.types.BMVert] = {}

            for old_v, new_v in vmap.items():
                if not new_v.is_valid:
                    continue
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
            _set_view3d_header_text(
                context,
                f"Maya Extrude [{nxt.title()}]: Blue Arrow = Normal Push | Center Cube = Uniform Scale | G = Repeat Extrude | Q/W/E/R = Exit",
            )
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


def snapshot_extrude_drag(
    bm: bmesh.types.BMesh,
    obj: bpy.types.Object,
    comp_mode: str,
    space: str,
    keep_faces_together: bool,
) -> list[dict]:
    """Snapshot selected component groups for drift-free Maya Extrude manipulator dragging."""
    groups: list[dict] = []
    if comp_mode == "FACE":
        sel_faces = [f for f in bm.faces if f.select and not f.hide]
        raw_groups = _connected_face_islands(sel_faces) if keep_faces_together else [[f] for f in sel_faces]
        for grp in raw_groups:
            cap_set = set(grp)
            cap_verts = list({v for f in grp for v in f.verts})
            even_norms = _even_vertex_normals(cap_verts, cap_set)
            miters = _inward_face_miters(cap_verts, cap_set)
            hint_x = None
            for e in grp[0].edges:
                d = e.verts[1].co - e.verts[0].co
                if d.length > 1e-8:
                    hint_x = d.normalized()
                    break
            pivot, basis = _compute_group_frame(obj, cap_verts, even_norms, hint_x, space)
            if space == "LOCAL" and sum((even_norms[v] for v in cap_verts), Vector((0, 0, 0))).length <= 1e-6:
                f0 = grp[0]
                basis = _orthonormal_basis_from_z(_vec_norm(f0.normal, Vector((0, 0, 1))), hint_x=hint_x)
            groups.append({
                "verts": cap_verts,
                "base_cos": {v: v.co.copy() for v in cap_verts},
                "even_norms": even_norms,
                "miters": miters,
                "pivot": pivot,
                "basis": basis,
                "basis_inv": basis.inverted_safe(),
            })
    elif comp_mode == "EDGE":
        sel_edges = [e for e in bm.edges if e.select and not e.hide]
        raw_groups = [sel_edges] if keep_faces_together else [[e] for e in sel_edges]
        for grp in raw_groups:
            cap_verts = list({v for e in grp for v in e.verts})
            v_norms = {
                v: _vec_norm(sum((f.normal for f in v.link_faces if f.normal.length > 1e-8), Vector((0, 0, 0))), _vec_norm(v.normal, Vector((0, 0, 1))))
                for v in cap_verts
            }
            miters = _inward_edge_miters(grp, v_norms)
            hint_x = None
            for e in grp:
                d = e.verts[1].co - e.verts[0].co
                if d.length > 1e-8:
                    hint_x = d.normalized()
                    break
            pivot, basis = _compute_group_frame(obj, cap_verts, v_norms, hint_x, space)
            groups.append({
                "verts": cap_verts,
                "base_cos": {v: v.co.copy() for v in cap_verts},
                "even_norms": v_norms,
                "miters": miters,
                "pivot": pivot,
                "basis": basis,
                "basis_inv": basis.inverted_safe(),
            })
    else:
        sel_verts = [v for v in bm.verts if v.select and not v.hide]
        for v in sel_verts:
            vn = _vec_norm(v.normal, Vector((0.0, 0.0, 1.0)))
            pivot, basis = _compute_group_frame(obj, [v], {v: vn}, None, space)
            groups.append({
                "verts": [v],
                "base_cos": {v: v.co.copy()},
                "even_norms": {v: vn},
                "miters": {v: Vector((0.0, 0.0, 0.0))},
                "pivot": pivot,
                "basis": basis,
                "basis_inv": basis.inverted_safe(),
            })
    return groups


def apply_extrude_drag_delta(
    bm: bmesh.types.BMesh,
    obj: bpy.types.Object,
    comp_mode: str,
    space: str,
    keep_faces_together: bool,
    drag_mode: str,
    amount: float,
    snapshot: list[dict] | None = None,
) -> list[dict]:
    """Apply live interactive Maya Extrude handle deformation across islands/faces/edges."""
    groups = snapshot if snapshot is not None else snapshot_extrude_drag(bm, obj, comp_mode, space, keep_faces_together)
    for g in groups:
        pivot = g["pivot"]
        basis = g["basis"]
        basis_inv = g["basis_inv"]
        base_cos = g["base_cos"]
        even_norms = g["even_norms"]
        miters = g["miters"]
        has_z_extent = (
            any(abs((basis_inv @ (base_cos[v] - pivot)).z) > 1e-4 for v in g["verts"])
            if drag_mode == "SCALE_Z"
            else True
        )

        for v in g["verts"]:
            if not v.is_valid:
                continue
            bco = base_cos[v]
            if drag_mode in {"AUTO_Z", "THICKNESS"}:
                if drag_mode == "THICKNESS" or space == "LOCAL":
                    v.co = bco + even_norms[v] * amount
                else:
                    v.co = bco + basis @ Vector((0.0, 0.0, amount))
            elif drag_mode == "MOVE_X":
                v.co = bco + basis @ Vector((amount, 0.0, 0.0))
            elif drag_mode == "MOVE_Y":
                v.co = bco + basis @ Vector((0.0, amount, 0.0))
            elif drag_mode == "OFFSET":
                v.co = bco + miters[v] * amount
            else:
                rel = basis_inv @ (bco - pivot)
                if drag_mode == "UNIFORM_SCALE":
                    s = max(0.01, 1.0 + amount)
                    rel = rel * s
                elif drag_mode == "SCALE_X":
                    rel.x *= max(0.01, 1.0 + amount)
                elif drag_mode == "SCALE_Y":
                    rel.y *= max(0.01, 1.0 + amount)
                elif drag_mode == "SCALE_Z":
                    s = max(0.01, 1.0 + amount)
                    if has_z_extent:
                        rel.z *= s
                    else:
                        # Planar caps have rel.z == 0; scale cleanly in-plane instead of being a dead handle.
                        rel.x *= s
                        rel.y *= s
                elif drag_mode == "TWIST":
                    rel = Euler((0.0, 0.0, amount), "XYZ").to_matrix() @ rel
                v.co = pivot + basis @ rel

    bm.normal_update()
    return groups


def _compute_extrude_manipulator_matrix(context) -> tuple[Vector | None, Matrix]:
    """Compute world-space (pivot, 4x4 rotation) for the Maya Extrude 3D Show Manipulator."""
    obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
    if obj is None or obj.type != "MESH" or obj.data is None:
        return None, Matrix.Identity(4)

    bm = bmesh.from_edit_mesh(obj.data)
    comp_mode = detect_extrude_component(context, bm)
    if not comp_mode:
        return None, Matrix.Identity(4)

    space_mode = getattr(context.scene, "maya_ux_extrude_space", "LOCAL")
    mw = obj.matrix_world
    mw3 = mw.to_3x3()

    if comp_mode == "FACE":
        sel = [f for f in bm.faces if f.select and not f.hide]
        act = bm.select_history.active
        ref_f = act if isinstance(act, bmesh.types.BMFace) and act.is_valid and act.select else sel[-1]
        verts = list({v for f in sel for v in f.verts})
        pivot = mw @ (sum((v.co for v in verts), Vector((0, 0, 0))) / max(1, len(verts)))
        if space_mode == "WORLD":
            return pivot, Matrix.Identity(4)
        avg_n = sum((f.normal for f in sel), Vector((0, 0, 0)))
        local_z = avg_n if avg_n.length > 1e-4 else ref_f.normal
        local_x = None
        for e in ref_f.edges:
            d = e.verts[1].co - e.verts[0].co
            if d.length > 1e-6:
                local_x = d.normalized()
                break
        world_z = _vec_norm(mw3 @ local_z, Vector((0, 0, 1)))
        world_x = (mw3 @ local_x).normalized() if local_x is not None else None
        return pivot, _orthonormal_basis_from_z(world_z, hint_x=world_x).to_4x4()

    if comp_mode == "EDGE":
        sel = [e for e in bm.edges if e.select and not e.hide]
        verts = list({v for e in sel for v in e.verts})
        pivot = mw @ (sum((v.co for v in verts), Vector((0, 0, 0))) / max(1, len(verts)))
        if space_mode == "WORLD":
            return pivot, Matrix.Identity(4)
        avg_n = sum((f.normal for e in sel for f in e.link_faces if f.normal.length > 1e-8), Vector((0, 0, 0)))
        if avg_n.length <= 1e-6:
            avg_n = sum((v.normal for v in verts), Vector((0, 0, 1)))
        d = sel[-1].verts[1].co - sel[-1].verts[0].co
        world_z = _vec_norm(mw3 @ avg_n, Vector((0, 0, 1)))
        world_x = (mw3 @ d).normalized() if d.length > 1e-6 else None
        return pivot, _orthonormal_basis_from_z(world_z, hint_x=world_x).to_4x4()

    sel = [v for v in bm.verts if v.select and not v.hide]
    pivot = mw @ (sum((v.co for v in sel), Vector((0, 0, 0))) / max(1, len(sel)))
    if space_mode == "WORLD":
        return pivot, Matrix.Identity(4)
    avg_n = sum((v.normal for v in sel), Vector((0, 0, 1)))
    world_z = _vec_norm(mw3 @ avg_n, Vector((0, 0, 1)))
    return pivot, _orthonormal_basis_from_z(world_z).to_4x4()


_EXTRUDE_DRAG_AXES = {
    "AUTO_Z": Vector((0.0, 0.0, 1.0)),
    "THICKNESS": Vector((0.0, 0.0, 1.0)),
    "MOVE_X": Vector((1.0, 0.0, 0.0)),
    "MOVE_Y": Vector((0.0, 1.0, 0.0)),
    "SCALE_X": Vector((1.0, 0.0, 0.0)),
    "SCALE_Y": Vector((0.0, 1.0, 0.0)),
    "SCALE_Z": Vector((0.0, 0.0, 1.0)),
}
_EXTRUDE_DRAG_SCALE_MODES = {"UNIFORM_SCALE", "SCALE_X", "SCALE_Y", "SCALE_Z"}
_EXTRUDE_DRAG_LABELS = {
    "AUTO_Z": "Thickness / Local Z",
    "THICKNESS": "Thickness",
    "MOVE_X": "Local Translate X",
    "MOVE_Y": "Local Translate Y",
    "UNIFORM_SCALE": "Uniform Scale",
    "SCALE_X": "Local Scale X",
    "SCALE_Y": "Local Scale Y",
    "SCALE_Z": "Local Scale Z",
    "OFFSET": "Offset",
    "TWIST": "Twist",
}


def _region_and_rv3d(context):
    """Return (region, rv3d) of the 3D viewport window region, or (None, None) headless."""
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    if region is None or rv3d is None or getattr(region, "type", "") != "WINDOW":
        space = getattr(context, "space_data", None)
        area = getattr(context, "area", None)
        if space is not None and getattr(space, "type", "") == "VIEW_3D" and area is not None:
            rv3d = space.region_3d
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
    if region is None or rv3d is None:
        return None, None
    return region, rv3d


def begin_extrude_drag(context, mode: str, mouse_x: float, mouse_y: float) -> dict | None:
    """Start an interactive Maya Extrude handle drag: snapshot geometry and screen-space mapping."""
    if getattr(context, "mode", "") != "EDIT_MESH":
        return None
    obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
    if obj is None or obj.type != "MESH" or obj.data is None:
        return None
    bm = bmesh.from_edit_mesh(obj.data)
    comp_mode = detect_extrude_component(context, bm)
    if not comp_mode:
        return None

    space = getattr(context.scene, "maya_ux_extrude_space", "LOCAL")
    keep = bool(getattr(context.scene, "maya_ux_keep_faces_together", True))
    snapshot = snapshot_extrude_drag(bm, obj, comp_mode, space, keep)
    if not snapshot:
        return None

    state = {
        "obj": obj,
        "mode": mode,
        "comp_mode": comp_mode,
        "space": space,
        "keep": keep,
        "snapshot": snapshot,
        "start": Vector((float(mouse_x), float(mouse_y))),
        "pivot_2d": None,
        "screen_dir": None,
        "units_per_px": 0.01,
        "twist_sign": 1.0,
        "amount": 0.0,
    }

    region, rv3d = _region_and_rv3d(context)
    pivot, rot4 = _compute_extrude_manipulator_matrix(context)
    if region is None or rv3d is None or pivot is None:
        return state

    p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, pivot)
    if p0 is None:
        return state
    state["pivot_2d"] = p0
    rot3 = rot4.to_3x3()

    right_w = (rv3d.view_rotation @ Vector((1.0, 0.0, 0.0))).normalized()
    p_right = view3d_utils.location_3d_to_region_2d(region, rv3d, pivot + right_w)
    if p_right is not None and (p_right - p0).length > 1e-4:
        state["units_per_px"] = 1.0 / (p_right - p0).length

    axis = _EXTRUDE_DRAG_AXES.get(mode)
    if axis is not None:
        w_axis = (rot3 @ axis).normalized()
        p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, pivot + w_axis)
        if p1 is not None and (p1 - p0).length > 2.0:
            state["screen_dir"] = (p1 - p0).normalized()
            if mode not in _EXTRUDE_DRAG_SCALE_MODES:
                # World units per pixel measured along the handle axis itself (drag sticks to the cursor)
                state["units_per_px"] = 1.0 / (p1 - p0).length

    view_dir = (rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))).normalized()
    z_world = (rot3 @ Vector((0.0, 0.0, 1.0))).normalized()
    state["twist_sign"] = 1.0 if z_world.dot(view_dir) <= 0.0 else -1.0
    return state


def compute_extrude_drag_amount(state: dict, mouse_x: float, mouse_y: float, precise: bool = False, snap: bool = False) -> float:
    """Map the current mouse position to a handle amount (distance, scale factor delta or twist angle)."""
    mode = state["mode"]
    cur = Vector((float(mouse_x), float(mouse_y)))
    start = state["start"]
    delta = cur - start
    p0 = state.get("pivot_2d")
    sdir = state.get("screen_dir")

    if mode == "TWIST":
        amount = None
        if p0 is not None:
            a = start - p0
            b = cur - p0
            if a.length > 6.0 and b.length > 6.0:
                amount = math.atan2(a.x * b.y - a.y * b.x, a.dot(b)) * state.get("twist_sign", 1.0)
        if amount is None:
            amount = (delta.x + delta.y * 0.5) * 0.015
    elif mode in _EXTRUDE_DRAG_SCALE_MODES:
        amount = None
        if p0 is not None:
            if mode == "UNIFORM_SCALE":
                d0 = (start - p0).length
                if abs(d0) > 12.0:
                    d1 = (cur - p0).length
                    amount = d1 / d0 - 1.0
            elif sdir is not None:
                d0 = (start - p0).dot(sdir)
                if abs(d0) > 12.0:
                    d1 = (cur - p0).dot(sdir)
                    amount = d1 / d0 - 1.0
        if amount is None:
            px = delta.dot(sdir) if sdir is not None else (delta.x + delta.y * 0.5)
            amount = px * (0.008 if mode == "UNIFORM_SCALE" else 0.006)
    else:
        px = delta.dot(sdir) if sdir is not None else (delta.x + delta.y)
        amount = px * state.get("units_per_px", 0.01)

    if precise:
        amount *= 0.1
    if snap:
        step = math.radians(15.0) if mode == "TWIST" else 0.1
        amount = round(amount / step) * step
    if mode in _EXTRUDE_DRAG_SCALE_MODES:
        amount = max(-0.99, amount)
    return amount


def update_extrude_drag(state: dict, mouse_x: float, mouse_y: float, precise: bool = False, snap: bool = False) -> float:
    """Apply the drag amount for the given mouse position to the live edit mesh."""
    amount = compute_extrude_drag_amount(state, mouse_x, mouse_y, precise=precise, snap=snap)
    set_extrude_drag_amount(state, amount)
    return amount


def set_extrude_drag_amount(state: dict, amount: float) -> None:
    """Deform the snapshotted geometry by an absolute handle amount (0.0 restores it)."""
    obj = state["obj"]
    bm = bmesh.from_edit_mesh(obj.data)
    apply_extrude_drag_delta(
        bm,
        obj,
        state["comp_mode"],
        state["space"],
        state["keep"],
        state["mode"],
        amount,
        snapshot=state["snapshot"],
    )
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=False)
    state["amount"] = amount


def _extrude_drag_header(context, state: dict | None) -> None:
    area = getattr(context, "area", None)
    if area is None:
        return
    if state is None:
        area.header_text_set(None)
        return
    mode = state["mode"]
    amount = state.get("amount", 0.0)
    if mode == "TWIST":
        txt = f"{math.degrees(amount):.1f}°"
    elif mode in _EXTRUDE_DRAG_SCALE_MODES:
        txt = f"{1.0 + amount:.3f}"
    else:
        txt = f"{amount:.4f}"
    area.header_text_set(f"Maya Extrude  {_EXTRUDE_DRAG_LABELS.get(mode, mode)}: {txt}   (⇧ precise · ⌃ snap · RMB/Esc cancel)")


class MAYA_UX_OT_extrude_drag_handle(bpy.types.Operator):
    """Interactive drag for a Maya Extrude handle (fallback operator; the manipulator drags natively)."""

    bl_idname = "maya_ux.extrude_drag_handle"
    bl_label = "Maya Extrude Drag Handle"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Handle Mode",
        items=[
            ("AUTO_Z", "Normal / Local Z", "Push each face/island along its own normal (or World Z)"),
            ("THICKNESS", "Thickness", "Uniform normal thickness push"),
            ("MOVE_X", "Move X", "Translate along X"),
            ("MOVE_Y", "Move Y", "Translate along Y"),
            ("UNIFORM_SCALE", "Uniform Scale", "Uniform per-island scale"),
            ("SCALE_X", "Scale X", "Scale along X"),
            ("SCALE_Y", "Scale Y", "Scale along Y"),
            ("SCALE_Z", "Scale Z", "Scale along Z"),
            ("OFFSET", "Offset", "Inward/outward boundary inset"),
            ("TWIST", "Twist", "Twist around Z axis"),
        ],
        default="AUTO_Z",
    )

    def invoke(self, context, event):
        self._state = begin_extrude_drag(context, self.mode, event.mouse_region_x, event.mouse_region_y)
        if self._state is None:
            return {"CANCELLED"}
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        state = self._state
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            update_extrude_drag(state, event.mouse_region_x, event.mouse_region_y, precise=event.shift, snap=event.ctrl)
            _extrude_drag_header(context, state)
            return {"RUNNING_MODAL"}
        if (event.type == "LEFTMOUSE" and event.value == "RELEASE") or (
            event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS"
        ):
            _extrude_drag_header(context, None)
            return {"FINISHED"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            set_extrude_drag_amount(state, 0.0)
            _extrude_drag_header(context, None)
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


class MAYA_UX_OT_repeat_last(bpy.types.Operator):
    """Maya Repeat Last (G): chains a new Extrude during active Extrude session, else screen.repeat_last."""

    bl_idname = "maya_ux.repeat_last"
    bl_label = "Maya Repeat Last"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if getattr(context, "mode", "") == "EDIT_MESH" and is_extrude_session_active():
            if bpy.app.background:
                return bpy.ops.maya_ux.maya_extrude(
                    space=getattr(context.scene, "maya_ux_extrude_space", "LOCAL"),
                    keep_faces_together=bool(getattr(context.scene, "maya_ux_keep_faces_together", True)),
                )
            return bpy.ops.maya_ux.maya_extrude("INVOKE_DEFAULT")
        try:
            return bpy.ops.screen.repeat_last()
        except (TypeError, RuntimeError):
            return {"CANCELLED"}


class MAYA_UX_OT_cleanup_extrude(bpy.types.Operator):
    """Merge zero-thickness accidental double extrusions and recalculate face normals."""

    bl_idname = "maya_ux.cleanup_extrude"
    bl_label = "Fix Double Extrude"
    bl_options = {"REGISTER", "UNDO"}

    merge_distance: FloatProperty(name="Merge Distance", default=1e-4, min=1e-6, max=0.1)

    def execute(self, context):
        if getattr(context, "mode", "") != "EDIT_MESH":
            self.report({"WARNING"}, "Switch to Edit Mode to clean up double extrusions")
            return {"CANCELLED"}
        obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
        if obj is None or obj.type != "MESH" or obj.data is None:
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)
        before_verts = len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=self.merge_distance)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        after_verts = len(bm.verts)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        removed = before_verts - after_verts
        self.report({"INFO"}, f"Cleanup Extrude: merged {removed} duplicate vertex(es)")
        return {"FINISHED"}


def _extrude_selection_flags(context, pivot: Vector, rot4: Matrix) -> tuple[bool, bool]:
    """Return (use_shrink_fatten, is_planar_z) for the active Edit Mesh selection."""
    obj = getattr(context, "edit_object", None) or getattr(context, "active_object", None)
    if obj is None or obj.type != "MESH" or obj.data is None:
        return False, False
    bm = bmesh.from_edit_mesh(obj.data)
    comp_mode = detect_extrude_component(context, bm)
    is_local = getattr(context.scene, "maya_ux_extrude_space", "LOCAL") == "LOCAL"
    if comp_mode == "FACE":
        sel_faces = [f for f in bm.faces if f.select and not f.hide]
        sum_len = sum((f.normal for f in sel_faces), Vector((0.0, 0.0, 0.0))).length
        tot_len = sum(f.normal.length for f in sel_faces)
        use_shrink = bool(is_local and len(sel_faces) >= 2 and tot_len > 1e-6 and sum_len < 0.85 * tot_len)
        sel_verts = list({v for f in sel_faces for v in f.verts})
    elif comp_mode == "EDGE":
        use_shrink = False
        sel_edges = [e for e in bm.edges if e.select and not e.hide]
        sel_verts = list({v for e in sel_edges for v in e.verts})
    else:
        use_shrink = False
        sel_verts = [v for v in bm.verts if v.select and not v.hide]
    mw = obj.matrix_world
    rot_inv = rot4.to_3x3().inverted_safe()
    is_planar_z = bool(sel_verts) and max(abs((rot_inv @ ((mw @ v.co) - pivot)).z) for v in sel_verts) <= 1e-4
    return use_shrink, is_planar_z


class VIEW3D_GT_maya_extrude_box(bpy.types.Gizmo):
    """Cube handle for Maya Extrude Uniform Scale."""

    bl_idname = "VIEW3D_GT_maya_extrude_box"

    def draw(self, context):
        self.draw_preset_box(self.matrix_world @ Matrix.Scale(0.09, 4))

    def draw_select(self, context, select_id):
        self.draw_preset_box(self.matrix_world @ Matrix.Scale(0.09, 4), select_id=select_id)


class VIEW3D_GT_maya_extrude_button(bpy.types.Gizmo):
    """Small clickable ring button (Local ↔ World toggle) — runs its target operator on click."""

    bl_idname = "VIEW3D_GT_maya_extrude_button"

    def draw(self, context):
        self.draw_preset_circle(self.matrix_world, axis="POS_Z")

    def draw_select(self, context, select_id):
        self.draw_preset_circle(self.matrix_world, axis="POS_Z", select_id=select_id)


class VIEW3D_GGT_maya_extrude(bpy.types.GizmoGroup):
    """Native 3D Maya Extrude Show Manipulator powered by Blender C++ transform operators."""

    bl_idname = "VIEW3D_GGT_maya_extrude"
    bl_label = "Maya Extrude Show Manipulator"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context):
        from . import ops_viewport

        if getattr(context, "mode", "") != "EDIT_MESH" or not is_extrude_session_active():
            return False
        if not bool(getattr(get_prefs(context), "extrude_activate_gizmo", True)):
            return False
        space = ops_viewport._get_view3d_space(context)
        return space is not None and space.type == "VIEW_3D" and bool(space.show_gizmo)

    def _new_arrow(
        self,
        color,
        op_idname: str,
        rot_offset: Matrix,
        *,
        draw_style: str,
        draw_options: set[str],
        length: float,
        scale_basis: float,
        line_width: float,
        select_bias: float,
        constraint_axis: tuple[bool, bool, bool] | None = None,
        use_even_offset: bool = False,
    ):
        gz = self.gizmos.new("GIZMO_GT_arrow_3d")
        gz.draw_style = draw_style
        gz.draw_options = draw_options
        gz.length = length
        gz.color = color
        gz.alpha = 0.92
        gz.color_highlight = (1.0, 0.95, 0.15)
        gz.alpha_highlight = 1.0
        gz.use_draw_scale = True
        gz.use_draw_modal = True
        gz.use_draw_value = False
        gz.scale_basis = scale_basis
        gz.line_width = line_width
        gz.select_bias = select_bias
        op = gz.target_set_operator(op_idname)
        op.release_confirm = True
        if constraint_axis is not None:
            op.constraint_axis = constraint_axis
            op.orient_type = "NORMAL"
            self._orient_ops.append(op)
        if use_even_offset and hasattr(op, "use_even_offset"):
            op.use_even_offset = True
        self._rot_offsets[gz] = rot_offset
        return gz, op

    def setup(self, context):
        self._rot_offsets = {}
        self._orient_ops = []
        rot_x = Matrix.Rotation(math.radians(90.0), 4, "Y")
        rot_y = Matrix.Rotation(math.radians(-90.0), 4, "X")
        rot_id = Matrix.Identity(4)

        # 1. Twist Dial (lowest selection priority, outer ring)
        gz_twist = self.gizmos.new("GIZMO_GT_dial_3d")
        gz_twist.draw_options = set()
        gz_twist.color = (0.88, 0.90, 0.94)
        gz_twist.alpha = 0.55
        gz_twist.color_highlight = (1.0, 0.95, 0.15)
        gz_twist.alpha_highlight = 1.0
        gz_twist.use_draw_scale = True
        gz_twist.use_draw_modal = True
        gz_twist.use_draw_value = False
        gz_twist.scale_basis = 1.25
        gz_twist.line_width = 2.0
        gz_twist.select_bias = -4.0
        op_twist = gz_twist.target_set_operator("transform.rotate")
        op_twist.constraint_axis = (False, False, True)
        op_twist.orient_type = "NORMAL"
        op_twist.release_confirm = True
        self._orient_ops.append(op_twist)
        self._rot_offsets[gz_twist] = rot_id
        self.gz_twist = gz_twist

        # 2. Axis Scale Handles (BOX style, compact length=0.56 with select_bias=8.5 above arrows)
        self.gz_scale_x, _ = self._new_arrow(
            (0.95, 0.25, 0.25), "transform.resize", rot_x,
            draw_style="BOX", draw_options=set(), length=0.56, scale_basis=1.0, line_width=2.0, select_bias=8.5,
            constraint_axis=(True, False, False),
        )
        self.gz_scale_y, _ = self._new_arrow(
            (0.25, 0.90, 0.35), "transform.resize", rot_y,
            draw_style="BOX", draw_options=set(), length=0.56, scale_basis=1.0, line_width=2.0, select_bias=8.5,
            constraint_axis=(False, True, False),
        )
        self.gz_scale_z, self._op_scale_z = self._new_arrow(
            (0.20, 0.58, 1.0), "transform.resize", rot_id,
            draw_style="BOX", draw_options=set(), length=0.56, scale_basis=1.0, line_width=2.0, select_bias=8.5,
            constraint_axis=(False, False, True),
        )

        # 3. Normal / Move Arrows (extend well beyond scale handles & twist dial)
        self.gz_move_x, _ = self._new_arrow(
            (0.95, 0.25, 0.25), "transform.translate", rot_x,
            draw_style="NORMAL", draw_options={"STEM"}, length=1.30, scale_basis=1.0, line_width=3.0, select_bias=5.5,
            constraint_axis=(True, False, False),
        )
        self.gz_move_y, _ = self._new_arrow(
            (0.25, 0.90, 0.35), "transform.translate", rot_y,
            draw_style="NORMAL", draw_options={"STEM"}, length=1.30, scale_basis=1.0, line_width=3.0, select_bias=5.5,
            constraint_axis=(False, True, False),
        )
        self.gz_move_z, _ = self._new_arrow(
            (0.20, 0.58, 1.0), "transform.translate", rot_id,
            draw_style="NORMAL", draw_options={"STEM"}, length=1.45, scale_basis=1.0, line_width=3.0, select_bias=6.0,
            constraint_axis=(False, False, True),
        )
        self.gz_move_z_shrink, _ = self._new_arrow(
            (0.20, 0.58, 1.0), "transform.shrink_fatten", rot_id,
            draw_style="NORMAL", draw_options={"STEM"}, length=1.45, scale_basis=1.0, line_width=3.0, select_bias=6.0,
            use_even_offset=True,
        )

        # 4. Center Uniform Scale Cube (bias=10.0 above arrows & scale handles at center)
        gz_center = self.gizmos.new(VIEW3D_GT_maya_extrude_box.bl_idname)
        gz_center.color = (0.35, 0.88, 0.98)
        gz_center.alpha = 0.92
        gz_center.color_highlight = (1.0, 0.95, 0.15)
        gz_center.alpha_highlight = 1.0
        gz_center.use_draw_scale = True
        gz_center.use_draw_offset_scale = True
        gz_center.use_draw_modal = True
        gz_center.use_draw_value = False
        gz_center.scale_basis = 1.0
        gz_center.select_bias = 10.0
        op_center = gz_center.target_set_operator("transform.resize")
        op_center.constraint_axis = (False, False, False)
        op_center.orient_type = "NORMAL"
        op_center.release_confirm = True
        self._orient_ops.append(op_center)
        self._rot_offsets[gz_center] = rot_id
        self.gz_scale_center = gz_center

        # 5. Local <-> World Toggle Button (outside 1.25 Twist ring, radius ~1.63)
        gz_sw = self.gizmos.new(VIEW3D_GT_maya_extrude_button.bl_idname)
        gz_sw.color = (0.35, 0.88, 0.98)
        gz_sw.alpha = 0.95
        gz_sw.color_highlight = (1.0, 0.95, 0.15)
        gz_sw.alpha_highlight = 1.0
        gz_sw.use_draw_scale = True
        gz_sw.use_draw_offset_scale = True
        gz_sw.use_draw_value = False
        gz_sw.scale_basis = 1.0
        gz_sw.line_width = 3.0
        gz_sw.select_bias = 12.0
        gz_sw.matrix_offset = Matrix.Translation((1.15, 1.15, 0.0)) @ Matrix.Scale(0.11, 4)
        gz_sw.target_set_operator("maya_ux.toggle_extrude_space")
        self._rot_offsets[gz_sw] = rot_id
        self.gz_space_btn = gz_sw

        self._update_gizmos(context)

    def _update_gizmos(self, context):
        all_gz = tuple(self._rot_offsets.keys())
        pivot, rot4 = _compute_extrude_manipulator_matrix(context)
        if pivot is None:
            for gz in all_gz:
                gz.hide = True
                gz.hide_select = True
            return

        use_shrink, is_planar_z = _extrude_selection_flags(context, pivot, rot4)
        is_local = getattr(context.scene, "maya_ux_extrude_space", "LOCAL") == "LOCAL"
        orient_type = "NORMAL" if is_local else "GLOBAL"
        rot3 = rot4.to_3x3()

        for op in self._orient_ops:
            op.orient_type = orient_type
            if hasattr(op, "orient_matrix_type"):
                op.orient_matrix_type = orient_type
            op.orient_matrix = rot3
        self._op_scale_z.constraint_axis = (True, True, False) if is_planar_z else (False, False, True)

        mat = Matrix.Translation(pivot) @ rot4
        self.gz_space_btn.color = (0.35, 0.88, 0.98) if is_local else (1.0, 0.58, 0.18)
        for gz, rot_off in self._rot_offsets.items():
            gz.hide = False
            gz.hide_select = False
            gz.matrix_basis = mat @ rot_off

        self.gz_move_z.hide = use_shrink
        self.gz_move_z.hide_select = use_shrink
        self.gz_move_z_shrink.hide = not use_shrink
        self.gz_move_z_shrink.hide_select = not use_shrink

    def refresh(self, context):
        self._update_gizmos(context)

    def draw_prepare(self, context):
        self._update_gizmos(context)


def draw_maya_extrude_mesh_menu(self, context):
    """Append Maya Extrude actions directly to Edit Mode top Mesh menu."""
    layout = self.layout
    layout.separator()
    layout.operator("maya_ux.maya_extrude", text="Maya Extrude (Face / Edge / Vert)", icon="FACESEL")
    keep_on = bool(getattr(context.scene, "maya_ux_keep_faces_together", True))
    layout.operator(
        "maya_ux.toggle_keep_faces_together",
        text=f"Keep Faces Together ({'ON' if keep_on else 'OFF'})",
    )
    layout.operator("maya_ux.extrude_along_curve", text="Maya Extrude Along Curve", icon="CURVE_BEZCURVE")
    layout.operator("maya_ux.cleanup_extrude", text="Fix Double Extrude", icon="AUTOMERGE_ON")


CLASSES = (
    MAYA_UX_OT_maya_extrude,
    MAYA_UX_OT_extrude_drag_handle,
    MAYA_UX_OT_repeat_last,
    MAYA_UX_OT_cleanup_extrude,
    MAYA_UX_OT_toggle_keep_faces_together,
    MAYA_UX_OT_toggle_extrude_space,
    MAYA_UX_OT_extrude_along_curve,
    VIEW3D_GT_maya_extrude_box,
    VIEW3D_GT_maya_extrude_button,
    VIEW3D_GGT_maya_extrude,
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
    bpy.types.VIEW3D_MT_edit_mesh.append(draw_maya_extrude_mesh_menu)


def unregister():
    try:
        bpy.types.VIEW3D_MT_edit_mesh.remove(draw_maya_extrude_mesh_menu)
    except ValueError:
        pass
    bpy.msgbus.clear_by_owner(_EXTRUDE_MSGBUS_OWNER)
    end_extrude_session(bpy.context, restore_tool=True)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    for attr in ("maya_ux_extrude_curve", "maya_ux_extrude_space", "maya_ux_keep_faces_together"):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
