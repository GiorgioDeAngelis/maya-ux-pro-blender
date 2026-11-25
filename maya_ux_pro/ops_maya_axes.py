from __future__ import annotations

import math
from math import hypot

import blf
import bpy
import gpu
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, PointerProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Quaternion, Vector

BLENDER_AXIS_COLORS = (
    (1.0, 0.2, 0.322),
    (0.545, 0.863, 0.0),
    (0.157, 0.565, 1.0),
)
MAYA_AXIS_COLORS = (
    (1.0, 0.2, 0.322),  # X = Red (Right)
    (0.157, 0.565, 1.0),  # Blender Y (Depth) = Blue (like Maya Z)
    (0.545, 0.863, 0.0),  # Blender Z (Up) = Green (like Maya Y)
)

MAYA_X = Vector((1.0, 0.0, 0.0))
MAYA_Y = Vector((0.0, 0.0, 1.0))   # Up
MAYA_Z = Vector((0.0, -1.0, 0.0))  # Forward toward viewer
_MAYA_AXIS_SPECS = (
    ("X", MAYA_X, (0.95, 0.22, 0.24, 1.0)),
    ("Y", MAYA_Y, (0.26, 0.88, 0.20, 1.0)),
    ("Z", MAYA_Z, (0.20, 0.56, 1.0, 1.0)),
)
_HUD_DRAW_HANDLE = None
_PREV_NAV_GIZMO: dict[int, bool] = {}


def project_maya_yup_axes(view_rotation: Quaternion) -> list[tuple[str, Vector, tuple[float, float, float, float]]]:
    """Project Maya's right-handed Y-Up axes (X Red, Y Green Up, Z Blue Forward) into camera space."""
    rot_inv = view_rotation.inverted()
    return [(label, rot_inv @ vec, color) for label, vec, color in _MAYA_AXIS_SPECS]


def sync_viewport_yup_gizmo(hide_zup_gizmo: bool, context=None):
    """Hide Blender's Z-Up navigation gizmo when Maya Y-Up tripod is active, or restore previous state."""
    ctx = context or bpy.context
    wm = getattr(ctx, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            if space is None:
                continue
            ptr = space.as_pointer()
            if hide_zup_gizmo:
                if ptr not in _PREV_NAV_GIZMO:
                    _PREV_NAV_GIZMO[ptr] = bool(space.show_gizmo_navigate)
                space.show_gizmo_navigate = False
            else:
                space.show_gizmo_navigate = _PREV_NAV_GIZMO.pop(ptr, True)
            area.tag_redraw()


def _draw_maya_yup_axis_hud():
    from .preferences import get_prefs

    ctx = bpy.context
    prefs = get_prefs(ctx)
    if not bool(getattr(prefs, "show_maya_yup_hud", False)):
        return

    region = getattr(ctx, "region", None)
    rv3d = getattr(ctx, "region_data", None)
    if region is None or rv3d is None:
        return

    prefs_root = getattr(ctx, "preferences", None)
    ui_scale = float(getattr(prefs_root.system, "ui_scale", 1.0)) if prefs_root is not None else 1.0

    origin_x = 58.0 * ui_scale
    origin_y = 68.0 * ui_scale
    axis_len = 34.0 * ui_scale
    head_len = 8.0 * ui_scale
    half_w = 3.5 * ui_scale

    projected = sorted(project_maya_yup_axes(rv3d.view_rotation), key=lambda item: item[1].z)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(2.5 * ui_scale)
    try:
        labels_to_draw: list[tuple[str, float, float, tuple[float, float, float, float]]] = []
        for label, cam_vec, color in projected:
            end_x = origin_x + cam_vec.x * axis_len
            end_y = origin_y + cam_vec.y * axis_len
            proj_len = hypot(cam_vec.x, cam_vec.y) * axis_len

            shader.bind()
            shader.uniform_float("color", color)
            batch_line = batch_for_shader(shader, "LINES", {"pos": ((origin_x, origin_y), (end_x, end_y))})
            batch_line.draw(shader)

            if proj_len > 6.0 * ui_scale:
                dx = (end_x - origin_x) / proj_len
                dy = (end_y - origin_y) / proj_len
                px, py = -dy, dx
                tip = (end_x + dx * head_len, end_y + dy * head_len)
                base_l = (end_x - dx * (2.0 * ui_scale) + px * half_w, end_y - dy * (2.0 * ui_scale) + py * half_w)
                base_r = (end_x - dx * (2.0 * ui_scale) - px * half_w, end_y - dy * (2.0 * ui_scale) - py * half_w)
                batch_tri = batch_for_shader(shader, "TRIS", {"pos": (tip, base_l, base_r)})
                batch_tri.draw(shader)
                lbl_x = tip[0] + dx * (5.0 * ui_scale) - (4.0 * ui_scale)
                lbl_y = tip[1] + dy * (5.0 * ui_scale) - (5.0 * ui_scale)
            else:
                lbl_x = origin_x + (6.0 * ui_scale)
                lbl_y = origin_y + (6.0 * ui_scale)

            labels_to_draw.append((label, lbl_x, lbl_y, color))

        # Neutral origin dot
        d = 2.5 * ui_scale
        shader.bind()
        shader.uniform_float("color", (0.85, 0.85, 0.85, 0.9))
        batch_dot = batch_for_shader(
            shader,
            "TRIS",
            {
                "pos": (
                    (origin_x - d, origin_y - d),
                    (origin_x + d, origin_y - d),
                    (origin_x + d, origin_y + d),
                    (origin_x - d, origin_y - d),
                    (origin_x + d, origin_y + d),
                    (origin_x - d, origin_y + d),
                )
            },
        )
        batch_dot.draw(shader)

        font_id = 0
        blf.size(font_id, max(10, int(13 * ui_scale)))
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.85)
        try:
            for label, lx, ly, color in labels_to_draw:
                blf.color(font_id, *color)
                blf.position(font_id, lx, ly, 0.0)
                blf.draw(font_id, label)
        finally:
            blf.disable(font_id, blf.SHADOW)
    finally:
        gpu.state.line_width_set(1.0)
        gpu.state.blend_set("NONE")


def apply_maya_axis_colors(enabled: bool, context=None):
    """Visually swap Y/Z viewport axis colors so Up axis is Green (Maya Y) and Depth is Blue (Maya Z)."""
    ctx = context or bpy.context
    prefs = getattr(ctx, "preferences", None)
    if prefs is None or not prefs.themes:
        return
    ui_theme = prefs.themes[0].user_interface
    cols = MAYA_AXIS_COLORS if enabled else BLENDER_AXIS_COLORS
    ui_theme.axis_x = cols[0]
    ui_theme.axis_y = cols[1]
    ui_theme.axis_z = cols[2]


def apply_maya_grid_theme(context=None):
    """Apply Maya-like viewport gradient, grid colors, and floor/axis overlay settings."""
    ctx = context or bpy.context
    prefs = getattr(ctx, "preferences", None)
    if prefs is not None and prefs.themes:
        v3d_theme = prefs.themes[0].view_3d
        v3d_theme.grid = (0.38, 0.38, 0.38, 0.65)
        v3d_theme.grid_major = (0.48, 0.48, 0.48, 0.85)
        gradients = v3d_theme.space.gradients
        gradients.background_type = "LINEAR"
        gradients.high_gradient = (0.38, 0.43, 0.50)
        gradients.gradient = (0.14, 0.16, 0.19)

    wm = getattr(ctx, "window_manager", None)
    if wm is not None:
        for win in wm.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    space = area.spaces.active
                    space.overlay.show_floor = True
                    space.overlay.show_axis_x = True
                    space.overlay.show_axis_y = True
                    space.overlay.grid_subdivisions = 5

    from .preferences import get_prefs

    sync_viewport_yup_gizmo(bool(getattr(get_prefs(ctx), "show_maya_yup_hud", False)), ctx)


def _active_obj():
    return getattr(bpy.context, "active_object", None)


def _get_translate(self):
    obj = _active_obj()
    if obj is None:
        return (0.0, 0.0, 0.0)
    return (obj.location.x, obj.location.z, -obj.location.y)


def _set_translate(self, value):
    obj = _active_obj()
    if obj is None:
        return
    if not obj.lock_location[0]:
        obj.location[0] = value[0]
    if not obj.lock_location[2]:
        obj.location[2] = value[1]
    if not obj.lock_location[1]:
        obj.location[1] = -value[2]


def _get_rotate(self):
    obj = _active_obj()
    if obj is None:
        return (0.0, 0.0, 0.0)
    return (obj.rotation_euler.x, obj.rotation_euler.z, -obj.rotation_euler.y)


def _set_rotate(self, value):
    obj = _active_obj()
    if obj is None:
        return
    if not obj.lock_rotation[0]:
        obj.rotation_euler[0] = value[0]
    if not obj.lock_rotation[2]:
        obj.rotation_euler[2] = value[1]
    if not obj.lock_rotation[1]:
        obj.rotation_euler[1] = -value[2]


def _get_scale(self):
    obj = _active_obj()
    if obj is None:
        return (1.0, 1.0, 1.0)
    return (obj.scale.x, obj.scale.z, obj.scale.y)


def _set_scale(self, value):
    obj = _active_obj()
    if obj is None:
        return
    if not obj.lock_scale[0]:
        obj.scale[0] = value[0]
    if not obj.lock_scale[2]:
        obj.scale[2] = value[1]
    if not obj.lock_scale[1]:
        obj.scale[1] = value[2]


class MayaYUpProxy(bpy.types.PropertyGroup):
    """Virtual Y-Up (Maya) Channel Box proxy mapped onto active object's Z-Up Blender transforms."""

    translate: FloatVectorProperty(
        name="Translate (Maya Y-Up)",
        size=3,
        subtype="TRANSLATION",
        unit="LENGTH",
        get=_get_translate,
        set=_set_translate,
    )
    rotate: FloatVectorProperty(
        name="Rotate (Maya Y-Up)",
        size=3,
        subtype="EULER",
        unit="ROTATION",
        get=_get_rotate,
        set=_set_rotate,
    )
    scale: FloatVectorProperty(
        name="Scale (Maya Y-Up)",
        size=3,
        subtype="XYZ",
        get=_get_scale,
        set=_set_scale,
    )


class MAYA_UX_OT_convert_up_axis(bpy.types.Operator):
    """Rotate selected objects ±90° around X to convert between Maya Y-Up and Blender Z-Up."""

    bl_idname = "maya_ux.convert_up_axis"
    bl_label = "Convert Up-Axis (Y-Up / Z-Up)"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        name="Direction",
        items=[
            ("Y_TO_Z", "Maya Y-Up -> Blender Z-Up (+90° X)", "Rotate +90° on X so Maya Y-Up model stands upright in Blender"),
            ("Z_TO_Y", "Blender Z-Up -> Maya Y-Up (-90° X)", "Rotate -90° on X for Maya Y-Up orientation"),
        ],
        default="Y_TO_Z",
    )
    apply_rotation: BoolProperty(
        name="Freeze Rotation After Convert",
        description="Apply rotation to mesh data when single-user",
        default=True,
    )

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            self.report({"WARNING"}, "Select at least one object")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        angle = math.pi * 0.5 if self.direction == "Y_TO_Z" else -math.pi * 0.5
        view_layer = context.view_layer
        prev_active = context.active_object

        try:
            for obj in selected:
                obj.rotation_euler.x += angle
                if self.apply_rotation and (obj.data is None or obj.data.users == 1):
                    bpy.ops.object.select_all(action="DESELECT")
                    obj.select_set(True)
                    view_layer.objects.active = obj
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in selected:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if prev_active is not None and prev_active.name in bpy.data.objects:
                view_layer.objects.active = prev_active

        return {"FINISHED"}


class MAYA_UX_OT_apply_maya_grid_theme(bpy.types.Operator):
    """Apply Maya viewport background gradient, grid colors, and respect axis theme preference."""

    bl_idname = "maya_ux.apply_maya_grid_theme"
    bl_label = "Apply Maya Grid & Viewport Theme"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .preferences import get_prefs

        apply_maya_grid_theme(context)
        apply_maya_axis_colors(bool(getattr(get_prefs(context), "swap_axis_colors_yup", False)), context)
        self.report({"INFO"}, "Maya Grid & Viewport theme applied")
        return {"FINISHED"}


class MAYA_UX_OT_set_maya_cm_units(bpy.types.Operator):
    """Toggle scene units between Maya Centimeters (0.01) and Blender Meters (1.0)."""

    bl_idname = "maya_ux.set_maya_cm_units"
    bl_label = "Toggle Maya Centimeters"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        us = context.scene.unit_settings
        is_cm = us.system == "METRIC" and us.length_unit == "CENTIMETERS"
        if us.system != "METRIC":
            us.system = "METRIC"
        if is_cm:
            us.length_unit = "METERS"
            us.scale_length = 1.0
            self.report({"INFO"}, "Scene Units: Meters (1.0)")
        else:
            us.length_unit = "CENTIMETERS"
            us.scale_length = 0.01
            self.report({"INFO"}, "Scene Units: Maya Centimeters (0.01)")
        return {"FINISHED"}


class MAYA_UX_OT_toggle_channel_box_yup(bpy.types.Operator):
    """Toggle Channel Box display between Maya Y-Up and Blender Z-Up."""

    bl_idname = "maya_ux.toggle_channel_box_yup"
    bl_label = "Toggle Channel Box Y-Up"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .preferences import _DEFAULT_PREFS, get_prefs

        prefs = get_prefs(context)
        new_val = not bool(getattr(prefs, "channel_box_yup", False))
        if prefs is _DEFAULT_PREFS:
            _DEFAULT_PREFS.channel_box_yup = new_val
        else:
            prefs.channel_box_yup = new_val
        return {"FINISHED"}


CLASSES = (
    MayaYUpProxy,
    MAYA_UX_OT_convert_up_axis,
    MAYA_UX_OT_apply_maya_grid_theme,
    MAYA_UX_OT_set_maya_cm_units,
    MAYA_UX_OT_toggle_channel_box_yup,
)


def register():
    global _HUD_DRAW_HANDLE
    from .preferences import get_prefs

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.maya_ux_yup = PointerProperty(type=MayaYUpProxy)
    if _HUD_DRAW_HANDLE is None:
        _HUD_DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_maya_yup_axis_hud, (), "WINDOW", "POST_PIXEL"
        )
    prefs = get_prefs()
    apply_maya_axis_colors(bool(getattr(prefs, "swap_axis_colors_yup", False)))
    sync_viewport_yup_gizmo(bool(getattr(prefs, "show_maya_yup_hud", False)))


def unregister():
    global _HUD_DRAW_HANDLE
    if _HUD_DRAW_HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_HUD_DRAW_HANDLE, "WINDOW")
        except Exception:
            pass
        _HUD_DRAW_HANDLE = None
    sync_viewport_yup_gizmo(False)
    _PREV_NAV_GIZMO.clear()
    if hasattr(bpy.types.WindowManager, "maya_ux_yup"):
        del bpy.types.WindowManager.maya_ux_yup
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
