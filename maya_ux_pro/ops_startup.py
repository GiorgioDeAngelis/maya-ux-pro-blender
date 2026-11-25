from __future__ import annotations

import bpy
from bpy.app.handlers import persistent

from .preferences import get_prefs

DEFAULT_STARTUP_OBJECT_NAMES = {"Cube", "Camera", "Light"}


def is_factory_default_scene() -> bool:
    """Return True only for an unsaved scene containing solely Blender's factory Cube/Camera/Light."""
    if bpy.data.filepath:
        return False
    objs = list(bpy.data.objects)
    if not objs:
        return False
    return {o.name for o in objs}.issubset(DEFAULT_STARTUP_OBJECT_NAMES)


def clear_default_scene_objects(context=None) -> int:
    """Remove scene objects, empty default 'Collection', and zero-user default datablocks."""
    objs = list(bpy.data.objects)
    removed = len(objs)
    for obj in objs:
        bpy.data.objects.remove(obj, do_unlink=True)

    default_col = bpy.data.collections.get("Collection")
    if default_col is not None and len(default_col.objects) == 0 and len(default_col.children) == 0:
        bpy.data.collections.remove(default_col)

    for data_coll in (bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
        for datablock in list(data_coll):
            if datablock.users == 0:
                try:
                    data_coll.remove(datablock)
                except Exception:
                    pass

    return removed


def _close_bottom_timeline(context, win, scr, v3d_areas: list[bpy.types.Area]):
    dopes = [a for a in scr.areas if a.type == "DOPESHEET_EDITOR"]
    for dope in dopes:
        for v3d in v3d_areas:
            aligned_x = abs(dope.x - v3d.x) <= 8 and abs(dope.width - v3d.width) <= 8
            is_below = (dope.y + dope.height) <= (v3d.y + 8)
            if aligned_x and is_below and hasattr(context, "temp_override"):
                try:
                    with context.temp_override(window=win, screen=scr, area=dope):
                        bpy.ops.screen.area_close()
                except Exception:
                    pass
                break


def apply_clean_maya_ui(context=None, remove_timeline: bool = True):
    """Apply the user's clean charcoal 3-pane Maya viewport layout and preferences."""
    ctx = context or bpy.context
    prefs = getattr(ctx, "preferences", None)
    if prefs is not None:
        prefs.view.gizmo_size = 75
        prefs.view.show_statusbar_memory = False
        prefs.view.show_statusbar_stats = False
        if prefs.themes:
            v3d_theme = prefs.themes[0].view_3d
            v3d_theme.grid = (0.38, 0.38, 0.38, 0.651)
            v3d_theme.grid_major = (0.478, 0.478, 0.478, 0.851)
            v3d_theme.facedot_size = 5 if bool(getattr(get_prefs(ctx), "maya_face_center_select", True)) else 3
            gradients = v3d_theme.space.gradients
            gradients.background_type = "SINGLE_COLOR"
            gradients.high_gradient = (0.09, 0.09, 0.09)
            gradients.gradient = (0.09, 0.09, 0.09)

    wm = getattr(ctx, "window_manager", None)
    if wm is None:
        return

    for win in wm.windows:
        scr = getattr(win, "screen", None)
        if scr is None:
            continue
        v3d_areas = [a for a in scr.areas if a.type == "VIEW_3D"]
        if remove_timeline and not bpy.app.background:
            _close_bottom_timeline(ctx, win, scr, v3d_areas)

        for area in scr.areas:
            if area.type != "VIEW_3D":
                continue
            sp = area.spaces.active
            if sp is None:
                continue
            if not bpy.app.background:
                for reg_attr, reg_val in (
                    ("show_region_header", True),
                    ("show_region_tool_header", True),
                    ("show_region_toolbar", True),
                    ("show_region_ui", True),
                    ("show_region_hud", True),
                    ("show_region_asset_shelf", False),
                ):
                    if getattr(sp, reg_attr) != reg_val:
                        setattr(sp, reg_attr, reg_val)

            sp.show_gizmo = True
            sp.show_gizmo_navigate = True
            sp.show_gizmo_tool = True
            sp.show_gizmo_context = True
            sp.show_gizmo_object_translate = True

            sp.lens = 50.0
            sp.clip_start = 0.01
            sp.clip_end = 1000.0

            ov = sp.overlay
            ov.show_overlays = True
            ov.show_floor = True
            ov.show_axis_x = True
            ov.show_axis_y = True
            ov.show_axis_z = False
            ov.show_cursor = True
            ov.show_object_origins = True
            ov.show_relationship_lines = True
            ov.show_extras = True
            ov.show_text = not bool(getattr(get_prefs(ctx), "show_poly_count_hud", True))
            ov.show_stats = False
            ov.show_face_center = bool(getattr(get_prefs(ctx), "maya_face_center_select", True))
            ov.grid_subdivisions = 10
            ov.grid_scale = 1.0

            sh = sp.shading
            sh.type = "SOLID"
            sh.light = "STUDIO"
            sh.color_type = "MATERIAL"
            sh.show_cavity = False
            sh.show_shadows = False
            sh.background_type = "THEME"

            area.tag_redraw()


def _apply_clean_ui_deferred():
    prefs = get_prefs()
    if bool(getattr(prefs, "clean_maya_startup_layout", True)):
        apply_clean_maya_ui(bpy.context, remove_timeline=not bpy.app.background)
    return None


@persistent
def _on_load_post(_dummy):
    if bpy.data.filepath:
        return
    prefs = get_prefs()
    if bool(getattr(prefs, "clean_empty_new_scene", True)) and is_factory_default_scene():
        clear_default_scene_objects()
    if bool(getattr(prefs, "maya_face_center_select", True)):
        from . import ops_selection

        ops_selection.sync_face_center_overlay(True)
    if bool(getattr(prefs, "clean_maya_startup_layout", True)) and not bpy.app.background:
        if not bpy.app.timers.is_registered(_apply_clean_ui_deferred):
            bpy.app.timers.register(_apply_clean_ui_deferred, first_interval=0.05)


class MAYA_UX_OT_new_clean_scene(bpy.types.Operator):
    """Clear the scene to empty and apply the clean 3-pane Maya viewport layout."""

    bl_idname = "maya_ux.new_clean_scene"
    bl_label = "New Clean Empty Scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        clear_default_scene_objects(context)
        apply_clean_maya_ui(context, remove_timeline=not bpy.app.background)
        self.report({"INFO"}, "Clean empty Maya scene ready")
        return {"FINISHED"}


class MAYA_UX_OT_save_clean_startup(bpy.types.Operator):
    """Clear factory objects if present, apply clean Maya layout, and save Blender Startup File."""

    bl_idname = "maya_ux.save_clean_startup"
    bl_label = "Save Clean Empty Startup File"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if is_factory_default_scene():
            clear_default_scene_objects(context)
        apply_clean_maya_ui(context, remove_timeline=not bpy.app.background)
        try:
            bpy.ops.wm.save_homefile()
        except Exception as exc:
            self.report({"WARNING"}, f"Could not save Startup File: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Saved Clean Empty Startup File")
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_new_clean_scene,
    MAYA_UX_OT_save_clean_startup,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    if bpy.app.timers.is_registered(_apply_clean_ui_deferred):
        bpy.app.timers.unregister(_apply_clean_ui_deferred)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
