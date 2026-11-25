from __future__ import annotations

from math import hypot
import time

import bpy
from bpy.props import EnumProperty
from mathutils import Quaternion

from .preferences import get_prefs, is_macos_layout

_LAST_PERSP_STATE: dict[int, tuple] = {}
_DEFAULT_PERSP_ROT = Quaternion((0.7804827, 0.4835360, 0.2087036, 0.3368716)).normalized()
_ORTHO_AXIS_QUATS = tuple(
    q.normalized()
    for q in (
        Quaternion((1.0, 0.0, 0.0, 0.0)),
        Quaternion((0.0, 1.0, 0.0, 0.0)),
        Quaternion((0.7071068, 0.7071068, 0.0, 0.0)),
        Quaternion((0.0, 0.0, 0.7071068, 0.7071068)),
        Quaternion((0.5, 0.5, 0.5, 0.5)),
        Quaternion((0.5, 0.5, -0.5, -0.5)),
    )
)


VISUAL_PANE_AREAS = {
    "OUTLINER",
    "IMAGE_EDITOR",
    "GRAPH_EDITOR",
    "DOPESHEET_EDITOR",
    "NODE_EDITOR",
    "PROPERTIES",
    "NLA_EDITOR",
    "SEQUENCE_EDITOR",
    "CLIP_EDITOR",
    "FILE_BROWSER",
    "ASSET_BROWSER",
    "SPREADSHEET",
}

TEXT_SAFE_AREAS = {"TEXT_EDITOR", "CONSOLE"}


def pick_quadview_index(regions, mouse_xy: tuple[float, float] | None) -> int | None:
    """Return the index (0..3) of the Quad View region containing mouse_xy, or None."""
    if mouse_xy is None or not regions:
        return None
    mx, my = mouse_xy
    win_regions = [r for r in regions if getattr(r, "type", "WINDOW") == "WINDOW"]
    candidates = win_regions if win_regions else list(regions)
    for idx, reg in enumerate(candidates):
        if reg.x <= mx < (reg.x + reg.width) and reg.y <= my < (reg.y + reg.height):
            return idx
    return None


def _run_screen_op(context, area, op_callable, **kwargs):
    win = getattr(context, "window", None)
    screen = getattr(context, "screen", None)
    if area is not None and hasattr(context, "temp_override"):
        override_kwargs = {"area": area}
        if area.type == "VIEW_3D":
            win_reg = next((r for r in area.regions if r.type == "WINDOW"), None)
            if win_reg is not None:
                override_kwargs["region"] = win_reg
        if win is not None:
            override_kwargs["window"] = win
        if screen is not None:
            override_kwargs["screen"] = screen
        with context.temp_override(**override_kwargs):
            return op_callable(**kwargs)
    return op_callable(**kwargs)


def _snapshot_rv3d(rv3d) -> tuple | None:
    if rv3d is None:
        return None
    return (
        rv3d.view_location.copy(),
        rv3d.view_rotation.copy(),
        float(rv3d.view_distance),
        str(rv3d.view_perspective),
    )


def _is_ortho_axis_rotation(rot: Quaternion) -> bool:
    rot_norm = rot.normalized()
    return any(abs(rot_norm.dot(q)) > 0.999 for q in _ORTHO_AXIS_QUATS)


def save_quadview_persp_state(space, area_key: int | None):
    """Save the Top-Right Perspective quadrant camera state before leaving Quad View."""
    if area_key is None or space is None:
        return
    quads = list(getattr(space, "region_quadviews", []) or [])
    if len(quads) != 4:
        return
    snap = _snapshot_rv3d(quads[3])
    if snap is not None:
        loc, rot, dist, _persp = snap
        _LAST_PERSP_STATE[area_key] = (loc, rot, dist, "PERSP")


def ensure_quadview_persp(
    space,
    area_key: int | None = None,
    prev_single_state: tuple | None = None,
) -> bool:
    """Ensure Quad View's Top-Right quadrant (quads[3]) is unlocked Perspective (Maya 4-View)."""
    if space is None:
        return False
    quads = list(getattr(space, "region_quadviews", []) or [])
    if len(quads) != 4:
        return False

    persp_rv3d = quads[3]
    persp_rv3d.lock_rotation = False

    if prev_single_state is not None and prev_single_state[3] == "PERSP":
        loc, rot, dist, _ = prev_single_state
        persp_rv3d.view_location = loc.copy()
        persp_rv3d.view_rotation = rot.copy()
        persp_rv3d.view_distance = dist
        persp_rv3d.view_perspective = "PERSP"
        if area_key is not None:
            _LAST_PERSP_STATE[area_key] = (loc.copy(), rot.copy(), dist, "PERSP")
    elif area_key is not None and area_key in _LAST_PERSP_STATE:
        loc, rot, dist, _ = _LAST_PERSP_STATE[area_key]
        persp_rv3d.view_location = loc.copy()
        persp_rv3d.view_rotation = rot.copy()
        persp_rv3d.view_distance = dist
        persp_rv3d.view_perspective = "PERSP"
    else:
        persp_rv3d.view_perspective = "PERSP"
        if _is_ortho_axis_rotation(persp_rv3d.view_rotation):
            persp_rv3d.view_rotation = _DEFAULT_PERSP_ROT.copy()
    return True


def toggle_pane_or_quadview(context, mouse_xy: tuple[float, float] | None = None) -> set[str]:
    """Maya Tap-Space behavior: expand hovered Quad View pane, toggle Quad View, or maximize editor pane."""
    area = getattr(context, "area", None)
    if area is None:
        return {"CANCELLED"}

    if area.type in TEXT_SAFE_AREAS:
        return {"PASS_THROUGH"}

    screen = getattr(context, "screen", None)
    if area.type == "VIEW_3D":
        space = getattr(context, "space_data", None) or area.spaces.active
        if space is None:
            return {"CANCELLED"}

        if screen is not None and getattr(screen, "show_fullscreen", False):
            _run_screen_op(context, area, bpy.ops.screen.screen_full_area, use_hide_panels=False)
            area.tag_redraw()
            return {"FINISHED"}

        area_key = area.as_pointer()
        quads = list(getattr(space, "region_quadviews", []) or [])
        if len(quads) == 4:
            save_quadview_persp_state(space, area_key)
            win_regions = [r for r in area.regions if r.type == "WINDOW"]
            idx = pick_quadview_index(win_regions, mouse_xy)
            src_rv3d = None
            if idx is not None:
                if idx < len(win_regions) and getattr(win_regions[idx], "data", None) is not None:
                    src_rv3d = win_regions[idx].data
                elif idx < len(quads):
                    src_rv3d = quads[idx]
            snapshot = _snapshot_rv3d(src_rv3d)

            _run_screen_op(context, area, bpy.ops.screen.region_quadview)

            dst_rv3d = getattr(space, "region_3d", None)
            if snapshot is not None and dst_rv3d is not None:
                loc, rot, dist, persp = snapshot
                dst_rv3d.view_location = loc
                dst_rv3d.view_rotation = rot
                dst_rv3d.view_distance = dist
                if persp in {"PERSP", "ORTHO", "CAMERA"}:
                    dst_rv3d.view_perspective = persp

            area.tag_redraw()
            return {"FINISHED"}

        prev_state = _snapshot_rv3d(getattr(space, "region_3d", None))
        _run_screen_op(context, area, bpy.ops.screen.region_quadview)
        ensure_quadview_persp(space, area_key=area_key, prev_single_state=prev_state)
        area.tag_redraw()
        return {"FINISHED"}

    if area.type in VISUAL_PANE_AREAS:
        _run_screen_op(context, area, bpy.ops.screen.screen_full_area, use_hide_panels=False)
        area.tag_redraw()
        return {"FINISHED"}

    return {"PASS_THROUGH"}


def _find_view3d_target(context):
    area = getattr(context, "area", None)
    if area is not None and area.type == "VIEW_3D":
        return area, area.spaces.active
    screen = getattr(context, "screen", None)
    if screen is not None:
        for candidate in screen.areas:
            if candidate.type == "VIEW_3D":
                return candidate, candidate.spaces.active
    return None, None


class MAYA_UX_OT_hotbox_view(bpy.types.Operator):
    """Switch the active 3D Viewport to a Maya camera or orthographic view."""

    bl_idname = "maya_ux.hotbox_view"
    bl_label = "Maya Hotbox View"
    bl_options = {"REGISTER", "UNDO"}

    view_type: EnumProperty(
        name="View",
        items=[
            ("PERSP", "Persp", "Switch to Perspective view"),
            ("TOP", "Top", "Switch to Top orthographic view"),
            ("FRONT", "Front", "Switch to Front orthographic view"),
            ("SIDE", "Side", "Switch to Side (Right) orthographic view"),
            ("BACK", "Back", "Switch to Back orthographic view"),
            ("LEFT", "Left", "Switch to Left orthographic view"),
            ("BOTTOM", "Bottom", "Switch to Bottom orthographic view"),
            ("CAMERA", "Camera", "Switch to active Scene Camera view"),
        ],
        default="PERSP",
    )

    def execute(self, context):
        v3d_area, space = _find_view3d_target(context)
        if v3d_area is None or space is None or space.region_3d is None:
            return {"CANCELLED"}

        rv3d = space.region_3d
        if self.view_type == "PERSP":
            rv3d.view_perspective = "PERSP"
            v3d_area.tag_redraw()
            return {"FINISHED"}

        if self.view_type == "CAMERA":
            win_reg = next((r for r in v3d_area.regions if r.type == "WINDOW"), None)
            try:
                if win_reg is not None and hasattr(context, "temp_override"):
                    with context.temp_override(area=v3d_area, region=win_reg):
                        bpy.ops.view3d.view_camera()
                else:
                    rv3d.view_perspective = "CAMERA"
            except Exception:
                rv3d.view_perspective = "CAMERA"
            v3d_area.tag_redraw()
            return {"FINISHED"}

        axis = "RIGHT" if self.view_type == "SIDE" else self.view_type
        win_reg = next((r for r in v3d_area.regions if r.type == "WINDOW"), None)
        try:
            if win_reg is not None and hasattr(context, "temp_override"):
                with context.temp_override(area=v3d_area, region=win_reg):
                    bpy.ops.view3d.view_axis(type=axis)
            else:
                rv3d.view_perspective = "ORTHO"
        except Exception:
            rv3d.view_perspective = "ORTHO"

        v3d_area.tag_redraw()
        return {"FINISHED"}


class MAYA_UX_OT_hotbox_popup(bpy.types.Operator):
    """Floating Maya Hotbox giving rapid access to Menus, Modes, Views, Modeling, and Panels."""

    bl_idname = "maya_ux.hotbox_popup"
    bl_label = "Maya Hotbox"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        wm = getattr(context, "window_manager", None)
        if wm is None:
            return {"CANCELLED"}
        return wm.invoke_popup(self, width=660)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        is_mac = is_macos_layout(context)
        mod_ctrl = "⌃" if is_mac else "Ctrl"
        mod_cmd = "⌘" if is_mac else "Ctrl"
        mod_shift = "⇧" if is_mac else "Shift"
        obj = getattr(context, "active_object", None)
        obj_name = obj.name if obj else "No Selection"

        # Header
        hdr = layout.row()
        hdr.label(text="MAYA HOTBOX", icon="WINDOW")
        hdr.label(
            text=f"Tap Space: Pane/Quad  |  Hold Space: Hotbox  |  {mod_ctrl}+Space: Expert  |  Active: {obj_name}"
        )

        # ZONE 1 (North): Maya Top Menus Bar
        north = layout.box()
        top_row = north.row(align=False)

        file_col = top_row.column(align=True)
        file_col.label(text="File", icon="FILE_FOLDER")
        r = file_col.row(align=True)
        r.operator("maya_ux.new_clean_scene", text="New")
        r.operator("maya_ux.increment_save", text="Inc Save")
        r.operator("maya_ux.export_maya_fbx", text="FBX")
        r.operator("maya_ux.export_maya_obj", text="OBJ")

        edit_col = top_row.column(align=True)
        edit_col.label(text="Edit", icon="MODIFIER")
        r = edit_col.row(align=True)
        r.operator("maya_ux.duplicate_in_place", text=f"Dup {mod_cmd}D")
        r.operator("maya_ux.group_selected", text=f"Grp {mod_cmd}G")
        r.operator("maya_ux.freeze_transforms", text="Freeze")
        r.operator("maya_ux.delete_history", text="History")

        disp_col = top_row.column(align=True)
        disp_col.label(text="Display", icon="SHADING_SOLID")
        r = disp_col.row(align=True)
        r.operator("maya_ux.set_shading", text="Wire").shading_type = "WIREFRAME"
        r.operator("maya_ux.set_shading", text="Shade").shading_type = "SOLID"
        r.operator("maya_ux.set_shading", text="Mat").shading_type = "MATERIAL"
        r.operator("maya_ux.toggle_wireframe_on_shaded", text="W/S")
        r.operator("maya_ux.toggle_xray", text="X-Ray")
        r.operator("maya_ux.isolate_select", text="Iso")
        r.operator("maya_ux.toggle_poly_count_hud", text="HUD")

        # ZONE 2-4 (West / Center / East)
        mid = layout.row(align=False)

        # ZONE 2 (West): Selection Modes & Retopo
        west = mid.box()
        west.label(text="Modes & Retopo", icon="VERTEXSEL")
        wcol = west.column(align=True)
        wcol.operator("maya_ux.component_mode", text="Object Mode", icon="OBJECT_DATAMODE").mode = "OBJECT"
        wcol.operator("maya_ux.component_mode", text="Vertex (F9)", icon="VERTEXSEL").mode = "VERT"
        wcol.operator("maya_ux.component_mode", text="Edge (F10)", icon="EDGESEL").mode = "EDGE"
        wcol.operator("maya_ux.component_mode", text="Face (F11)", icon="FACESEL").mode = "FACE"
        wcol.operator("maya_ux.component_mode", text="Multi-Component", icon="UV_VERTEXSEL").mode = "MULTI"
        wcol.separator()
        wcol.operator("maya_ux.toggle_soft_select", text="Soft Select (B)", icon="PROP_ON")
        wcol.operator("maya_ux.make_live", text="Make Live", icon="SNAP_FACE")
        wcol.operator("maya_ux.start_quad_draw", text="Quad Draw", icon="MESH_GRID")
        wcol.operator("maya_ux.target_weld", text="Target Weld", icon="AUTOMERGE_ON")

        # ZONE 3 (Center): Maya Camera Views & Pane Toggles
        center = mid.box()
        center.label(text="Maya Views & Panes", icon="VIEW3D")
        ccol = center.column(align=True)
        ccol.operator("maya_ux.hotbox_view", text="Persp View", icon="VIEW_PERSPECTIVE").view_type = "PERSP"
        r_ortho = ccol.row(align=True)
        r_ortho.operator("maya_ux.hotbox_view", text="Top").view_type = "TOP"
        r_ortho.operator("maya_ux.hotbox_view", text="Front").view_type = "FRONT"
        r_ortho.operator("maya_ux.hotbox_view", text="Side").view_type = "SIDE"
        r_extra = ccol.row(align=True)
        r_extra.operator("maya_ux.hotbox_view", text="Back").view_type = "BACK"
        r_extra.operator("maya_ux.hotbox_view", text="Left").view_type = "LEFT"
        r_extra.operator("maya_ux.hotbox_view", text="Camera").view_type = "CAMERA"
        ccol.separator()
        ccol.operator("maya_ux.toggle_quad_view", text="Quad View / Single (Tap)", icon="VIEW_ORTHO")
        ccol.operator("maya_ux.expert_mode", text=f"Expert Mode ({mod_ctrl}+Space)", icon="FULLSCREEN_ENTER")
        ccol.operator("wm.call_menu_pie", text=f"View Marking Pie ({mod_shift}+Space)", icon="MESH_CIRCLE").name = (
            "VIEW3D_MT_maya_view_pie"
        )

        # ZONE 4 (East): Modeling, Pivot, LookDev
        east = mid.box()
        east.label(text="Modeling & Pivot", icon="TOOL_SETTINGS")
        ecol = east.column(align=True)
        ecol.operator("maya_ux.toggle_edit_pivot", text="Edit Pivot (D)", icon="ORIENTATION_CURSOR")
        rp = ecol.row(align=True)
        rp.operator("maya_ux.pivot_action", text="Center").action = "CENTER"
        rp.operator("maya_ux.pivot_action", text="Origin").action = "WORLD_ORIGIN"
        rp.operator("maya_ux.pivot_action", text="Bottom").action = "BOTTOM_CENTER"
        ecol.separator()
        rc = ecol.row(align=True)
        rc.operator("maya_ux.combine", text="Combine")
        rc.operator("maya_ux.separate", text="Separate")
        rs = ecol.row(align=True)
        rs.operator("maya_ux.smooth_preview", text="1 Rough").level = 1
        rs.operator("maya_ux.smooth_preview", text="2 Cage").level = 2
        rs.operator("maya_ux.smooth_preview", text="3 Smooth").level = 3
        ecol.separator()
        rl = ecol.row(align=True)
        rl.operator("maya_ux.assign_maya_material", text="Lambert1").preset = "LAMBERT1"
        rl.operator("maya_ux.assign_maya_material", text="UV Check").preset = "UV_CHECKER"
        rcam = ecol.row(align=True)
        rcam.operator("maya_ux.cam_from_view", text="Cam View")
        rcam.operator("maya_ux.setup_studio_lighting", text="3Pt Light")

        # ZONE 5 (South): Panels, Workspaces & Help
        south = layout.box()
        srow = south.row(align=True)
        srow.operator("maya_ux.toggle_channel_box", text=f"Channel Box ({mod_ctrl}+A)", icon="MENU_PANEL")
        for label, ws_id in (
            ("Maya Pro", "Maya Pro"),
            ("Layout", "Layout"),
            ("Modeling", "Modeling"),
            ("UV", "UV Editing"),
            ("Sculpt", "Sculpting"),
            ("Anim", "Animation"),
            ("Shading", "Shading"),
        ):
            srow.operator("maya_ux.create_maya_workspace", text=label).workspace_name = ws_id
        srow.operator("maya_ux.cheatsheet", text="Hotkeys ?", icon="HELP")


def _open_hotbox(context):
    area = getattr(context, "area", None)
    prefs = get_prefs(context)
    if prefs.spacebar_mode == "VIEW_PIE_ONLY" and area is not None and area.type == "VIEW_3D":
        bpy.ops.wm.call_menu_pie("INVOKE_DEFAULT", name="VIEW3D_MT_maya_view_pie")
        return
    bpy.ops.maya_ux.hotbox_popup("INVOKE_DEFAULT")


class MAYA_UX_OT_spacebar_maya(bpy.types.Operator):
    """Maya Spacebar: Tap to maximize/restore pane or Quad View; Hold to open Floating Hotbox."""

    bl_idname = "maya_ux.spacebar_maya"
    bl_label = "Maya Spacebar (Tap Pane / Hold Hotbox)"
    bl_options = {"REGISTER"}

    _timer = None
    _start_time: float = 0.0
    _start_xy: tuple[float, float] = (0.0, 0.0)
    _last_xy: tuple[float, float] = (0.0, 0.0)
    _hold_delay: float = 0.20

    def _cleanup(self, context):
        wm = getattr(context, "window_manager", None)
        if wm is not None and self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def invoke(self, context, event):
        prefs = get_prefs(context)
        sp_mode = getattr(prefs, "spacebar_mode", "HYBRID")
        if sp_mode == "DISABLED":
            return {"PASS_THROUGH"}

        area = getattr(context, "area", None)
        region = getattr(context, "region", None)
        if area is None or area.type in TEXT_SAFE_AREAS:
            return {"PASS_THROUGH"}
        if getattr(context, "mode", "") == "EDIT_TEXT":
            return {"PASS_THROUGH"}
        if region is not None and region.type == "TEMPORARY":
            return {"PASS_THROUGH"}
        if area.type != "VIEW_3D" and area.type not in VISUAL_PANE_AREAS:
            return {"PASS_THROUGH"}

        mouse_xy = (float(event.mouse_x), float(event.mouse_y))
        if sp_mode == "QUAD_ONLY":
            return toggle_pane_or_quadview(context, mouse_xy)
        if sp_mode == "VIEW_PIE_ONLY":
            if area.type == "VIEW_3D":
                bpy.ops.wm.call_menu_pie("INVOKE_DEFAULT", name="VIEW3D_MT_maya_view_pie")
            else:
                bpy.ops.maya_ux.hotbox_popup("INVOKE_DEFAULT")
            return {"FINISHED"}

        wm = context.window_manager
        self._start_time = time.monotonic()
        self._start_xy = mouse_xy
        self._last_xy = mouse_xy
        self._hold_delay = float(getattr(prefs, "hotbox_hold_delay", 0.20))
        self._timer = wm.event_timer_add(0.03, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "MOUSEMOVE":
            self._last_xy = (float(event.mouse_x), float(event.mouse_y))
            dx = self._last_xy[0] - self._start_xy[0]
            dy = self._last_xy[1] - self._start_xy[1]
            if hypot(dx, dy) >= 14.0:
                self._cleanup(context)
                _open_hotbox(context)
                return {"FINISHED"}
            return {"RUNNING_MODAL"}

        if event.type == "TIMER":
            if (time.monotonic() - self._start_time) >= self._hold_delay:
                self._cleanup(context)
                _open_hotbox(context)
                return {"FINISHED"}
            return {"RUNNING_MODAL"}

        if event.type in {"ESC", "RIGHTMOUSE"}:
            self._cleanup(context)
            return {"CANCELLED"}

        if event.type == "SPACE" and event.value == "RELEASE":
            self._cleanup(context)
            toggle_pane_or_quadview(context, self._last_xy)
            return {"FINISHED"}

        return {"RUNNING_MODAL"}


_CLASSES = (
    MAYA_UX_OT_hotbox_view,
    MAYA_UX_OT_hotbox_popup,
    MAYA_UX_OT_spacebar_maya,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
