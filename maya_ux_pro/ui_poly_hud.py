from __future__ import annotations

import time

import bmesh
import blf
import bpy
from bpy.app.handlers import persistent

from .ops_smooth import SMOOTH_MOD_NAME
from .preferences import get_prefs

_HUD_HANDLE = None
_PREV_SHOW_TEXT: dict[int, bool] = {}
_STATS_DIRTY: bool = True
_CACHE_KEY: tuple | None = None
_CACHE_TIME: float = 0.0
_CACHE_STATS: dict = {
    "verts": (0, 0, 0),
    "edges": (0, 0, 0),
    "faces": (0, 0, 0),
    "tris": (0, 0, 0),
    "uvs": (0, 0, 0),
    "subdiv_level": 0,
    "subdiv_mode": "Standard",
}

_LABEL_COLOR = (0.38, 0.80, 0.44, 0.96)
_VALUE_COLOR = (0.95, 0.96, 0.98, 0.98)


def _active_subdiv_info(obj) -> tuple[int, str]:
    if obj is None or obj.type != "MESH":
        return (0, "Standard")

    smooth_mod = obj.modifiers.get(SMOOTH_MOD_NAME)
    if smooth_mod is not None:
        if not smooth_mod.show_viewport:
            return (0, "Rough (1)")
        if getattr(smooth_mod, "show_on_cage", False):
            return (int(smooth_mod.levels), "Smooth (3)")
        return (int(smooth_mod.levels), "Cage (2)")

    for mod in obj.modifiers:
        if mod.type == "SUBSURF":
            sub_type = getattr(mod, "subdivision_type", "CATMULL_CLARK")
            mode_lbl = "Simple" if sub_type == "SIMPLE" else "Standard"
            lvl = int(mod.levels) if mod.show_viewport else 0
            return (lvl, mode_lbl)

    return (0, "Standard")


def compute_poly_stats(context) -> dict:
    """Compute Maya 3-column Poly Count (Scene / Selected Objects / Selected Components) and Subdiv info."""
    view_layer = getattr(context, "view_layer", None)
    objects = view_layer.objects if view_layer is not None else bpy.data.objects
    selected_set = set(getattr(context, "selected_objects", ()) or ())
    active_obj = getattr(context, "active_object", None)
    mode = getattr(context, "mode", "OBJECT")
    if mode == "EDIT_MESH" and active_obj is not None:
        selected_set.add(active_obj)
    for m_obj in getattr(context, "objects_in_mode", ()) or ():
        selected_set.add(m_obj)

    scene_v = scene_e = scene_f = scene_t = scene_uv = 0
    sel_v = sel_e = sel_f = sel_t = sel_uv = 0
    comp_v = comp_e = comp_f = comp_t = comp_uv = 0

    for obj in objects:
        if obj is None or obj.type != "MESH" or obj.data is None:
            continue
        try:
            visible = obj.visible_get(view_layer=view_layer) if view_layer is not None else obj.visible_get()
        except Exception:
            visible = not obj.hide_viewport
        if not visible:
            continue

        me = obj.data
        is_sel = obj in selected_set
        has_uv = me.uv_layers.active is not None

        if mode == "EDIT_MESH" and obj.mode == "EDIT":
            bm = bmesh.from_edit_mesh(me)
            has_uv = has_uv or (bm.loops.layers.uv.active is not None)
            ov = len(bm.verts)
            oe = len(bm.edges)
            of = len(bm.faces)
            ot = sum(max(0, len(f.verts) - 2) for f in bm.faces)
            ouv = sum(len(f.loops) for f in bm.faces) if has_uv else 0

            cv = sum(1 for v in bm.verts if v.select)
            ce = sum(1 for e in bm.edges if e.select)
            cf = sum(1 for f in bm.faces if f.select)
            ct = sum(max(0, len(f.verts) - 2) for f in bm.faces if f.select)
            if has_uv:
                if cf > 0:
                    cuv = sum(len(f.loops) for f in bm.faces if f.select)
                else:
                    cuv = sum(1 for f in bm.faces for lp in f.loops if lp.vert.select)
            else:
                cuv = 0

            comp_v += cv
            comp_e += ce
            comp_f += cf
            comp_t += ct
            comp_uv += cuv
        else:
            ov = len(me.vertices)
            oe = len(me.edges)
            of = len(me.polygons)
            loops_n = len(me.loops)
            ot = max(0, loops_n - 2 * of)
            ouv = loops_n if has_uv else 0

        scene_v += ov
        scene_e += oe
        scene_f += of
        scene_t += ot
        scene_uv += ouv

        if is_sel:
            sel_v += ov
            sel_e += oe
            sel_f += of
            sel_t += ot
            sel_uv += ouv

    subdiv_level, subdiv_mode = _active_subdiv_info(active_obj)
    return {
        "verts": (scene_v, sel_v, comp_v),
        "edges": (scene_e, sel_e, comp_e),
        "faces": (scene_f, sel_f, comp_f),
        "tris": (scene_t, sel_t, comp_t),
        "uvs": (scene_uv, sel_uv, comp_uv),
        "subdiv_level": subdiv_level,
        "subdiv_mode": subdiv_mode,
    }


def _selection_signature(context) -> tuple:
    active = getattr(context, "active_object", None)
    sel_objs = getattr(context, "selected_objects", ()) or ()
    return (
        getattr(context, "mode", "OBJECT"),
        active.as_pointer() if active is not None else 0,
        len(sel_objs),
        len(getattr(context, "scene", None).objects) if getattr(context, "scene", None) else 0,
    )


def _get_cached_stats(context) -> dict:
    global _STATS_DIRTY, _CACHE_KEY, _CACHE_TIME, _CACHE_STATS
    now = time.monotonic()
    sig = _selection_signature(context)
    in_edit = sig[0] == "EDIT_MESH"
    if (
        _CACHE_KEY != sig
        or (_STATS_DIRTY and (now - _CACHE_TIME) >= 0.12)
        or (in_edit and (now - _CACHE_TIME) >= 0.15)
    ):
        _CACHE_STATS = compute_poly_stats(context)
        _CACHE_KEY = sig
        _CACHE_TIME = now
        _STATS_DIRTY = False
    return _CACHE_STATS


@persistent
def _on_depsgraph_update(_scene, _depsgraph=None):
    global _STATS_DIRTY
    _STATS_DIRTY = True


def _compute_hud_anchor(area, region, space, ui_scale: float) -> tuple[float, float]:
    left_inset = 0.0
    top_inset = 0.0

    for reg in getattr(area, "regions", ()):
        if reg == region:
            continue
        if reg.type == "TOOLS" and reg.width > 1 and reg.alignment == "LEFT":
            overlap_x = (reg.x + reg.width) - region.x
            if 0 < overlap_x < 260 * ui_scale:
                left_inset = max(left_inset, float(overlap_x))
        elif reg.type in {"HEADER", "TOOL_HEADER"} and reg.height > 1 and reg.alignment == "TOP":
            # Count header height only when Region Overlap places it inside WINDOW's vertical bounds
            if reg.y >= region.y and (reg.y + reg.height) <= (region.y + region.height + 2):
                top_inset += float(reg.height)

    text_offset = (
        (68.0 * ui_scale)
        if (getattr(space.overlay, "show_overlays", True) and getattr(space.overlay, "show_text", True))
        else (22.0 * ui_scale)
    )
    x = left_inset + (14.0 * ui_scale)
    y = float(region.height) - top_inset - text_offset
    return (x, y)


def sync_viewport_text_overlay(hide_text: bool, context=None):
    """Hide Blender's top-left Text Info ('User Perspective / Cube') when Maya Poly HUD is active."""
    ctx = context or bpy.context
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
            if hide_text:
                if ptr not in _PREV_SHOW_TEXT:
                    _PREV_SHOW_TEXT[ptr] = bool(sp.overlay.show_text)
                sp.overlay.show_text = False
            else:
                sp.overlay.show_text = _PREV_SHOW_TEXT.pop(ptr, True)
            area.tag_redraw()


def _draw_poly_count_hud():
    ctx = bpy.context
    prefs = get_prefs(ctx)
    if not bool(getattr(prefs, "show_poly_count_hud", True)):
        return

    area = getattr(ctx, "area", None)
    region = getattr(ctx, "region", None)
    space = getattr(ctx, "space_data", None)
    if area is None or region is None or space is None or area.type != "VIEW_3D":
        return

    quads = getattr(space, "region_quadviews", None)
    if quads and len(quads) == 4:
        win_regions = [r for r in area.regions if r.type == "WINDOW"]
        if win_regions:
            top_left = max(win_regions, key=lambda r: (r.y, -r.x))
            if region != top_left:
                return

    prefs_root = getattr(ctx, "preferences", None)
    ui_scale = float(getattr(prefs_root.system, "ui_scale", 1.0)) if prefs_root is not None else 1.0

    stats = _get_cached_stats(ctx)
    start_x, start_y = _compute_hud_anchor(area, region, space, ui_scale)

    font_id = 0
    font_size = max(11, int(12 * ui_scale))
    line_step = 17.0 * ui_scale

    label_x = start_x
    col_x = (
        start_x + 150.0 * ui_scale,
        start_x + 216.0 * ui_scale,
        start_x + 282.0 * ui_scale,
    )

    rows_3col = (
        ("Verts:", stats["verts"]),
        ("Edges:", stats["edges"]),
        ("Faces:", stats["faces"]),
        ("Tris:", stats["tris"]),
        ("UVs:", stats["uvs"]),
    )

    blf.size(font_id, font_size)
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.88)
    try:
        y = start_y
        for label, vals in rows_3col:
            blf.color(font_id, *_LABEL_COLOR)
            blf.position(font_id, label_x, y, 0.0)
            blf.draw(font_id, label)

            blf.color(font_id, *_VALUE_COLOR)
            for cx, val in zip(col_x, vals):
                blf.position(font_id, cx, y, 0.0)
                blf.draw(font_id, str(val))
            y -= line_step

        # Subdiv rows matching Maya Heads-Up Display
        for label, val in (
            ("Subdiv current level:", str(stats["subdiv_level"])),
            ("Subdiv mode:", str(stats["subdiv_mode"])),
        ):
            blf.color(font_id, *_LABEL_COLOR)
            blf.position(font_id, label_x, y, 0.0)
            blf.draw(font_id, label)

            blf.color(font_id, *_VALUE_COLOR)
            blf.position(font_id, col_x[0], y, 0.0)
            blf.draw(font_id, val)
            y -= line_step
    finally:
        blf.disable(font_id, blf.SHADOW)


class MAYA_UX_OT_toggle_poly_count_hud(bpy.types.Operator):
    """Toggle Maya-style Poly Count & Subdiv Heads-Up Display in 3D Viewports."""

    bl_idname = "maya_ux.toggle_poly_count_hud"
    bl_label = "Toggle Maya Poly Count HUD"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .preferences import _DEFAULT_PREFS

        prefs = get_prefs(context)
        new_val = not bool(getattr(prefs, "show_poly_count_hud", True))
        if prefs is _DEFAULT_PREFS:
            _DEFAULT_PREFS.show_poly_count_hud = new_val
        else:
            prefs.show_poly_count_hud = new_val

        sync_viewport_text_overlay(new_val, context)
        return {"FINISHED"}


CLASSES = (MAYA_UX_OT_toggle_poly_count_hud,)


def register():
    global _HUD_HANDLE
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if _HUD_HANDLE is None:
        _HUD_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_poly_count_hud, (), "WINDOW", "POST_PIXEL"
        )
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
    prefs = get_prefs()
    sync_viewport_text_overlay(bool(getattr(prefs, "show_poly_count_hud", True)))


def unregister():
    global _HUD_HANDLE
    sync_viewport_text_overlay(False)
    _PREV_SHOW_TEXT.clear()
    if _HUD_HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_HUD_HANDLE, "WINDOW")
        except Exception:
            pass
        _HUD_HANDLE = None
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
