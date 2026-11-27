from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty
from mathutils import Vector

_HOLD_SNAP_BACKUP: dict | None = None
_HOLD_PIVOT_BACKUP: dict | None = None


def _get_current_tool_id(context) -> str:
    ws = getattr(context, "workspace", None)
    if ws is not None and hasattr(ws, "tools"):
        try:
            tool = ws.tools.from_space_view3d_mode(context.mode)
            if tool is not None and tool.idname:
                return tool.idname
        except Exception:
            pass
    return "builtin.select_box"


def _redraw_view3d_areas(context):
    wm = getattr(context, "window_manager", None)
    if wm is None:
        return
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _set_origin_to_cursor_for_objects(context, objects: list[bpy.types.Object], cursor_pos_fn):
    """Apply ORIGIN_CURSOR individually per object while preserving selection and 3D cursor."""
    view_layer = context.view_layer
    prev_selected = list(context.selected_objects)
    prev_active = context.active_object

    for obj in objects:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        view_layer.objects.active = obj
        context.scene.cursor.location = cursor_pos_fn(obj)
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in prev_selected:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    if prev_active is not None and prev_active.name in bpy.data.objects:
        view_layer.objects.active = prev_active


class MAYA_UX_OT_toggle_edit_pivot(bpy.types.Operator):
    """Toggle Maya-style Edit Pivot mode (D) using Transform Affect Only Origins."""

    bl_idname = "maya_ux.toggle_edit_pivot"
    bl_label = "Toggle Edit Pivot"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global _HOLD_PIVOT_BACKUP
        _HOLD_PIVOT_BACKUP = None
        ts = context.scene.tool_settings
        new_state = not ts.use_transform_data_origin
        ts.use_transform_data_origin = new_state
        if _HOLD_SNAP_BACKUP is not None:
            ts.use_snap_self = bool(new_state)

        if new_state and context.mode == "OBJECT":
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.move")
            except Exception:
                pass
            space = getattr(context, "space_data", None)
            if space is not None and space.type == "VIEW_3D":
                space.show_gizmo = True
                space.show_gizmo_tool = True

        self.report({"INFO"}, f"Edit Pivot: {'ON' if new_state else 'OFF'}")
        return {"FINISHED"}


class MAYA_UX_OT_pivot_action(bpy.types.Operator):
    """Reposition object pivot (Center, World Origin, Bottom Center, or Match Active)."""

    bl_idname = "maya_ux.pivot_action"
    bl_label = "Maya Pivot Action"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        name="Action",
        items=[
            ("CENTER", "Center Pivot", "Move pivot to bounding box center"),
            ("WORLD_ORIGIN", "Pivot to World Origin", "Move pivot to (0, 0, 0) without moving mesh"),
            ("BOTTOM_CENTER", "Pivot to Bottom Center", "Move pivot to bottom-center of bounding box"),
            ("TO_ACTIVE", "Match Active Pivot", "Align pivots of selected objects to active object origin"),
        ],
        default="CENTER",
    )

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}]
        if not selected:
            self.report({"WARNING"}, "Select at least one object")
            return {"CANCELLED"}

        was_edit = context.mode != "OBJECT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")

        cursor = context.scene.cursor
        saved_loc = cursor.location.copy()
        saved_rot = cursor.rotation_euler.copy()

        try:
            if self.action == "CENTER":
                bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")

            elif self.action == "WORLD_ORIGIN":
                _set_origin_to_cursor_for_objects(context, selected, lambda _obj: Vector((0.0, 0.0, 0.0)))

            elif self.action == "BOTTOM_CENTER":
                def _bottom_center(obj: bpy.types.Object) -> Vector:
                    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
                    xs = [p.x for p in corners]
                    ys = [p.y for p in corners]
                    zs = [p.z for p in corners]
                    return Vector(((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, min(zs)))

                _set_origin_to_cursor_for_objects(context, selected, _bottom_center)

            elif self.action == "TO_ACTIVE":
                active = context.active_object
                if active is None:
                    return {"CANCELLED"}
                target_loc = active.matrix_world.translation.copy()
                targets = [obj for obj in selected if obj != active]
                if targets:
                    _set_origin_to_cursor_for_objects(context, targets, lambda _obj: target_loc)
        finally:
            cursor.location = saved_loc
            cursor.rotation_euler = saved_rot
            if was_edit and context.active_object is not None:
                bpy.ops.object.mode_set(mode="EDIT")

        return {"FINISHED"}


def _configure_maya_snap_target(context, snap_type: str):
    """Snap object origin/pivot in Object Mode or transform center in Edit Mode onto other objects."""
    ts = context.scene.tool_settings
    ts.snap_target = "ACTIVE" if context.mode == "OBJECT" else "CENTER"
    ts.use_snap_self = bool(ts.use_transform_data_origin)
    ts.use_snap_nonedit = True
    ts.use_snap_translate = True
    if snap_type == "INCREMENT":
        ts.use_snap_rotate = True
        ts.use_snap_scale = True


class MAYA_UX_OT_maya_snap(bpy.types.Operator):
    """Maya-style Snap toggle/switch: X = Grid, C = Curve/Edge, V = Point/Vertex."""

    bl_idname = "maya_ux.maya_snap"
    bl_label = "Maya Snap"
    bl_options = {"REGISTER", "UNDO"}

    snap_type: EnumProperty(
        name="Snap Type",
        items=[
            ("GRID", "Grid (X)", "Snap to grid"),
            ("EDGE", "Edge / Curve (C)", "Snap to edge"),
            ("VERTEX", "Vertex / Point (V)", "Snap to vertex"),
        ],
        default="VERTEX",
    )

    def execute(self, context):
        global _HOLD_SNAP_BACKUP
        _HOLD_SNAP_BACKUP = None
        ts = context.scene.tool_settings
        target_set = {self.snap_type}

        if ts.use_snap and set(ts.snap_elements) == target_set:
            ts.use_snap = False
            self.report({"INFO"}, f"Snap {self.snap_type}: OFF")
        else:
            ts.snap_elements = target_set
            ts.use_snap = True
            _configure_maya_snap_target(context, self.snap_type)
            self.report({"INFO"}, f"Snap {self.snap_type}: ON")
        return {"FINISHED"}


class MAYA_UX_OT_maya_snap_hold(bpy.types.Operator):
    """Maya-native Hold-to-Snap: hold V (Vertex), C (Edge), X (Grid), J (Step); release to restore."""

    bl_idname = "maya_ux.maya_snap_hold"
    bl_label = "Maya Hold Snap"
    bl_options = {"REGISTER"}

    snap_type: EnumProperty(
        name="Snap Type",
        items=[
            ("GRID", "Grid (X)", "Snap to grid while held"),
            ("EDGE", "Edge / Curve (C)", "Snap to edge while held"),
            ("VERTEX", "Vertex / Point (V)", "Snap to vertex while held"),
            ("INCREMENT", "Discrete Step (J)", "Snap to increment while held"),
        ],
        default="VERTEX",
    )
    active: BoolProperty(name="Hold Active", default=True)

    def execute(self, context):
        global _HOLD_SNAP_BACKUP
        ts = context.scene.tool_settings

        if self.active:
            if _HOLD_SNAP_BACKUP is None:
                _HOLD_SNAP_BACKUP = {
                    "use_snap": bool(ts.use_snap),
                    "snap_elements": set(ts.snap_elements),
                    "snap_target": str(ts.snap_target),
                    "use_snap_self": bool(ts.use_snap_self),
                    "use_snap_nonedit": bool(ts.use_snap_nonedit),
                    "use_snap_translate": bool(ts.use_snap_translate),
                    "use_snap_rotate": bool(ts.use_snap_rotate),
                    "use_snap_scale": bool(ts.use_snap_scale),
                }
            ts.snap_elements = {self.snap_type}
            ts.use_snap = True
            _configure_maya_snap_target(context, self.snap_type)
            _redraw_view3d_areas(context)
        else:
            if _HOLD_SNAP_BACKUP is not None:
                ts.use_snap = _HOLD_SNAP_BACKUP["use_snap"]
                ts.snap_elements = _HOLD_SNAP_BACKUP["snap_elements"]
                ts.snap_target = _HOLD_SNAP_BACKUP["snap_target"]
                ts.use_snap_self = _HOLD_SNAP_BACKUP["use_snap_self"]
                ts.use_snap_nonedit = _HOLD_SNAP_BACKUP["use_snap_nonedit"]
                ts.use_snap_translate = _HOLD_SNAP_BACKUP["use_snap_translate"]
                ts.use_snap_rotate = _HOLD_SNAP_BACKUP["use_snap_rotate"]
                ts.use_snap_scale = _HOLD_SNAP_BACKUP["use_snap_scale"]
                _HOLD_SNAP_BACKUP = None
                _redraw_view3d_areas(context)
        return {"FINISHED"}


class MAYA_UX_OT_maya_pivot_hold(bpy.types.Operator):
    """Maya-native Hold D Edit Pivot: works cleanly with Hold V/C/X (D+V, D+C, D+X) in any order."""

    bl_idname = "maya_ux.maya_pivot_hold"
    bl_label = "Maya Hold Edit Pivot"
    bl_options = {"REGISTER"}

    active: BoolProperty(name="Hold Active", default=True)

    def execute(self, context):
        global _HOLD_PIVOT_BACKUP
        if context.mode != "OBJECT":
            return {"PASS_THROUGH"}

        ts = context.scene.tool_settings
        if self.active:
            if _HOLD_PIVOT_BACKUP is None:
                _HOLD_PIVOT_BACKUP = {
                    "use_transform_data_origin": bool(ts.use_transform_data_origin),
                    "prev_tool": _get_current_tool_id(context),
                }
            ts.use_transform_data_origin = True
            if _HOLD_SNAP_BACKUP is not None:
                ts.snap_target = "ACTIVE"
                ts.use_snap_self = True
                ts.use_snap_nonedit = True

            if _HOLD_PIVOT_BACKUP["prev_tool"] == "builtin.select_box":
                try:
                    bpy.ops.wm.tool_set_by_id(name="builtin.move")
                except Exception:
                    pass
            space = getattr(context, "space_data", None)
            if space is not None and space.type == "VIEW_3D":
                space.show_gizmo = True
                space.show_gizmo_tool = True
            _redraw_view3d_areas(context)
        else:
            if _HOLD_PIVOT_BACKUP is not None:
                ts.use_transform_data_origin = _HOLD_PIVOT_BACKUP["use_transform_data_origin"]
                if _HOLD_SNAP_BACKUP is not None:
                    ts.use_snap_self = bool(ts.use_transform_data_origin)
                if _HOLD_PIVOT_BACKUP["prev_tool"] == "builtin.select_box":
                    try:
                        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
                    except Exception:
                        pass
                _HOLD_PIVOT_BACKUP = None
                _redraw_view3d_areas(context)
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_toggle_edit_pivot,
    MAYA_UX_OT_pivot_action,
    MAYA_UX_OT_maya_snap,
    MAYA_UX_OT_maya_snap_hold,
    MAYA_UX_OT_maya_pivot_hold,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    global _HOLD_SNAP_BACKUP, _HOLD_PIVOT_BACKUP
    _HOLD_SNAP_BACKUP = None
    _HOLD_PIVOT_BACKUP = None
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
