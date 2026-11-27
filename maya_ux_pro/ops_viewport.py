from __future__ import annotations

import os
import re

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Quaternion, Vector

# Tracks last-hidden object names per scene name for Maya-style H / Ctrl+Shift+H toggle.
_LAST_HIDDEN_OBJECTS: dict[str, list[str]] = {}

# Tracks active tool & optional MMB constraint lock for Maya Smart MMB drag.
_ACTIVE_TOOL_ID: str = "builtin.select_box"
_EXPLICIT_SELECT_TOOL: bool = False
_MMB_LOCKED_AXIS: tuple[bool, bool, bool] | None = None

# Per-area camera navigation history for Maya [ / ] view undo/redo.
_CAM_HISTORY: dict[int, dict] = {}

_BG_PRESETS = (
    ("SINGLE_COLOR", (0.215, 0.215, 0.215), (0.215, 0.215, 0.215)),
    ("LINEAR", (0.38, 0.43, 0.50), (0.14, 0.16, 0.19)),
    ("SINGLE_COLOR", (0.58, 0.58, 0.58), (0.58, 0.58, 0.58)),
    ("SINGLE_COLOR", (0.09, 0.09, 0.09), (0.09, 0.09, 0.09)),
)
_BG_INDEX = 0


def _view_state_from_rv3d(rv3d: bpy.types.RegionView3D) -> tuple:
    return (
        rv3d.view_location.copy(),
        rv3d.view_rotation.copy(),
        float(rv3d.view_distance),
        str(rv3d.view_perspective),
    )


def _states_equal(a: tuple, b: tuple) -> bool:
    return (
        (a[0] - b[0]).length < 1e-4
        and abs(a[1].dot(b[1])) > 0.9999
        and abs(a[2] - b[2]) < 1e-4
        and a[3] == b[3]
    )


def record_view_state(area_key: int, loc: Vector, rot: Quaternion, dist: float, persp: str):
    """Push a camera state onto the undo stack for area_key."""
    state = (loc.copy(), rot.copy(), float(dist), str(persp))
    entry = _CAM_HISTORY.setdefault(area_key, {"stack": [], "idx": -1})
    stack: list = entry["stack"]
    idx: int = entry["idx"]

    if 0 <= idx < len(stack) and _states_equal(stack[idx], state):
        return

    if idx < len(stack) - 1:
        del stack[idx + 1 :]
    stack.append(state)
    if len(stack) > 40:
        stack.pop(0)
    entry["idx"] = len(stack) - 1


def _cam_history_timer():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return 0.5
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            rv3d = getattr(space, "region_3d", None)
            if rv3d is not None:
                record_view_state(
                    area.as_pointer(),
                    rv3d.view_location,
                    rv3d.view_rotation,
                    rv3d.view_distance,
                    rv3d.view_perspective,
                )
    return 0.5


def _get_view3d_space(context) -> bpy.types.SpaceView3D | None:
    space = getattr(context, "space_data", None)
    if space is not None and space.type == "VIEW_3D":
        return space
    screen = getattr(context, "screen", None)
    if screen is not None:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                return area.spaces.active
    return None


def _show_gizmo_for_tool(space, tool_id: str):
    if space is None or tool_id not in {"builtin.move", "builtin.rotate", "builtin.scale", "builtin.transform"}:
        return
    space.show_gizmo = True
    if tool_id == "builtin.move":
        space.show_gizmo_object_translate = True
    elif tool_id == "builtin.rotate":
        space.show_gizmo_object_rotate = True
    elif tool_id == "builtin.scale":
        space.show_gizmo_object_scale = True
    elif tool_id == "builtin.transform":
        space.show_gizmo_object_translate = True
        space.show_gizmo_object_rotate = True
        space.show_gizmo_object_scale = True


def _sync_tool_after_mode_switch(context, prev_tool: str):
    if prev_tool not in {"builtin.move", "builtin.rotate", "builtin.scale", "builtin.transform", "builtin.select_box"}:
        return
    try:
        bpy.ops.wm.tool_set_by_id(name=prev_tool)
    except Exception:
        pass
    _show_gizmo_for_tool(_get_view3d_space(context), prev_tool)


class MAYA_UX_OT_set_tool(bpy.types.Operator):
    """Switch active tool (Q/W/E/R) and ensure transform gizmos are visible for W/E/R."""

    bl_idname = "maya_ux.set_tool"
    bl_label = "Maya Set Tool"
    bl_options = {"REGISTER"}

    tool_id: StringProperty(name="Tool ID", default="builtin.select_box")

    def execute(self, context):
        global _ACTIVE_TOOL_ID, _EXPLICIT_SELECT_TOOL, _MMB_LOCKED_AXIS

        try:
            bpy.ops.wm.tool_set_by_id(name=self.tool_id)
        except Exception as exc:
            self.report({"WARNING"}, f"Could not activate tool {self.tool_id}: {exc}")
            return {"CANCELLED"}

        _ACTIVE_TOOL_ID = self.tool_id
        _EXPLICIT_SELECT_TOOL = self.tool_id == "builtin.select_box"
        _MMB_LOCKED_AXIS = None

        _show_gizmo_for_tool(_get_view3d_space(context), self.tool_id)
        return {"FINISHED"}


def resolve_gizmo_size_delta(delta: int, auto_mode: bool = False, event=None) -> int | None:
    """Resolve gizmo size step across Italian ISO (* / _) and US ANSI (+ / -) Shift bindings."""
    char = ""
    if event is not None:
        char = getattr(event, "unicode", "") or getattr(event, "ascii", "")
    if auto_mode:
        step = abs(int(delta)) or 10
        if char in {"+", "*"}:
            return step
        if char in {"-", "_"}:
            return -step
        return None
    if char == "?":
        return None
    return int(delta)


class MAYA_UX_OT_gizmo_size(bpy.types.Operator):
    """Adjust viewport transform gizmo size like Maya +/- and Shift++ / Shift+- keys."""

    bl_idname = "maya_ux.gizmo_size"
    bl_label = "Adjust Gizmo Size"
    bl_options = {"REGISTER"}

    delta: IntProperty(name="Delta", default=10)
    auto_mode: BoolProperty(name="Auto Layout Detect", default=False)

    def _apply_delta(self, context, step: int):
        view_prefs = context.preferences.view
        new_size = max(20, min(200, int(view_prefs.gizmo_size) + int(step)))
        view_prefs.gizmo_size = new_size
        wm = getattr(context, "window_manager", None)
        if wm is not None:
            for win in wm.windows:
                for area in win.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        self.report({"INFO"}, f"Gizmo Size: {new_size}")
        return {"FINISHED"}

    def invoke(self, context, event):
        step = resolve_gizmo_size_delta(self.delta, self.auto_mode, event)
        if step is None:
            return {"PASS_THROUGH"}
        return self._apply_delta(context, step)

    def execute(self, context):
        return self._apply_delta(context, self.delta)


class MAYA_UX_OT_set_shading(bpy.types.Operator):
    """Switch 3D Viewport shading mode (4=Wireframe, 5=Solid, 6=Material, 7=Rendered)."""

    bl_idname = "maya_ux.set_shading"
    bl_label = "Maya Set Shading"
    bl_options = {"REGISTER"}

    shading_type: EnumProperty(
        name="Shading Type",
        items=[
            ("WIREFRAME", "Wireframe (4)", "Wireframe display"),
            ("SOLID", "Solid (5)", "Shaded solid display"),
            ("MATERIAL", "Material (6)", "Textured / Material preview"),
            ("RENDERED", "Rendered (7)", "Rendered with scene lights"),
        ],
        default="SOLID",
    )

    def execute(self, context):
        space = _get_view3d_space(context)
        if space is None:
            self.report({"WARNING"}, "No 3D Viewport found")
            return {"CANCELLED"}
        space.shading.type = self.shading_type
        if self.shading_type == "RENDERED":
            space.shading.use_scene_lights = True
        return {"FINISHED"}


class MAYA_UX_OT_toggle_wireframe_on_shaded(bpy.types.Operator):
    """Toggle Wireframe on Shaded overlay (Alt+5)."""

    bl_idname = "maya_ux.toggle_wireframe_on_shaded"
    bl_label = "Toggle Wireframe on Shaded"
    bl_options = {"REGISTER"}

    def execute(self, context):
        space = _get_view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        space.overlay.show_wireframes = not space.overlay.show_wireframes
        return {"FINISHED"}


class MAYA_UX_OT_toggle_xray(bpy.types.Operator):
    """Toggle Viewport X-Ray shading (Alt+X)."""

    bl_idname = "maya_ux.toggle_xray"
    bl_label = "Toggle X-Ray"
    bl_options = {"REGISTER"}

    def execute(self, context):
        space = _get_view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        space.shading.show_xray = not space.shading.show_xray
        return {"FINISHED"}


class MAYA_UX_OT_isolate_select(bpy.types.Operator):
    """Toggle Maya-style Isolate Select (Local View) without reframing camera."""

    bl_idname = "maya_ux.isolate_select"
    bl_label = "Isolate Select"
    bl_options = {"REGISTER"}

    def execute(self, context):
        space = _get_view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        if space.local_view is None and not context.selected_objects:
            self.report({"WARNING"}, "Select at least one object to isolate")
            return {"CANCELLED"}
        bpy.ops.view3d.localview(frame_selected=False)
        return {"FINISHED"}


class MAYA_UX_OT_smart_hide(bpy.types.Operator):
    """Maya-style Hide (Ctrl+H), Unhide (Shift+H), and Smart Toggle (H)."""

    bl_idname = "maya_ux.smart_hide"
    bl_label = "Maya Smart Hide"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        name="Action",
        items=[
            ("HIDE", "Hide Selected", "Hide selected objects or components"),
            ("UNHIDE", "Unhide All", "Show hidden objects or components"),
            ("TOGGLE", "Smart Toggle", "Hide selected, or unhide last-hidden if nothing selected"),
            ("HIDE_UNSELECTED", "Hide Unselected", "Hide everything except current selection (Alt+H)"),
            ("UNHIDE_LAST", "Show Last Hidden", "Unhide last hidden selection (Ctrl+Shift+H)"),
        ],
        default="TOGGLE",
    )

    def execute(self, context):
        if context.mode == "EDIT_MESH":
            if self.action in {"UNHIDE", "UNHIDE_LAST"}:
                bpy.ops.mesh.reveal(select=False)
            elif self.action == "HIDE":
                bpy.ops.mesh.hide(unselected=False)
            elif self.action == "HIDE_UNSELECTED":
                bpy.ops.mesh.hide(unselected=True)
            else:
                # Toggle in edit mode: hide selected; if nothing selected, reveal hidden
                mesh = context.active_object.data if context.active_object else None
                if mesh is not None:
                    bpy.ops.object.mode_set(mode="OBJECT")
                    has_sel = any(v.select for v in mesh.vertices) or any(e.select for e in mesh.edges) or any(p.select for p in mesh.polygons)
                    bpy.ops.object.mode_set(mode="EDIT")
                    if has_sel:
                        bpy.ops.mesh.hide(unselected=False)
                    else:
                        bpy.ops.mesh.reveal(select=False)
            return {"FINISHED"}

        scene_key = context.scene.name if context.scene else "__default__"
        selected = list(context.selected_objects)

        if self.action == "HIDE_UNSELECTED":
            if not selected:
                self.report({"WARNING"}, "Select at least one object to keep visible")
                return {"CANCELLED"}
            sel_set = set(selected)
            names = []
            for obj in context.view_layer.objects:
                if obj not in sel_set and not obj.hide_get():
                    obj.hide_set(True)
                    names.append(obj.name)
            if names:
                _LAST_HIDDEN_OBJECTS[scene_key] = names
            return {"FINISHED"}

        if self.action == "UNHIDE_LAST":
            last_names = _LAST_HIDDEN_OBJECTS.pop(scene_key, [])
            for name in last_names:
                obj = bpy.data.objects.get(name)
                if obj is not None and obj.name in context.view_layer.objects:
                    obj.hide_set(False)
                    obj.select_set(True)
            return {"FINISHED"}

        if self.action == "HIDE" or (self.action == "TOGGLE" and selected):
            if not selected:
                self.report({"INFO"}, "Nothing selected to hide")
                return {"CANCELLED"}
            names = []
            for obj in selected:
                obj.hide_set(True)
                names.append(obj.name)
            _LAST_HIDDEN_OBJECTS[scene_key] = names
            return {"FINISHED"}

        if self.action == "TOGGLE":
            last_names = _LAST_HIDDEN_OBJECTS.pop(scene_key, [])
            restored = 0
            for name in last_names:
                obj = bpy.data.objects.get(name)
                if obj is not None and obj.name in context.view_layer.objects:
                    obj.hide_set(False)
                    obj.select_set(True)
                    restored += 1
            if restored > 0:
                return {"FINISHED"}

        # UNHIDE (or TOGGLE fallback when no cached batch)
        for obj in context.view_layer.objects:
            if obj.hide_get():
                obj.hide_set(False)
        return {"FINISHED"}


class MAYA_UX_OT_toggle_quad_view(bpy.types.Operator):
    """Toggle 4-way Quad View in the active 3D Viewport."""

    bl_idname = "maya_ux.toggle_quad_view"
    bl_label = "Toggle Quad View"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from .ops_hotbox import _snapshot_rv3d, ensure_quadview_persp, save_quadview_persp_state

        space = _get_view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        area = getattr(context, "area", None)
        area_key = area.as_pointer() if area is not None else None
        was_quad = len(getattr(space, "region_quadviews", []) or []) == 4
        if was_quad:
            save_quadview_persp_state(space, area_key)
            prev_state = None
        else:
            prev_state = _snapshot_rv3d(getattr(space, "region_3d", None))
        try:
            bpy.ops.screen.region_quadview()
        except Exception as exc:
            self.report({"WARNING"}, f"Quad View unavailable in current context: {exc}")
            return {"CANCELLED"}
        if not was_quad:
            ensure_quadview_persp(space, area_key=area_key, prev_single_state=prev_state)
        return {"FINISHED"}


class MAYA_UX_OT_component_mode(bpy.types.Operator):
    """Switch seamlessly between Object Mode and Vertex/Edge/Face/Multi component modes."""

    bl_idname = "maya_ux.component_mode"
    bl_label = "Maya Component Mode"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="Mode",
        items=[
            ("OBJECT", "Object Mode", "Switch to Object Mode"),
            ("VERT", "Vertex", "Switch to Vertex Edit Mode"),
            ("EDGE", "Edge", "Switch to Edge Edit Mode"),
            ("FACE", "Face", "Switch to Face Edit Mode"),
            ("MULTI", "Multi-Component", "Switch to Vertex+Edge+Face Edit Mode"),
            ("TOGGLE", "Toggle Object/Component", "Toggle between Object Mode and Edit Mode (F8)"),
        ],
        default="OBJECT",
    )

    def execute(self, context):
        from . import ops_selection

        obj = context.active_object
        prev_tool = _get_active_tool_id(context)
        if self.mode == "TOGGLE":
            if obj is None or obj.type != "MESH":
                return {"CANCELLED"}
            target = "OBJECT" if context.mode == "EDIT_MESH" else "EDIT"
            bpy.ops.object.mode_set(mode=target)
            _sync_tool_after_mode_switch(context, prev_tool)
            ops_selection.sync_component_selection_display(context, force=True)
            return {"FINISHED"}

        if self.mode == "OBJECT":
            if obj is not None and context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
                _sync_tool_after_mode_switch(context, prev_tool)
            ops_selection.sync_component_selection_display(context, force=True)
            return {"FINISHED"}

        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, "Select a Mesh object for component editing")
            return {"CANCELLED"}

        mode_switched = False
        if context.mode != "EDIT_MESH":
            bpy.ops.object.mode_set(mode="EDIT")
            mode_switched = True

        mode_map = {
            "VERT": (True, False, False),
            "EDGE": (False, True, False),
            "FACE": (False, False, True),
            "MULTI": (True, True, True),
        }
        context.tool_settings.mesh_select_mode = mode_map[self.mode]
        if mode_switched:
            _sync_tool_after_mode_switch(context, prev_tool)
        if self.mode == "FACE":
            from .preferences import get_prefs

            if bool(getattr(get_prefs(context), "maya_face_center_select", True)):
                sp = _get_view3d_space(context)
                if sp is not None:
                    sp.overlay.show_face_center = True
        ops_selection.sync_component_selection_display(context, force=True)
        return {"FINISHED"}


class MAYA_UX_OT_expert_mode(bpy.types.Operator):
    """Toggle Maya Expert Mode — maximize 3D Viewport hiding panels (Ctrl+Space)."""

    bl_idname = "maya_ux.expert_mode"
    bl_label = "Toggle Expert Mode"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            bpy.ops.screen.screen_full_area(use_hide_panels=True)
        except Exception as exc:
            self.report({"WARNING"}, f"Expert Mode unavailable: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


class MAYA_UX_OT_toggle_channel_box(bpy.types.Operator):
    """Toggle 3D Viewport N-Panel / Channel Box (Maya Ctrl+A)."""

    bl_idname = "maya_ux.toggle_channel_box"
    bl_label = "Toggle Channel Box"
    bl_options = {"REGISTER"}

    def execute(self, context):
        space = _get_view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        space.show_region_ui = not space.show_region_ui
        return {"FINISHED"}


class MAYA_UX_OT_cycle_viewport_bg(bpy.types.Operator):
    """Cycle 3D Viewport background color/gradient presets (Maya Alt+B)."""

    bl_idname = "maya_ux.cycle_viewport_bg"
    bl_label = "Cycle Viewport Background"
    bl_options = {"REGISTER"}

    def execute(self, context):
        global _BG_INDEX
        _BG_INDEX = (_BG_INDEX + 1) % len(_BG_PRESETS)
        bg_type, high_col, grad_col = _BG_PRESETS[_BG_INDEX]
        gradients = context.preferences.themes[0].view_3d.space.gradients
        gradients.background_type = bg_type
        gradients.high_gradient = high_col
        gradients.gradient = grad_col
        return {"FINISHED"}


def _step_camera_history(context, step: int) -> bool:
    area = getattr(context, "area", None)
    space = _get_view3d_space(context)
    if space is None or area is None:
        return False
    rv3d = getattr(space, "region_3d", None)
    if rv3d is None:
        return False
    entry = _CAM_HISTORY.get(area.as_pointer())
    if not entry or not entry["stack"]:
        return False
    new_idx = entry["idx"] + step
    if not (0 <= new_idx < len(entry["stack"])):
        return False
    entry["idx"] = new_idx
    loc, rot, dist, persp = entry["stack"][new_idx]
    rv3d.view_location = loc.copy()
    rv3d.view_rotation = rot.copy()
    rv3d.view_distance = dist
    rv3d.view_perspective = persp
    return True


class MAYA_UX_OT_camera_view_undo(bpy.types.Operator):
    """Undo 3D Viewport camera tumble/pan/zoom (Maya '[')."""

    bl_idname = "maya_ux.camera_view_undo"
    bl_label = "Camera View Undo"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not _step_camera_history(context, -1):
            return {"CANCELLED"}
        return {"FINISHED"}


class MAYA_UX_OT_camera_view_redo(bpy.types.Operator):
    """Redo 3D Viewport camera tumble/pan/zoom (Maya ']')."""

    bl_idname = "maya_ux.camera_view_redo"
    bl_label = "Camera View Redo"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not _step_camera_history(context, 1):
            return {"CANCELLED"}
        return {"FINISHED"}


class MAYA_UX_OT_increment_save(bpy.types.Operator):
    """Save file with an incremented version suffix (Maya Ctrl+Alt+S)."""

    bl_idname = "maya_ux.increment_save"
    bl_label = "Increment & Save"
    bl_options = {"REGISTER"}

    filepath_override: StringProperty(name="Filepath Override", default="", options={"HIDDEN"})

    def execute(self, context):
        cur_path = self.filepath_override or bpy.data.filepath
        if not cur_path:
            self.report({"WARNING"}, "Save the .blend file once before Increment & Save")
            return {"CANCELLED"}

        directory = os.path.dirname(cur_path)
        filename = os.path.basename(cur_path)
        stem, ext = os.path.splitext(filename)
        if not ext:
            ext = ".blend"

        match = re.match(r"^(.*?)(\d+)$", stem)
        if match:
            prefix, digits = match.group(1), match.group(2)
            width = len(digits)
            num = int(digits) + 1
        else:
            prefix = f"{stem}_"
            width = 4
            num = 1

        new_path = os.path.join(directory, f"{prefix}{num:0{width}d}{ext}")
        while os.path.exists(new_path):
            num += 1
            new_path = os.path.join(directory, f"{prefix}{num:0{width}d}{ext}")

        bpy.ops.wm.save_as_mainfile(filepath=new_path)
        self.report({"INFO"}, f"Saved {os.path.basename(new_path)}")
        return {"FINISHED"}


class MAYA_UX_OT_default_display(bpy.types.Operator):
    """Reset to Maya Default Quality Display (0): Smooth Preview 1 + Shaded Solid."""

    bl_idname = "maya_ux.default_display"
    bl_label = "Default Quality Display (0)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if not meshes and context.active_object and context.active_object.type == "MESH":
            meshes = [context.active_object]
        if meshes:
            bpy.ops.maya_ux.smooth_preview(level=1)

        space = _get_view3d_space(context)
        if space is not None:
            space.shading.type = "SOLID"
        return {"FINISHED"}


class MAYA_UX_OT_frame_all_views(bpy.types.Operator):
    """Frame Selected (Shift+F) or Frame All (Shift+A) across all visible 3D Viewports."""

    bl_idname = "maya_ux.frame_all_views"
    bl_label = "Frame All Views"
    bl_options = {"REGISTER"}

    selected_only: BoolProperty(name="Selected Only", default=False)

    def execute(self, context):
        screen = getattr(context, "screen", None)
        if screen is None:
            return {"CANCELLED"}

        framed = 0
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            with context.temp_override(area=area, region=region):
                if self.selected_only:
                    bpy.ops.view3d.view_selected()
                else:
                    bpy.ops.view3d.view_all()
            framed += 1
        return {"FINISHED"} if framed else {"CANCELLED"}


class MAYA_UX_OT_screen_nudge(bpy.types.Operator):
    """Nudge selected objects or vertices in screen space (Maya Option + Arrow keys)."""

    bl_idname = "maya_ux.screen_nudge"
    bl_label = "Screen-Space Nudge"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        name="Direction",
        items=[
            ("UP", "Up", "Nudge up"),
            ("DOWN", "Down", "Nudge down"),
            ("LEFT", "Left", "Nudge left"),
            ("RIGHT", "Right", "Nudge right"),
        ],
        default="UP",
    )
    step: FloatProperty(name="Step", default=0.1, min=0.001, max=100.0)

    def execute(self, context):
        space = _get_view3d_space(context)
        rv3d = getattr(space, "region_3d", None) if space is not None else None
        if rv3d is not None:
            rot = rv3d.view_rotation
            right = (rot @ Vector((1.0, 0.0, 0.0))).normalized()
            up = (rot @ Vector((0.0, 1.0, 0.0))).normalized()
        else:
            right = Vector((1.0, 0.0, 0.0))
            up = Vector((0.0, 0.0, 1.0))

        dir_map = {
            "UP": up,
            "DOWN": -up,
            "RIGHT": right,
            "LEFT": -right,
        }
        delta = dir_map[self.direction] * self.step

        if context.mode == "EDIT_MESH":
            bpy.ops.transform.translate(value=tuple(delta))
            return {"FINISHED"}

        selected = list(context.selected_objects)
        if not selected:
            return {"CANCELLED"}
        for obj in selected:
            obj.location += delta
        return {"FINISHED"}


_TRANSFORM_TOOL_MAP = {
    "builtin.move": "TRANSLATE",
    "builtin.rotate": "ROTATE",
    "builtin.scale": "RESIZE",
}
_OP_TO_ACTION = {
    "TRANSFORM_OT_translate": "TRANSLATE",
    "TRANSFORM_OT_rotate": "ROTATE",
    "TRANSFORM_OT_resize": "RESIZE",
}
_ACTION_TO_OP = {v: k for k, v in _OP_TO_ACTION.items()}


def _has_selection(context) -> bool:
    mode = getattr(context, "mode", "OBJECT")
    if mode == "OBJECT":
        return bool(getattr(context, "selected_objects", None))
    if mode == "EDIT_MESH":
        objs = getattr(context, "objects_in_mode", None)
        if not objs:
            active = getattr(context, "active_object", None)
            objs = [active] if active is not None else []
        for obj in objs:
            if obj is None or obj.type != "MESH":
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            if any(v.select for v in bm.verts) or any(e.select for e in bm.edges) or any(f.select for f in bm.faces):
                return True
        return False
    if mode == "EDIT_CURVE":
        objs = getattr(context, "objects_in_mode", None) or ([getattr(context, "active_object", None)] if getattr(context, "active_object", None) else [])
        for obj in objs:
            if obj is None or obj.type != "CURVE":
                continue
            for spline in obj.data.splines:
                if any(p.select for p in spline.points) or any(bp.select_control_point for bp in spline.bezier_points):
                    return True
        return False
    if mode == "EDIT_ARMATURE":
        return bool(getattr(context, "selected_editable_bones", None) or getattr(context, "selected_bones", None))
    if mode == "POSE":
        return bool(getattr(context, "selected_pose_bones", None))
    return getattr(context, "active_object", None) is not None


def _get_active_tool_id(context) -> str:
    ws = getattr(context, "workspace", None)
    if ws is not None and hasattr(ws, "tools"):
        try:
            tool = ws.tools.from_space_view3d_mode(context.mode)
            if tool is not None and tool.idname:
                return tool.idname
        except Exception:
            pass
    return _ACTIVE_TOOL_ID


def _resolve_effective_tool_id(context, tool_override: str = "") -> str:
    """Resolve the active transform tool ID, carrying Object Move/Rotate/Scale across Component Mode."""
    tool_id = tool_override or _get_active_tool_id(context)
    if tool_id in _TRANSFORM_TOOL_MAP or tool_id == "builtin.transform":
        return tool_id
    if getattr(context.scene.tool_settings, "use_transform_data_origin", False):
        return "builtin.move"
    if not tool_override and not _EXPLICIT_SELECT_TOOL and getattr(context, "mode", "OBJECT") != "OBJECT":
        if _ACTIVE_TOOL_ID in _TRANSFORM_TOOL_MAP or _ACTIVE_TOOL_ID == "builtin.transform":
            return _ACTIVE_TOOL_ID
        ws = getattr(context, "workspace", None)
        if ws is not None and hasattr(ws, "tools"):
            try:
                obj_tool = ws.tools.from_space_view3d_mode("OBJECT")
                if obj_tool is not None and (
                    obj_tool.idname in _TRANSFORM_TOOL_MAP or obj_tool.idname == "builtin.transform"
                ):
                    return obj_tool.idname
            except Exception:
                pass
    return tool_id


def resolve_mmb_action(context, tool_override: str = "") -> tuple[str, tuple[bool, bool, bool]]:
    """Determine Maya MMB action ('PAN' | 'TRANSLATE' | 'ROTATE' | 'RESIZE') and constraint axis."""
    if not _has_selection(context):
        return ("PAN", (False, False, False))

    tool_id = _resolve_effective_tool_id(context, tool_override)
    if tool_id not in _TRANSFORM_TOOL_MAP and tool_id != "builtin.transform":
        return ("PAN", (False, False, False))

    wm = getattr(context, "window_manager", None)
    last_op = wm.operators[-1] if (wm is not None and len(wm.operators) > 0) else None

    if tool_id == "builtin.transform":
        if last_op is not None and last_op.bl_idname in _OP_TO_ACTION:
            action = _OP_TO_ACTION[last_op.bl_idname]
        else:
            action = "TRANSLATE"
    else:
        action = _TRANSFORM_TOOL_MAP[tool_id]

    if _MMB_LOCKED_AXIS is not None:
        return (action, _MMB_LOCKED_AXIS)

    if last_op is not None and last_op.bl_idname == _ACTION_TO_OP.get(action):
        c_axis = getattr(last_op.properties, "constraint_axis", None)
        if c_axis is not None:
            axis_tuple = (bool(c_axis[0]), bool(c_axis[1]), bool(c_axis[2]))
            if any(axis_tuple):
                return (action, axis_tuple)

    return (action, (False, False, False))


class MAYA_UX_OT_mmb_smart_drag(bpy.types.Operator):
    """Maya Smart MMB: Pan when empty or in Select tool; Move/Rotate/Scale globally or along last axis when transforming."""

    bl_idname = "maya_ux.mmb_smart_drag"
    bl_label = "Maya Smart MMB Drag"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        action, axis = resolve_mmb_action(context)
        if action == "PAN":
            return bpy.ops.view3d.move("INVOKE_DEFAULT")
        if getattr(context, "mode", "OBJECT") != "OBJECT":
            cur_tool = _get_active_tool_id(context)
            if cur_tool not in _TRANSFORM_TOOL_MAP and cur_tool != "builtin.transform":
                eff_tool = _resolve_effective_tool_id(context)
                try:
                    bpy.ops.wm.tool_set_by_id(name=eff_tool)
                except Exception:
                    pass
        if action == "TRANSLATE":
            ts = context.scene.tool_settings
            if ts.use_snap:
                return bpy.ops.transform.translate(
                    "INVOKE_DEFAULT",
                    release_confirm=True,
                    constraint_axis=axis,
                    snap=True,
                    snap_elements=set(ts.snap_elements),
                    snap_target=("ACTIVE" if context.mode == "OBJECT" else "CENTER"),
                    use_snap_self=(True if context.mode != "OBJECT" else bool(ts.use_transform_data_origin)),
                    use_snap_nonedit=True,
                )
            return bpy.ops.transform.translate("INVOKE_DEFAULT", release_confirm=True, constraint_axis=axis)
        if action == "ROTATE":
            return bpy.ops.transform.rotate("INVOKE_DEFAULT", release_confirm=True, constraint_axis=axis)
        if action == "RESIZE":
            return bpy.ops.transform.resize("INVOKE_DEFAULT", release_confirm=True, constraint_axis=axis)
        return {"CANCELLED"}


class MAYA_UX_OT_set_mmb_axis(bpy.types.Operator):
    """Lock or clear the axis constraint used by Maya Smart MMB virtual drag."""

    bl_idname = "maya_ux.set_mmb_axis"
    bl_label = "Set MMB Axis Lock"
    bl_options = {"REGISTER"}

    axis: EnumProperty(
        name="Axis",
        items=[
            ("FREE", "Free / Global", "No axis constraint (Global/Free)"),
            ("X", "X", "Constrain MMB drag to X axis"),
            ("Y", "Y", "Constrain MMB drag to Blender Y axis"),
            ("Z", "Z", "Constrain MMB drag to Blender Z axis"),
        ],
        default="FREE",
    )

    def execute(self, context):
        global _MMB_LOCKED_AXIS
        axis_map = {
            "X": (True, False, False),
            "Y": (False, True, False),
            "Z": (False, False, True),
        }
        if self.axis == "FREE":
            _MMB_LOCKED_AXIS = None
        else:
            target = axis_map[self.axis]
            _MMB_LOCKED_AXIS = None if _MMB_LOCKED_AXIS == target else target
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_set_tool,
    MAYA_UX_OT_gizmo_size,
    MAYA_UX_OT_set_shading,
    MAYA_UX_OT_toggle_wireframe_on_shaded,
    MAYA_UX_OT_toggle_xray,
    MAYA_UX_OT_isolate_select,
    MAYA_UX_OT_smart_hide,
    MAYA_UX_OT_toggle_quad_view,
    MAYA_UX_OT_component_mode,
    MAYA_UX_OT_expert_mode,
    MAYA_UX_OT_toggle_channel_box,
    MAYA_UX_OT_cycle_viewport_bg,
    MAYA_UX_OT_camera_view_undo,
    MAYA_UX_OT_camera_view_redo,
    MAYA_UX_OT_increment_save,
    MAYA_UX_OT_default_display,
    MAYA_UX_OT_frame_all_views,
    MAYA_UX_OT_screen_nudge,
    MAYA_UX_OT_mmb_smart_drag,
    MAYA_UX_OT_set_mmb_axis,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    if not bpy.app.timers.is_registered(_cam_history_timer):
        bpy.app.timers.register(_cam_history_timer, first_interval=0.5, persistent=True)


def unregister():
    global _MMB_LOCKED_AXIS
    _MMB_LOCKED_AXIS = None
    if bpy.app.timers.is_registered(_cam_history_timer):
        bpy.app.timers.unregister(_cam_history_timer)
    _CAM_HISTORY.clear()
    _LAST_HIDDEN_OBJECTS.clear()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
