from __future__ import annotations

from math import hypot

import bmesh
import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from .preferences import get_prefs

_PREV_FACE_CENTER: dict[int, bool] = {}
_GROW_HISTORY: dict[tuple, list[tuple[tuple, tuple]]] = {}
_PICKWALK_STATE: dict[str, dict] = {}
_EDGE_LOOP_ORIGIN: dict[str, dict] = {}
_SAVED_COMPONENT_COLORS: dict[str, tuple] = {}
_LAST_COMPONENT_DISPLAY_KEY: tuple | None = None
_MSGBUS_OWNER = object()
_SELECTED_VERT_DRAW_HANDLE = None
_SELECTED_WIRE_DRAW_HANDLE = None
_SELECTED_WIRE_CACHE: dict[int, tuple[tuple, object]] = {}
_SELECTED_WIRE_CACHE_GEN: int = 0
_MAX_GROW_HISTORY = 64
_MAX_SELECTED_WIRE_EDGES = 250_000

_DEFAULT_COMPONENT_FALLBACKS = {
    "edge_select": (1.0, 0.6, 0.0),
    "edge_mode_select": (1.0, 0.847, 0.0),
    "face_select": (1.0, 0.639, 0.0, 0.2),
    "face_mode_select": (1.0, 0.718, 0.0, 0.2),
    "editmesh_active": (1.0, 1.0, 1.0, 0.5),
}


def _snapshot_component_colors(v3d) -> dict[str, tuple]:
    if _SAVED_COMPONENT_COLORS:
        return _SAVED_COMPONENT_COLORS
    wire_rgb = tuple(round(float(c), 4) for c in v3d.wire_edit[:3])
    for attr, fallback in _DEFAULT_COMPONENT_FALLBACKS.items():
        if not hasattr(v3d, attr):
            continue
        cur = tuple(float(c) for c in getattr(v3d, attr))
        if attr in {"edge_select", "edge_mode_select"}:
            if tuple(round(float(c), 4) for c in cur[:3]) == wire_rgb:
                cur = fallback
        elif len(cur) >= 4 and cur[3] < 0.05:
            cur = fallback
        _SAVED_COMPONENT_COLORS[attr] = cur
    return _SAVED_COMPONENT_COLORS


def _tag_view3d_redraw(ctx):
    wm = getattr(ctx, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def restore_component_selection_display(context=None):
    """Restore original Edit Mesh component highlight colors saved before isolation."""
    global _LAST_COMPONENT_DISPLAY_KEY
    ctx = context or bpy.context
    prefs_root = getattr(ctx, "preferences", None)
    if prefs_root is not None and prefs_root.themes and _SAVED_COMPONENT_COLORS:
        v3d = prefs_root.themes[0].view_3d
        for attr, orig in _SAVED_COMPONENT_COLORS.items():
            if hasattr(v3d, attr):
                setattr(v3d, attr, orig)
        _tag_view3d_redraw(ctx)
    _LAST_COMPONENT_DISPLAY_KEY = None


def reset_component_color_cache(context=None):
    """Refresh saved theme color baseline (e.g. after applying a new theme)."""
    global _LAST_COMPONENT_DISPLAY_KEY
    _SAVED_COMPONENT_COLORS.clear()
    _LAST_COMPONENT_DISPLAY_KEY = None
    sync_component_selection_display(context, force=True)


def sync_component_selection_display(context=None, force: bool = False):
    """Show only active component highlights (Vert/Edge/Face) in Edit Mesh, like Maya."""
    global _LAST_COMPONENT_DISPLAY_KEY
    ctx = context or bpy.context
    prefs_root = getattr(ctx, "preferences", None)
    if prefs_root is None or not prefs_root.themes:
        return
    if not bool(getattr(get_prefs(ctx), "isolate_component_display", True)):
        if _SAVED_COMPONENT_COLORS:
            restore_component_selection_display(ctx)
            _SAVED_COMPONENT_COLORS.clear()
        return

    mode = getattr(ctx, "mode", "OBJECT")
    ts = getattr(ctx, "tool_settings", None)
    sel_mode = tuple(bool(x) for x in ts.mesh_select_mode) if ts is not None else (False, False, False)
    v3d = prefs_root.themes[0].view_3d
    wire_rgb = tuple(float(c) for c in v3d.wire_edit[:3])
    key = (mode, sel_mode if mode == "EDIT_MESH" else None, tuple(round(c, 4) for c in wire_rgb))
    if not force and key == _LAST_COMPONENT_DISPLAY_KEY:
        return
    _LAST_COMPONENT_DISPLAY_KEY = key

    saved = _snapshot_component_colors(v3d)
    is_vert_only = mode == "EDIT_MESH" and sel_mode == (True, False, False)
    is_edge_only = mode == "EDIT_MESH" and sel_mode == (False, True, False)
    is_face_only = mode == "EDIT_MESH" and sel_mode == (False, False, True)

    if not (is_vert_only or is_edge_only or is_face_only):
        for attr, orig in saved.items():
            if hasattr(v3d, attr):
                setattr(v3d, attr, orig)
        _tag_view3d_redraw(ctx)
        return

    hide_edges = is_vert_only or is_face_only
    hide_faces = is_vert_only or is_edge_only

    for attr in ("edge_select", "edge_mode_select"):
        if not hasattr(v3d, attr):
            continue
        if hide_edges:
            cur = getattr(v3d, attr)
            setattr(v3d, attr, wire_rgb + tuple(cur[3:]) if len(cur) > 3 else wire_rgb)
        elif attr in saved:
            setattr(v3d, attr, saved[attr])

    for attr in ("face_select", "face_mode_select", "editmesh_active"):
        if not hasattr(v3d, attr) or attr not in saved:
            continue
        orig = saved[attr]
        if hide_faces:
            setattr(v3d, attr, (orig[0], orig[1], orig[2], 0.0))
        else:
            setattr(v3d, attr, orig)

    _tag_view3d_redraw(ctx)


def invalidate_selected_wireframe_cache():
    """Clear cached GPU wireframe batches for selected Object Mode meshes."""
    global _SELECTED_WIRE_CACHE_GEN
    _SELECTED_WIRE_CACHE.clear()
    _SELECTED_WIRE_CACHE_GEN += 1


@persistent
def _on_load_pre_selection_cache(*_args):
    invalidate_selected_wireframe_cache()


@persistent
def _on_component_display_depsgraph(scene, depsgraph=None):
    sync_component_selection_display(bpy.context)
    if depsgraph is None or any(getattr(upd, "is_updated_geometry", False) for upd in depsgraph.updates):
        invalidate_selected_wireframe_cache()


def collect_selected_vertex_world_coords(context) -> tuple[list[Vector], Vector | None]:
    """Return world coordinates for selected Edit Mesh vertices, separating the active vertex."""
    if getattr(context, "mode", "") != "EDIT_MESH":
        return [], None
    ts = getattr(context, "tool_settings", None)
    if ts is None or not bool(ts.mesh_select_mode[0]):
        return [], None

    objs = [o for o in (getattr(context, "objects_in_mode_unique_data", None) or ()) if o.type == "MESH" and o.data is not None]
    if not objs:
        eo = getattr(context, "edit_object", None)
        if eo is not None and eo.type == "MESH" and eo.data is not None:
            objs = [eo]

    pts: list[Vector] = []
    active_pt: Vector | None = None
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        mat = obj.matrix_world
        act_elem = bm.select_history.active
        active_vert = (
            act_elem
            if isinstance(act_elem, bmesh.types.BMVert) and act_elem.is_valid and act_elem.select and not act_elem.hide
            else None
        )
        if active_vert is not None:
            active_pt = mat @ active_vert.co
        for v in bm.verts:
            if v.select and not v.hide and v is not active_vert:
                pts.append(mat @ v.co)
    return pts, active_pt


def _draw_selected_vertices_overlay():
    """Draw only selected vertices larger in Edit Mode without affecting unselected vertex size."""
    if bpy.app.background:
        return
    ctx = bpy.context
    prefs = get_prefs(ctx)
    if not bool(getattr(prefs, "enlarge_selected_vertices", True)):
        return
    space = getattr(ctx, "space_data", None)
    rv3d = getattr(ctx, "region_data", None)
    if space is None or rv3d is None or not getattr(space.overlay, "show_overlays", True):
        return

    pts, active_pt = collect_selected_vertex_world_coords(ctx)
    if not pts and active_pt is None:
        return

    show_through = (
        (getattr(rv3d, "view_perspective", "PERSP") == "ORTHO")
        or (getattr(space.shading, "type", "SOLID") == "WIREFRAME")
        or bool(getattr(space.shading, "show_xray", False))
    )
    if not show_through:
        cam_pos = rv3d.view_matrix.inverted().translation
        pts = [p + (cam_pos - p) * 0.0015 for p in pts]
        if active_pt is not None:
            active_pt = active_pt + (cam_pos - active_pt) * 0.0015

    v3d = ctx.preferences.themes[0].view_3d
    sel_rgba = (float(v3d.vertex_select[0]), float(v3d.vertex_select[1]), float(v3d.vertex_select[2]), 1.0)
    act_rgba = (float(v3d.editmesh_active[0]), float(v3d.editmesh_active[1]), float(v3d.editmesh_active[2]), 1.0)
    px_scale = max(1.0, float(getattr(ctx.preferences.system, "pixel_size", 1.0)))
    pt_size = max(2.0, float(getattr(prefs, "selected_vertex_size", 6.0)) * px_scale)

    try:
        shader = gpu.shader.from_builtin("POINT_UNIFORM_COLOR")
    except ValueError:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_mask_set(False)
        gpu.state.depth_test_set("NONE" if show_through else "LESS_EQUAL")
        if pts:
            gpu.state.point_size_set(pt_size)
            shader.bind()
            shader.uniform_float("color", sel_rgba)
            batch_for_shader(shader, "POINTS", {"pos": pts}).draw(shader)
        if active_pt is not None:
            gpu.state.point_size_set(pt_size + px_scale)
            shader.bind()
            shader.uniform_float("color", act_rgba)
            batch_for_shader(shader, "POINTS", {"pos": [active_pt]}).draw(shader)
    finally:
        gpu.state.point_size_set(1.0)
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set("NONE")


def collect_selected_wireframe_meshes(context) -> list[tuple[bpy.types.Object, bool]]:
    """Return selected visible Mesh objects in Object Mode ordered [(obj, is_active)], active last."""
    if getattr(context, "mode", "") != "OBJECT":
        return []
    if not bool(getattr(get_prefs(context), "maya_selected_wireframe", True)):
        return []
    space = getattr(context, "space_data", None)
    if space is not None:
        if not getattr(space.overlay, "show_overlays", True):
            return []
        if getattr(space.shading, "type", "SOLID") == "WIREFRAME":
            return []

    selected = getattr(context, "selected_objects", ()) or ()
    active = getattr(context, "active_object", None)
    secondary: list[tuple[bpy.types.Object, bool]] = []
    active_entry: list[tuple[bpy.types.Object, bool]] = []

    for obj in selected:
        if (
            obj is None
            or obj.type != "MESH"
            or obj.data is None
            or obj.hide_viewport
            or obj.display_type in {"WIRE", "BOUNDS"}
        ):
            continue
        try:
            if not obj.visible_get():
                continue
        except Exception:
            pass
        if obj == active:
            active_entry.append((obj, True))
        else:
            secondary.append((obj, False))

    return secondary + active_entry


def extract_mesh_wireframe_arrays(
    obj: bpy.types.Object, depsgraph=None
) -> tuple[np.ndarray, np.ndarray] | None:
    """Extract (verts_float32, edge_indices_int32) for a Mesh object without mutating scene data."""
    if obj is None or obj.type != "MESH" or obj.data is None:
        return None

    use_eval = len(obj.modifiers) > 0 and depsgraph is not None
    ev_obj = None
    me = None
    try:
        if use_eval:
            ev_obj = obj.evaluated_get(depsgraph)
            me = ev_obj.to_mesh()
        else:
            me = obj.data

        if me is None:
            return None
        nv = len(me.vertices)
        ne = len(me.edges)
        if nv == 0 or ne == 0 or ne > _MAX_SELECTED_WIRE_EDGES:
            return None

        verts = np.empty(nv * 3, dtype=np.float32)
        me.vertices.foreach_get("co", verts)
        verts = verts.reshape((nv, 3))

        edges = np.empty(ne * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", edges)
        edges = edges.reshape((ne, 2))
        return verts, edges
    finally:
        if ev_obj is not None:
            ev_obj.to_mesh_clear()


def _get_selected_wire_batch(obj: bpy.types.Object, depsgraph, shader, shader_name: str):
    key = (_SELECTED_WIRE_CACHE_GEN, obj.data.as_pointer(), len(obj.modifiers), shader_name)
    ptr = obj.as_pointer()
    cached = _SELECTED_WIRE_CACHE.get(ptr)
    if cached is not None and cached[0] == key:
        return cached[1]

    arrays = extract_mesh_wireframe_arrays(obj, depsgraph)
    if arrays is None:
        return None
    verts, edges = arrays
    batch = batch_for_shader(shader, "LINES", {"pos": verts}, indices=edges)
    if len(_SELECTED_WIRE_CACHE) > 256:
        _SELECTED_WIRE_CACHE.clear()
    _SELECTED_WIRE_CACHE[ptr] = (key, batch)
    return batch


def _biased_projection_matrix(
    proj: Matrix, persp_bias: float = 2.0e-3, ortho_bias: float = 2.0e-5
) -> Matrix:
    """Pull wireframe depth slightly toward camera without z-fighting or back-face bleed-through.

    In Perspective (`proj[3][2] != 0`), dividing `proj[2][3]` by `(1 - persp_bias)` is
    algebraically equivalent to pulling every vertex `persp_bias` (0.2%) closer along its exact
    eye ray: 0.0 px screen shift, independent of `clip_start`, and occluded faces stay behind.
    In Orthographic (`proj[3][2] == 0`), depth is linear so subtracting `ortho_bias` from
    `proj[2][3]` gives a small constant depth offset.
    """
    biased = proj.copy()
    if abs(float(biased[3][2])) > 1e-6:
        biased[2][3] = float(biased[2][3]) / (1.0 - persp_bias)
    else:
        biased[2][3] = float(biased[2][3]) - ortho_bias
    return biased


def _draw_selected_object_wireframe_overlay():
    """Draw wireframe divisions on selected Mesh objects in Shaded views (hidden when deselected)."""
    if bpy.app.background:
        return
    ctx = bpy.context
    targets = collect_selected_wireframe_meshes(ctx)
    if not targets:
        return
    space = getattr(ctx, "space_data", None)
    if space is None:
        return

    show_xray = bool(getattr(space.shading, "show_xray", False))
    try:
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        shader_name = "POLYLINE"
    except ValueError:
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        shader_name = "UNIFORM"

    v3d = ctx.preferences.themes[0].view_3d
    act_rgb = tuple(float(c) for c in v3d.object_active[:3])
    sel_rgb = tuple(float(c) for c in v3d.object_selected[:3])
    alpha_act = 0.60 if show_xray else 0.95
    alpha_sel = 0.55 if show_xray else 0.90
    px_scale = max(1.0, float(getattr(ctx.preferences.system, "pixel_size", 1.0)))
    line_w = 1.15 * px_scale
    depsgraph = ctx.evaluated_depsgraph_get()

    try:
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_mask_set(False)
        gpu.state.depth_test_set("NONE" if show_xray else "LESS_EQUAL")
        with gpu.matrix.push_pop_projection():
            if not show_xray:
                gpu.matrix.load_projection_matrix(
                    _biased_projection_matrix(gpu.matrix.get_projection_matrix())
                )
            shader.bind()
            if shader_name == "POLYLINE":
                vp = gpu.state.viewport_get()
                shader.uniform_float("viewportSize", (float(vp[2]), float(vp[3])))
                shader.uniform_float("lineWidth", line_w)
            else:
                gpu.state.line_width_set(line_w)

            for obj, is_active in targets:
                batch = _get_selected_wire_batch(obj, depsgraph, shader, shader_name)
                if batch is None:
                    continue
                rgba = (
                    (act_rgb[0], act_rgb[1], act_rgb[2], alpha_act)
                    if is_active
                    else (sel_rgb[0], sel_rgb[1], sel_rgb[2], alpha_sel)
                )
                shader.uniform_float("color", rgba)
                with gpu.matrix.push_pop():
                    gpu.matrix.multiply_matrix(obj.matrix_world)
                    batch.draw(shader)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set("NONE")


def is_ortho_component_view(context) -> bool:
    """True when Edit Mesh is active in an Orthographic viewport with ortho_select_through enabled."""
    if getattr(context, "mode", "") != "EDIT_MESH":
        return False
    if not bool(getattr(get_prefs(context), "ortho_select_through", True)):
        return False
    rv3d = getattr(context, "region_data", None)
    return getattr(rv3d, "view_perspective", "PERSP") == "ORTHO"


def segment_intersects_rect(
    x0: float, y0: float, x1: float, y1: float, xmin: float, ymin: float, xmax: float, ymax: float
) -> bool:
    """Return True if 2D segment (x0,y0)-(x1,y1) intersects [xmin,xmax] x [ymin,ymax] (Liang-Barsky)."""
    dx = x1 - x0
    dy = y1 - y0
    t0 = 0.0
    t1 = 1.0
    for p, q in (
        (-dx, x0 - xmin),
        (dx, xmax - x0),
        (-dy, y0 - ymin),
        (dy, ymax - y0),
    ):
        if abs(p) <= 1e-12:
            if q < 0.0:
                return False
        else:
            r = q / p
            if p < 0.0:
                if r > t1:
                    return False
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return False
                if r < t1:
                    t1 = r
    return t0 <= t1


def point_to_segment_dist_2d(px: float, py: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """Shortest Euclidean distance from 2D point (px, py) to segment (x0,y0)-(x1,y1)."""
    vx = x1 - x0
    vy = y1 - y0
    len2 = vx * vx + vy * vy
    if len2 <= 1e-12:
        return hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * vx + (py - y0) * vy) / len2))
    return hypot(px - (x0 + t * vx), py - (y0 + t * vy))


def pick_stacked_indices_2d(
    candidates,
    mouse_xy: tuple[float, float],
    hit_radius_px: float = 10.0,
    stack_tol_px: float = 4.0,
) -> list:
    """Return all front+back stacked candidates overlapping the closest hit under mouse_xy."""
    mx, my = mouse_xy
    in_radius = []
    for item, px, py, depth in candidates:
        dist = hypot(px - mx, py - my)
        if dist <= hit_radius_px:
            in_radius.append((item, float(px), float(py), float(depth), dist))
    if not in_radius:
        return []
    _item, ref_x, ref_y, _depth, _dist = min(in_radius, key=lambda c: (c[4], c[3]))
    return [item for item, px, py, _d, _md in in_radius if hypot(px - ref_x, py - ref_y) <= stack_tol_px]


def apply_ortho_box_selection(
    objs: list[bpy.types.Object],
    select_mode: tuple[bool, bool, bool],
    hits_by_obj: dict[bpy.types.Object, tuple[set[int], set[int], set[int]]],
    mode: str = "SET",
):
    """Apply SET/ADD/SUB selection across Vert/Edge/Face hits for orthographic select-through."""
    v_mode, e_mode, f_mode = select_mode
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        v_hits, e_hits, f_hits = hits_by_obj.get(obj, (set(), set(), set()))

        if mode == "SET":
            for grp in (bm.verts, bm.edges, bm.faces):
                for el in grp:
                    el.select = False
            for idx in (v_hits if v_mode else ()):
                bm.verts[idx].select_set(True)
            for idx in (e_hits if e_mode else ()):
                bm.edges[idx].select_set(True)
            for idx in (f_hits if f_mode else ()):
                bm.faces[idx].select_set(True)
        elif mode == "ADD":
            for idx in (v_hits if v_mode else ()):
                bm.verts[idx].select_set(True)
            for idx in (e_hits if e_mode else ()):
                bm.edges[idx].select_set(True)
            for idx in (f_hits if f_mode else ()):
                bm.faces[idx].select_set(True)
        else:
            for idx in (v_hits if v_mode else ()):
                bm.verts[idx].select_set(False)
            for idx in (e_hits if e_mode else ()):
                bm.edges[idx].select_set(False)
            for idx in (f_hits if f_mode else ()):
                bm.faces[idx].select_set(False)

        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def select_mesh_components_in_rect(
    context,
    objs: list[bpy.types.Object],
    rect_xy: tuple[float, float, float, float],
    mode: str = "SET",
):
    """Project all non-hidden Verts/Edges/Faces (front & hidden back) and select those inside rect_xy."""
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    if region is None or rv3d is None:
        return
    xmin, ymin, xmax, ymax = rect_xy
    select_mode = tuple(bool(x) for x in context.tool_settings.mesh_select_mode)
    v_mode, e_mode, f_mode = select_mode
    hits_by_obj: dict[bpy.types.Object, tuple[set[int], set[int], set[int]]] = {}

    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        mat_world = obj.matrix_world

        vert_2d: dict[int, tuple[float, float]] = {}
        for v in bm.verts:
            if v.hide:
                continue
            pt = view3d_utils.location_3d_to_region_2d(region, rv3d, mat_world @ v.co)
            if pt is not None:
                vert_2d[v.index] = (float(pt.x), float(pt.y))

        v_hits: set[int] = set()
        e_hits: set[int] = set()
        f_hits: set[int] = set()

        if v_mode:
            for idx, (px, py) in vert_2d.items():
                if xmin <= px <= xmax and ymin <= py <= ymax:
                    v_hits.add(idx)

        if e_mode:
            for e in bm.edges:
                if e.hide:
                    continue
                p0 = vert_2d.get(e.verts[0].index)
                p1 = vert_2d.get(e.verts[1].index)
                if p0 is None or p1 is None:
                    continue
                if segment_intersects_rect(p0[0], p0[1], p1[0], p1[1], xmin, ymin, xmax, ymax):
                    e_hits.add(e.index)

        if f_mode:
            for f in bm.faces:
                if f.hide:
                    continue
                pt = view3d_utils.location_3d_to_region_2d(region, rv3d, mat_world @ f.calc_center_median())
                if pt is not None and xmin <= pt.x <= xmax and ymin <= pt.y <= ymax:
                    f_hits.add(f.index)

        hits_by_obj[obj] = (v_hits, e_hits, f_hits)

    apply_ortho_box_selection(objs, select_mode, hits_by_obj, mode=mode)


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


def apply_face_center_selection_multi(
    objs,
    hits: list[tuple[bpy.types.Object, int]],
    *,
    toggle: bool = False,
    deselect: bool = False,
):
    """Apply plain/toggle/deselect face selection across one or more (obj, face_index) hits."""
    bm_map = {obj: bmesh.from_edit_mesh(obj.data) for obj in objs}
    for bm in bm_map.values():
        bm.faces.ensure_lookup_table()

    valid_hits = []
    for hit_obj, hit_idx in hits:
        hit_bm = bm_map.get(hit_obj)
        if hit_bm is not None and 0 <= hit_idx < len(hit_bm.faces):
            valid_hits.append((hit_bm, hit_bm.faces[hit_idx]))

    if not valid_hits:
        if not toggle and not deselect:
            for obj, bm in bm_map.items():
                for f in bm.faces:
                    f.select_set(False)
                bm.faces.active = None
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return

    if not toggle and not deselect:
        for bm in bm_map.values():
            for f in bm.faces:
                f.select_set(False)
            bm.faces.active = None
        for hit_bm, hit_face in valid_hits:
            hit_face.select_set(True)
            hit_bm.faces.active = hit_face
    elif toggle:
        target_state = not all(f.select for _bm, f in valid_hits)
        for hit_bm, hit_face in valid_hits:
            hit_face.select_set(target_state)
            if target_state:
                hit_bm.faces.active = hit_face
    else:
        for _bm, hit_face in valid_hits:
            hit_face.select_set(False)

    for obj, bm in bm_map.items():
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def apply_face_center_selection(
    objs,
    hit: tuple[bpy.types.Object, int] | None,
    *,
    toggle: bool = False,
    deselect: bool = False,
):
    """Apply plain/toggle/deselect face selection using (obj, face_index) with live BMesh wrappers."""
    apply_face_center_selection_multi(objs, [hit] if hit is not None else [], toggle=toggle, deselect=deselect)


def _pick_ortho_face_centers(context, mouse_xy: tuple[float, float], hit_radius_px: float = 10.0):
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    if region is None or rv3d is None:
        return []
    objs = _get_edit_mesh_objects(context)
    candidates = []
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        mat_world = obj.matrix_world
        for face in bm.faces:
            if face.hide:
                continue
            world_center = mat_world @ face.calc_center_median()
            pt2d = view3d_utils.location_3d_to_region_2d(region, rv3d, world_center)
            if pt2d is None:
                continue
            depth = -(rv3d.view_matrix @ world_center).z
            candidates.append(((obj, face.index), float(pt2d.x), float(pt2d.y), float(depth)))
    return pick_stacked_indices_2d(candidates, mouse_xy, hit_radius_px=hit_radius_px)


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
        objs = _get_edit_mesh_objects(context)

        if is_ortho_component_view(context):
            hits = _pick_ortho_face_centers(context, mouse_xy, hit_radius_px=radius)
            apply_face_center_selection_multi(objs, hits, toggle=self.toggle, deselect=self.deselect)
        else:
            hit = pick_face_by_center(context, mouse_xy, hit_radius_px=radius)
            apply_face_center_selection(objs, hit, toggle=self.toggle, deselect=self.deselect)

        from . import ops_extrude

        if ops_extrude.is_extrude_session_active():
            ops_extrude.end_extrude_session(context, restore_tool=True)
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
        sync_component_selection_display(context, force=True)
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
    state_matches_sel = (
        state is not None
        and state.get("edge_count") == len(bm.edges)
        and state.get("all_selected") == cur_sel
    )

    target: frozenset[int] | None = None

    if extend:
        if state_matches_sel and state.get("extend") is True:
            loops = list(state.get("loops", (cur_sel,)))
            extend_dir = state.get("extend_dir")
            last_popped = state.get("last_popped")
            last_popped_dir = state.get("last_popped_dir")

            if len(loops) > 1 and extend_dir is not None and direction != extend_dir:
                popped = loops.pop()
                new_sel = frozenset().union(*loops)
                _PICKWALK_STATE[obj.name] = {
                    "edge_count": len(bm.edges),
                    "all_selected": new_sel,
                    "extend": True,
                    "loops": loops,
                    "extend_dir": extend_dir if len(loops) > 1 else None,
                    "last_popped": popped if len(loops) == 1 else None,
                    "last_popped_dir": extend_dir if len(loops) == 1 else None,
                }
            elif len(loops) > 1:
                frontier = loops[-1]
                prev = loops[-2]
                sides = compute_parallel_edge_loops(bm, set(frontier))
                candidates = [s for s in sides if not (s & prev) and not (s <= cur_sel)]
                if not candidates:
                    return False
                target = (
                    candidates[0]
                    if len(candidates) == 1
                    else _rank_sides_for_direction(context, bm, obj.matrix_world, set(frontier), candidates, direction)
                )
                if target is None:
                    return False
                loops.append(target)
                new_sel = frozenset(cur_sel | target)
                _PICKWALK_STATE[obj.name] = {
                    "edge_count": len(bm.edges),
                    "all_selected": new_sel,
                    "extend": True,
                    "loops": loops,
                    "extend_dir": direction,
                    "last_popped": None,
                    "last_popped_dir": None,
                }
            else:
                anchor = loops[0]
                sides = compute_parallel_edge_loops(bm, set(anchor))
                if not sides:
                    return False
                if last_popped is not None and last_popped_dir is not None:
                    if direction == last_popped_dir:
                        chosen = [s for s in sides if s & last_popped]
                    else:
                        chosen = [s for s in sides if not (s & last_popped)]
                    target = (
                        chosen[0]
                        if len(chosen) == 1
                        else _rank_sides_for_direction(context, bm, obj.matrix_world, set(anchor), chosen or sides, direction)
                    )
                else:
                    target = _rank_sides_for_direction(context, bm, obj.matrix_world, set(anchor), sides, direction)
                if target is None:
                    return False
                loops = [anchor, target]
                new_sel = frozenset(anchor | target)
                _PICKWALK_STATE[obj.name] = {
                    "edge_count": len(bm.edges),
                    "all_selected": new_sel,
                    "extend": True,
                    "loops": loops,
                    "extend_dir": direction,
                    "last_popped": None,
                    "last_popped_dir": None,
                }
        else:
            sides = compute_parallel_edge_loops(bm, set(cur_sel))
            if not sides:
                return False
            if state_matches_sel and state.get("extend") is False:
                prev = set(state["prev_loop"])
                if direction == state["last_dir"]:
                    candidates = [s for s in sides if not (s & prev)] or sides
                else:
                    candidates = [s for s in sides if s & prev] or sides
                target = (
                    candidates[0]
                    if len(candidates) == 1
                    else _rank_sides_for_direction(context, bm, obj.matrix_world, set(cur_sel), candidates, direction)
                )
            else:
                target = _rank_sides_for_direction(context, bm, obj.matrix_world, set(cur_sel), sides, direction)
            if target is None:
                return False
            new_sel = frozenset(cur_sel | target)
            _PICKWALK_STATE[obj.name] = {
                "edge_count": len(bm.edges),
                "all_selected": new_sel,
                "extend": True,
                "loops": [cur_sel, target],
                "extend_dir": direction,
                "last_popped": None,
                "last_popped_dir": None,
            }
    elif state_matches_sel and state.get("extend") is False:
        frontier = set(state["frontier"])
        prev = set(state["prev_loop"])
        sides = compute_parallel_edge_loops(bm, frontier)
        if not sides:
            return False
        if direction == state["last_dir"]:
            candidates = [s for s in sides if not (s & prev)]
            if not candidates:
                return False
            target = (
                candidates[0]
                if len(candidates) == 1
                else _rank_sides_for_direction(context, bm, obj.matrix_world, frontier, candidates, direction)
            )
        else:
            back_sides = [s for s in sides if s & prev]
            target = (
                back_sides[0]
                if back_sides
                else _rank_sides_for_direction(context, bm, obj.matrix_world, frontier, sides, direction)
            )
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


class MAYA_UX_OT_ortho_select_box(bpy.types.Operator):
    """Box select both front and hidden back mesh components in Orthographic views."""

    bl_idname = "maya_ux.ortho_select_box"
    bl_label = "Maya Ortho Box Select (Select-Through)"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Mode",
        items=[
            ("SET", "Set", "Set new selection"),
            ("ADD", "Add", "Extend selection"),
            ("SUB", "Subtract", "Subtract from selection"),
        ],
        default="SET",
    )

    _draw_handle = None
    _region = None
    _start_x: float = 0.0
    _start_y: float = 0.0
    _cur_x: float = 0.0
    _cur_y: float = 0.0

    def _draw_marquee(self):
        if bpy.context.region != self._region:
            return
        x0, y0 = self._start_x, self._start_y
        x1, y1 = self._cur_x, self._cur_y
        xmin, xmax = min(x0, x1), max(x0, x1)
        ymin, ymax = min(y0, y1), max(y0, y1)

        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")

        fill_verts = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
        fill_batch = batch_for_shader(shader, "TRIS", {"pos": fill_verts}, indices=[(0, 1, 2), (0, 2, 3)])
        shader.bind()
        shader.uniform_float("color", (0.28, 0.56, 0.90, 0.16))
        fill_batch.draw(shader)

        border_verts = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)]
        border_batch = batch_for_shader(shader, "LINE_STRIP", {"pos": border_verts})
        shader.uniform_float("color", (0.85, 0.92, 1.0, 0.85))
        border_batch.draw(shader)
        gpu.state.blend_set("NONE")

    def _cleanup(self):
        if self._draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        if self._region is not None:
            self._region.tag_redraw()

    def invoke(self, context, event):
        if not is_ortho_component_view(context):
            return {"PASS_THROUGH"}
        region = getattr(context, "region", None)
        rv3d = getattr(context, "region_data", None)
        if region is None or rv3d is None:
            return {"PASS_THROUGH"}

        self._region = region
        px = getattr(event, "mouse_prev_press_x", None)
        py = getattr(event, "mouse_prev_press_y", None)
        if (
            px is not None
            and py is not None
            and (px or py)
            and region.x <= px <= region.x + region.width
            and region.y <= py <= region.y + region.height
        ):
            self._start_x = float(px - region.x)
            self._start_y = float(py - region.y)
        else:
            self._start_x = float(event.mouse_region_x)
            self._start_y = float(event.mouse_region_y)
        self._cur_x = float(event.mouse_region_x)
        self._cur_y = float(event.mouse_region_y)

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_marquee, (), "WINDOW", "POST_PIXEL"
        )
        context.window_manager.modal_handler_add(self)
        region.tag_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "MOUSEMOVE":
            self._cur_x = float(event.mouse_region_x)
            self._cur_y = float(event.mouse_region_y)
            if self._region is not None:
                self._region.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._cur_x = float(event.mouse_region_x)
            self._cur_y = float(event.mouse_region_y)
            self._cleanup()
            rect = (
                min(self._start_x, self._cur_x),
                min(self._start_y, self._cur_y),
                max(self._start_x, self._cur_x),
                max(self._start_y, self._cur_y),
            )
            select_mesh_components_in_rect(context, _get_edit_mesh_objects(context), rect, mode=self.mode)
            from . import ops_extrude

            if ops_extrude.is_extrude_session_active():
                ops_extrude.end_extrude_session(context, restore_tool=True)
            return {"FINISHED"}

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            self._cleanup()
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}


def resolve_double_click_loop_action(
    clicked_selected: bool,
    any_neighbor_selected: bool,
    toggle: bool,
    deselect: bool,
) -> str:
    """Resolve Double-Click edge loop action ('REPLACE' | 'EXTEND' | 'DESELECT') after Click 1."""
    if deselect:
        return "DESELECT"
    if not toggle:
        return "REPLACE"
    if not clicked_selected and any_neighbor_selected:
        return "DESELECT"
    return "EXTEND"


def _step_edge_loop(vert: bmesh.types.BMVert, prev_edge: bmesh.types.BMEdge) -> bmesh.types.BMEdge | None:
    """Return the next coherent edge along a quad interior or boundary edge loop at vert."""
    if len(vert.link_edges) == 4:
        prev_faces = set(prev_edge.link_faces)
        opp = [
            e
            for e in vert.link_edges
            if e != prev_edge and not e.hide and not (set(e.link_faces) & prev_faces)
        ]
        if len(opp) == 1:
            return opp[0]
    if prev_edge.is_boundary:
        bnd = [e for e in vert.link_edges if e != prev_edge and not e.hide and e.is_boundary]
        if len(bnd) == 1:
            return bnd[0]
    return None


def collect_edge_loop_indices(bm: bmesh.types.BMesh, seed_edge: bmesh.types.BMEdge) -> set[int]:
    """Walk both ends of seed_edge to collect every edge index on its coherent edge loop."""
    loop = {seed_edge.index}
    for start_v in (seed_edge.verts[0], seed_edge.verts[1]):
        cur_v = start_v
        cur_e = seed_edge
        while True:
            nxt_e = _step_edge_loop(cur_v, cur_e)
            if nxt_e is None or nxt_e.index in loop:
                break
            loop.add(nxt_e.index)
            cur_v = nxt_e.other_vert(cur_v)
            cur_e = nxt_e
    return loop


def collect_face_loop_indices(
    bm: bmesh.types.BMesh,
    face_a: bmesh.types.BMFace,
    face_b: bmesh.types.BMFace,
) -> set[int]:
    """Walk opposite quad edges across two adjacent faces to collect their full Face Loop."""
    shared = next((e for e in face_a.edges if e in face_b.edges and not e.hide), None)
    if shared is None:
        return {face_a.index, face_b.index}

    loop = {face_a.index, face_b.index}

    def _walk(start_f: bmesh.types.BMFace, entry_e: bmesh.types.BMEdge):
        cur_f = start_f
        cur_e = entry_e
        while True:
            if cur_f.hide or len(cur_f.edges) != 4:
                break
            e_verts = set(cur_e.verts)
            opp_e = next((e for e in cur_f.edges if e != cur_e and not (set(e.verts) & e_verts)), None)
            if opp_e is None or opp_e.hide:
                break
            nbrs = [af for af in opp_e.link_faces if af != cur_f and not af.hide]
            if len(nbrs) != 1:
                break
            nxt_f = nbrs[0]
            if nxt_f.index in loop:
                break
            loop.add(nxt_f.index)
            cur_f = nxt_f
            cur_e = opp_e

    _walk(face_b, shared)
    _walk(face_a, shared)
    return loop


def _collect_linked_face_indices(seed_face: bmesh.types.BMFace) -> set[int]:
    """Flood-fill connected visible faces for Maya Double-Click Face Shell selection."""
    visited = {seed_face.index}
    stack = [seed_face]
    while stack:
        cur = stack.pop()
        for e in cur.edges:
            if e.hide:
                continue
            for af in e.link_faces:
                if not af.hide and af.index not in visited:
                    visited.add(af.index)
                    stack.append(af)
    return visited


def _collect_linked_vert_indices(seed_vert: bmesh.types.BMVert) -> set[int]:
    """Flood-fill connected visible vertices for Maya Double-Click Vertex Shell selection."""
    visited = {seed_vert.index}
    stack = [seed_vert]
    while stack:
        cur = stack.pop()
        for e in cur.link_edges:
            if e.hide:
                continue
            ov = e.other_vert(cur)
            if not ov.hide and ov.index not in visited:
                visited.add(ov.index)
                stack.append(ov)
    return visited


def _pick_face_hits_double_click(context, objs, mouse_xy: tuple[float, float], hit_radius_px: float):
    """Pick (obj, face_index) hit(s) under mouse_xy for Face Loop / Shell Double-Click."""
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    if region is None or rv3d is None:
        return []

    if is_ortho_component_view(context):
        stacked = _pick_ortho_face_centers(context, mouse_xy, hit_radius_px=max(hit_radius_px, 24.0))
        if stacked:
            return stacked

    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse_xy)
    ray_dir = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse_xy)
    depsgraph = context.evaluated_depsgraph_get()
    hit, _loc, _norm, face_idx, hit_obj, _mat = context.scene.ray_cast(depsgraph, ray_origin, ray_dir)
    if hit and hit_obj in objs and face_idx >= 0:
        return [(hit_obj, int(face_idx))]

    fb = pick_face_by_center(context, mouse_xy, hit_radius_px=max(hit_radius_px, 20.0))
    return [fb] if fb is not None else []


def _pick_vert_hits_double_click(context, objs, mouse_xy: tuple[float, float], hit_radius_px: float):
    """Pick (obj, vert_index) hit(s) under mouse_xy for Vertex Loop / Shell Double-Click."""
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    if region is None or rv3d is None:
        return []
    candidates = []
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        mw = obj.matrix_world
        for v in bm.verts:
            if v.hide:
                continue
            wc = mw @ v.co
            pt = view3d_utils.location_3d_to_region_2d(region, rv3d, wc)
            if pt is not None:
                depth = -(rv3d.view_matrix @ wc).z
                candidates.append(((obj, v.index), float(pt.x), float(pt.y), float(depth)))

    if is_ortho_component_view(context):
        ui_scale = float(getattr(context.preferences.system, "ui_scale", 1.0))
        return pick_stacked_indices_2d(candidates, mouse_xy, hit_radius_px=hit_radius_px, stack_tol_px=4.0 * ui_scale)
    mx, my = mouse_xy
    in_r = [(item, hypot(px - mx, py - my), depth) for item, px, py, depth in candidates if hypot(px - mx, py - my) <= hit_radius_px]
    return [min(in_r, key=lambda c: (c[2], c[1]))[0]] if in_r else []


def _pick_nearest_edge_candidates_2d(context, objs, mouse_xy: tuple[float, float]):
    """Project all visible mesh edges to 2D region coords for double-click loop picking."""
    region = getattr(context, "region", None)
    rv3d = getattr(context, "region_data", None)
    if region is None or rv3d is None:
        return []
    candidates = []
    for obj in objs:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        mat_world = obj.matrix_world
        for e in bm.edges:
            if e.hide:
                continue
            w0 = mat_world @ e.verts[0].co
            w1 = mat_world @ e.verts[1].co
            p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, w0)
            p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, w1)
            if p0 is None or p1 is None:
                continue
            vx, vy = float(p1.x - p0.x), float(p1.y - p0.y)
            len2 = vx * vx + vy * vy
            t = 0.5 if len2 <= 1e-12 else max(0.0, min(1.0, ((mouse_xy[0] - p0.x) * vx + (mouse_xy[1] - p0.y) * vy) / len2))
            qx = float(p0.x + t * vx)
            qy = float(p0.y + t * vy)
            depth = -(rv3d.view_matrix @ w0.lerp(w1, t)).z
            candidates.append(((obj, e.index), qx, qy, float(depth)))
    return candidates


class MAYA_UX_OT_edge_loop_double_click(bpy.types.Operator):
    """Maya-style Double-Click LMB on an Edge to select the entire Edge Loop."""

    bl_idname = "maya_ux.edge_loop_double_click"
    bl_label = "Maya Double-Click Select Edge Loop"
    bl_options = {"REGISTER", "UNDO"}

    toggle: BoolProperty(name="Toggle / Extend Loop", default=False)
    deselect: BoolProperty(name="Deselect Loop", default=False)

    def invoke(self, context, event):
        if getattr(context, "mode", "") != "EDIT_MESH":
            return {"PASS_THROUGH"}

        v_mode, e_mode, f_mode = tuple(bool(x) for x in context.tool_settings.mesh_select_mode)
        if not (v_mode or e_mode or f_mode):
            return {"PASS_THROUGH"}

        region = getattr(context, "region", None)
        rv3d = getattr(context, "region_data", None)
        if region is None or rv3d is None:
            return {"PASS_THROUGH"}

        objs = _get_edit_mesh_objects(context)
        for obj in objs:
            _PICKWALK_STATE.pop(obj.name, None)
            _EDGE_LOOP_ORIGIN.pop(obj.name, None)

        ui_scale = float(getattr(context.preferences.system, "ui_scale", 1.0))
        radius = 12.0 * ui_scale
        mouse_xy = (float(event.mouse_region_x), float(event.mouse_region_y))

        # Face Mode: Shift+Double-Click adjacent face -> Face Loop; Double-Click -> Face Shell
        if f_mode and not e_mode:
            hits = _pick_face_hits_double_click(context, objs, mouse_xy, radius)
            if not hits:
                return {"FINISHED"}
            bm_map = {obj: bmesh.from_edit_mesh(obj.data) for obj in objs}
            for bm in bm_map.values():
                bm.faces.ensure_lookup_table()
            for obj, face_idx in hits:
                bm = bm_map.get(obj)
                if bm is None or not (0 <= face_idx < len(bm.faces)):
                    continue
                clicked_f = bm.faces[face_idx]
                seed_f = None
                if self.toggle:
                    act = bm.select_history.active
                    if isinstance(act, bmesh.types.BMFace) and act.is_valid and act != clicked_f and act.select:
                        if any(e in clicked_f.edges for e in act.edges):
                            seed_f = act
                    if seed_f is None:
                        seed_f = next(
                            (af for e in clicked_f.edges for af in e.link_faces if af != clicked_f and not af.hide and af.select),
                            None,
                        )
                target_faces = (
                    collect_face_loop_indices(bm, seed_f, clicked_f)
                    if seed_f is not None
                    else _collect_linked_face_indices(clicked_f)
                )
                if self.deselect:
                    for idx in target_faces:
                        bm.faces[idx].select_set(False)
                elif not self.toggle:
                    for grp in (bm.verts, bm.edges, bm.faces):
                        for el in grp:
                            el.select = False
                    for idx in target_faces:
                        bm.faces[idx].select_set(True)
                else:
                    others_all_sel = all(bm.faces[idx].select for idx in target_faces if idx != face_idx)
                    state = False if (not clicked_f.select and others_all_sel and len(target_faces) > 1) else True
                    for idx in target_faces:
                        bm.faces[idx].select_set(state)

            for obj, bm in bm_map.items():
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            from . import ops_extrude

            if ops_extrude.is_extrude_session_active():
                ops_extrude.end_extrude_session(context, restore_tool=True)
            return {"FINISHED"}

        # Vertex Mode: Shift+Double-Click adjacent vertex -> Vertex Loop; Double-Click -> Vertex Shell
        if v_mode and not e_mode and not f_mode:
            hits = _pick_vert_hits_double_click(context, objs, mouse_xy, radius)
            if not hits:
                return {"FINISHED"}
            bm_map = {obj: bmesh.from_edit_mesh(obj.data) for obj in objs}
            for bm in bm_map.values():
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
            for obj, v_idx in hits:
                bm = bm_map.get(obj)
                if bm is None or not (0 <= v_idx < len(bm.verts)):
                    continue
                clicked_v = bm.verts[v_idx]
                adj_e = None
                if self.toggle:
                    adj_e = next(
                        (e for e in clicked_v.link_edges if not e.hide and e.other_vert(clicked_v).select),
                        None,
                    )
                if adj_e is not None:
                    loop_es = collect_edge_loop_indices(bm, adj_e)
                    target_verts = {v.index for ei in loop_es for v in bm.edges[ei].verts}
                else:
                    target_verts = _collect_linked_vert_indices(clicked_v)

                if self.deselect:
                    for idx in target_verts:
                        bm.verts[idx].select_set(False)
                elif not self.toggle:
                    for grp in (bm.verts, bm.edges, bm.faces):
                        for el in grp:
                            el.select = False
                    for idx in target_verts:
                        bm.verts[idx].select_set(True)
                else:
                    others_all_sel = all(bm.verts[idx].select for idx in target_verts if idx != v_idx)
                    state = False if (not clicked_v.select and others_all_sel and len(target_verts) > 1) else True
                    for idx in target_verts:
                        bm.verts[idx].select_set(state)

            for obj, bm in bm_map.items():
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            from . import ops_extrude

            if ops_extrude.is_extrude_session_active():
                ops_extrude.end_extrude_session(context, restore_tool=True)
            return {"FINISHED"}

        # Edge / Multi-Component Mode: Edge Loop selection
        candidates = _pick_nearest_edge_candidates_2d(context, objs, mouse_xy)

        if is_ortho_component_view(context):
            hits = pick_stacked_indices_2d(candidates, mouse_xy, hit_radius_px=radius, stack_tol_px=4.0 * ui_scale)
            if not hits:
                return {"FINISHED"}
            bm_map = {obj: bmesh.from_edit_mesh(obj.data) for obj in objs}
            for bm in bm_map.values():
                bm.edges.ensure_lookup_table()

            hit_groups = []
            for obj, edge_idx in hits:
                bm = bm_map.get(obj)
                if bm is None or not (0 <= edge_idx < len(bm.edges)):
                    continue
                seed = bm.edges[edge_idx]
                loop_indices = collect_edge_loop_indices(bm, seed)
                any_nbr_sel = any(bm.edges[idx].select for idx in loop_indices if idx != edge_idx)
                hit_groups.append((obj, bm, seed.select, any_nbr_sel, loop_indices))

            if not hit_groups:
                return {"FINISHED"}

            any_clicked = any(cs for _, _, cs, _, _ in hit_groups)
            any_nbr = any(ns for _, _, _, ns, _ in hit_groups)
            action = resolve_double_click_loop_action(any_clicked, any_nbr, self.toggle, self.deselect)

            if action == "REPLACE":
                for bm in bm_map.values():
                    for grp in (bm.verts, bm.edges, bm.faces):
                        for el in grp:
                            el.select = False
                for _obj, bm, _cs, _ns, loop_indices in hit_groups:
                    for idx in loop_indices:
                        bm.edges[idx].select_set(True)
            elif action == "EXTEND":
                for _obj, bm, _cs, _ns, loop_indices in hit_groups:
                    for idx in loop_indices:
                        bm.edges[idx].select_set(True)
            else:
                for _obj, bm, _cs, _ns, loop_indices in hit_groups:
                    for idx in loop_indices:
                        bm.edges[idx].select_set(False)

            for obj, bm in bm_map.items():
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        else:
            if self.deselect:
                action = "DESELECT"
            elif not self.toggle:
                action = "REPLACE"
            else:
                mx, my = mouse_xy
                in_r = [(item, hypot(px - mx, py - my), depth) for item, px, py, depth in candidates if hypot(px - mx, py - my) <= radius]
                if not in_r:
                    return {"FINISHED"}
                hit_obj, edge_idx = min(in_r, key=lambda c: (c[2], c[1]))[0]
                bm = bmesh.from_edit_mesh(hit_obj.data)
                bm.edges.ensure_lookup_table()
                seed = bm.edges[edge_idx]
                loop_indices = collect_edge_loop_indices(bm, seed)
                any_nbr_sel = any(bm.edges[idx].select for idx in loop_indices if idx != edge_idx)
                action = resolve_double_click_loop_action(seed.select, any_nbr_sel, True, False)

            try:
                bpy.ops.mesh.loop_select(
                    "INVOKE_DEFAULT",
                    extend=(action == "EXTEND"),
                    deselect=(action == "DESELECT"),
                    toggle=False,
                )
            except (TypeError, RuntimeError):
                return {"PASS_THROUGH"}

        from . import ops_extrude

        if ops_extrude.is_extrude_session_active():
            ops_extrude.end_extrude_session(context, restore_tool=True)
        return {"FINISHED"}


class MAYA_UX_OT_ortho_select_click(bpy.types.Operator):
    """Click select stacked front and hidden back components in Orthographic views."""

    bl_idname = "maya_ux.ortho_select_click"
    bl_label = "Maya Ortho Click Select (Select-Through)"
    bl_options = {"REGISTER", "UNDO"}

    toggle: BoolProperty(name="Toggle", default=False)
    deselect: BoolProperty(name="Deselect", default=False)

    def invoke(self, context, event):
        if not is_ortho_component_view(context):
            return {"PASS_THROUGH"}
        select_mode = tuple(bool(x) for x in context.tool_settings.mesh_select_mode)
        prefs = get_prefs(context)
        if select_mode == (False, False, True) and bool(getattr(prefs, "maya_face_center_select", True)):
            return {"PASS_THROUGH"}

        region = getattr(context, "region", None)
        rv3d = getattr(context, "region_data", None)
        if region is None or rv3d is None:
            return {"PASS_THROUGH"}

        ui_scale = float(getattr(context.preferences.system, "ui_scale", 1.0))
        radius = 12.0 * ui_scale
        mouse_xy = (float(event.mouse_region_x), float(event.mouse_region_y))
        objs = _get_edit_mesh_objects(context)
        v_mode, e_mode, f_mode = select_mode

        candidates = []
        for obj in objs:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            mat_world = obj.matrix_world

            if v_mode:
                for v in bm.verts:
                    if v.hide:
                        continue
                    wc = mat_world @ v.co
                    pt = view3d_utils.location_3d_to_region_2d(region, rv3d, wc)
                    if pt is not None:
                        depth = -(rv3d.view_matrix @ wc).z
                        candidates.append(((obj, "verts", v.index), float(pt.x), float(pt.y), float(depth)))

            if e_mode:
                for e in bm.edges:
                    if e.hide:
                        continue
                    w0 = mat_world @ e.verts[0].co
                    w1 = mat_world @ e.verts[1].co
                    p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, w0)
                    p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, w1)
                    if p0 is None or p1 is None:
                        continue
                    vx, vy = float(p1.x - p0.x), float(p1.y - p0.y)
                    len2 = vx * vx + vy * vy
                    t = 0.5 if len2 <= 1e-12 else max(0.0, min(1.0, ((mouse_xy[0] - p0.x) * vx + (mouse_xy[1] - p0.y) * vy) / len2))
                    qx = float(p0.x + t * vx)
                    qy = float(p0.y + t * vy)
                    depth = -(rv3d.view_matrix @ w0.lerp(w1, t)).z
                    candidates.append(((obj, "edges", e.index), qx, qy, float(depth)))

            if f_mode:
                for f in bm.faces:
                    if f.hide:
                        continue
                    wc = mat_world @ f.calc_center_median()
                    pt = view3d_utils.location_3d_to_region_2d(region, rv3d, wc)
                    if pt is not None:
                        depth = -(rv3d.view_matrix @ wc).z
                        candidates.append(((obj, "faces", f.index), float(pt.x), float(pt.y), float(depth)))

        stacked = pick_stacked_indices_2d(candidates, mouse_xy, hit_radius_px=radius, stack_tol_px=4.0 * ui_scale)
        bm_map = {obj: bmesh.from_edit_mesh(obj.data) for obj in objs}
        for bm in bm_map.values():
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

        if not stacked:
            if not self.toggle and not self.deselect:
                for obj, bm in bm_map.items():
                    for grp in (bm.verts, bm.edges, bm.faces):
                        for el in grp:
                            el.select = False
                    bm.select_flush_mode()
                    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            from . import ops_extrude

            if ops_extrude.is_extrude_session_active():
                ops_extrude.end_extrude_session(context, restore_tool=True)
            return {"FINISHED"}

        resolved_els = [(obj, bm_map[obj], getattr(bm_map[obj], kind)[idx]) for obj, kind, idx in stacked if obj in bm_map]
        if not self.toggle and not self.deselect:
            for bm in bm_map.values():
                for grp in (bm.verts, bm.edges, bm.faces):
                    for el in grp:
                        el.select = False
            for _obj, _bm, el in resolved_els:
                el.select_set(True)
        elif self.toggle:
            target_state = not all(el.select for _obj, _bm, el in resolved_els)
            for _obj, _bm, el in resolved_els:
                el.select_set(target_state)
        else:
            for _obj, _bm, el in resolved_els:
                el.select_set(False)

        for obj, bm in bm_map.items():
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        from . import ops_extrude

        if ops_extrude.is_extrude_session_active():
            ops_extrude.end_extrude_session(context, restore_tool=True)
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_select_face_center,
    MAYA_UX_OT_convert_selection,
    MAYA_UX_OT_pick_walk,
    MAYA_UX_OT_toggle_soft_select,
    MAYA_UX_OT_soft_select_radius,
    MAYA_UX_OT_smart_delete,
    MAYA_UX_OT_grow_shrink_selection,
    MAYA_UX_OT_ortho_select_box,
    MAYA_UX_OT_edge_loop_double_click,
    MAYA_UX_OT_ortho_select_click,
)


def register():
    global _SELECTED_VERT_DRAW_HANDLE, _SELECTED_WIRE_DRAW_HANDLE
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    sync_face_center_overlay(bool(getattr(get_prefs(), "maya_face_center_select", True)))
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.ToolSettings, "mesh_select_mode"),
        owner=_MSGBUS_OWNER,
        args=(),
        notify=lambda: sync_component_selection_display(force=True),
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=_MSGBUS_OWNER,
        args=(),
        notify=lambda: sync_component_selection_display(force=True),
    )
    if _on_component_display_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_component_display_depsgraph)
    if _on_load_pre_selection_cache not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre_selection_cache)
    if _SELECTED_VERT_DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_SELECTED_VERT_DRAW_HANDLE, "WINDOW")
    _SELECTED_VERT_DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
        _draw_selected_vertices_overlay, (), "WINDOW", "POST_VIEW"
    )
    if _SELECTED_WIRE_DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_SELECTED_WIRE_DRAW_HANDLE, "WINDOW")
    _SELECTED_WIRE_DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
        _draw_selected_object_wireframe_overlay, (), "WINDOW", "POST_VIEW"
    )
    sync_component_selection_display(force=True)


def unregister():
    global _SELECTED_VERT_DRAW_HANDLE, _SELECTED_WIRE_DRAW_HANDLE
    if _SELECTED_WIRE_DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_SELECTED_WIRE_DRAW_HANDLE, "WINDOW")
        _SELECTED_WIRE_DRAW_HANDLE = None
    if _SELECTED_VERT_DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_SELECTED_VERT_DRAW_HANDLE, "WINDOW")
        _SELECTED_VERT_DRAW_HANDLE = None
    bpy.msgbus.clear_by_owner(_MSGBUS_OWNER)
    if _on_load_pre_selection_cache in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre_selection_cache)
    if _on_component_display_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_component_display_depsgraph)
    invalidate_selected_wireframe_cache()
    restore_component_selection_display()
    _SAVED_COMPONENT_COLORS.clear()
    sync_face_center_overlay(False)
    _PREV_FACE_CENTER.clear()
    _GROW_HISTORY.clear()
    _PICKWALK_STATE.clear()
    _EDGE_LOOP_ORIGIN.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
