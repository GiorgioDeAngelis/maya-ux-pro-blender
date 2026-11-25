from __future__ import annotations

import json
import os

import bpy

# Optional test override so unit tests never touch user's real Blender config dir.
_BACKUP_PATH_OVERRIDE: str | None = None


def get_backup_path() -> str:
    """Return path to the setup backup JSON file."""
    if _BACKUP_PATH_OVERRIDE:
        return _BACKUP_PATH_OVERRIDE
    config_dir = bpy.utils.user_resource("CONFIG")
    return os.path.join(config_dir, "maya_ux_pro_backup.json")


def has_backup() -> bool:
    """Return True if a setup backup currently exists."""
    return os.path.isfile(get_backup_path())


def _keyconfig_preset_dir() -> str:
    return os.path.join(bpy.utils.resource_path("LOCAL"), "scripts", "presets", "keyconfig")


def _resolve_keyconfig_filepath(name: str) -> str | None:
    """Resolve a keyconfig name (e.g. 'Blender', 'Industry_Compatible') to its preset filepath."""
    preset_dir = _keyconfig_preset_dir()
    candidates = [
        f"{name}.py",
        f"{name.replace(' ', '_')}.py",
    ]
    for filename in candidates:
        path = os.path.join(preset_dir, filename)
        if os.path.isfile(path):
            return path
    user_presets = bpy.utils.user_resource("SCRIPTS", path="presets/keyconfig")
    if user_presets:
        for filename in candidates:
            path = os.path.join(user_presets, filename)
            if os.path.isfile(path):
                return path
    return None


class MAYA_UX_OT_apply_maya_setup(bpy.types.Operator):
    """Back up current Blender config and apply Industry Compatible + Maya viewport settings."""

    bl_idname = "maya_ux.apply_maya_setup"
    bl_label = "Apply Maya Base Setup"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from . import keymap
        from .preferences import is_macos_layout

        prefs = context.preferences
        wm = context.window_manager
        backup_path = get_backup_path()

        # Save backup only if one is not already stored (preserve original state).
        if not os.path.isfile(backup_path):
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            ui_theme = prefs.themes[0].user_interface if prefs.themes else None
            v3d_theme = prefs.themes[0].view_3d if prefs.themes else None
            ts = context.scene.tool_settings
            snapshot = {
                "active_keyconfig": wm.keyconfigs.active.name if wm.keyconfigs.active else "Blender",
                "gizmo_size": int(prefs.view.gizmo_size),
                "use_rotate_around_active": bool(prefs.inputs.use_rotate_around_active),
                "use_zoom_to_mouse": bool(prefs.inputs.use_zoom_to_mouse),
                "use_auto_perspective": bool(prefs.inputs.use_auto_perspective),
                "use_mouse_emulate_3_button": bool(prefs.inputs.use_mouse_emulate_3_button),
                "invert_mouse_zoom": bool(prefs.inputs.invert_mouse_zoom),
                "view_zoom_axis": str(prefs.inputs.view_zoom_axis),
                "view_zoom_method": str(prefs.inputs.view_zoom_method),
                "snap_target": str(ts.snap_target),
                "use_snap_self": bool(ts.use_snap_self),
                "use_snap_nonedit": bool(ts.use_snap_nonedit),
            }
            if ui_theme is not None and v3d_theme is not None:
                snapshot.update(
                    {
                        "axis_x": list(ui_theme.axis_x),
                        "axis_y": list(ui_theme.axis_y),
                        "axis_z": list(ui_theme.axis_z),
                        "grid": list(v3d_theme.grid),
                        "grid_major": list(v3d_theme.grid_major),
                        "bg_type": str(v3d_theme.space.gradients.background_type),
                        "bg_high": list(v3d_theme.space.gradients.high_gradient),
                        "bg_grad": list(v3d_theme.space.gradients.gradient),
                        "v3d_object_active": list(v3d_theme.object_active),
                        "v3d_object_selected": list(v3d_theme.object_selected),
                        "v3d_wire": list(v3d_theme.wire),
                        "v3d_wire_edit": list(v3d_theme.wire_edit),
                        "v3d_vertex_select": list(v3d_theme.vertex_select),
                        "v3d_edge_select": list(v3d_theme.edge_select),
                        "v3d_face_select": list(v3d_theme.face_select),
                    }
                )
            with open(backup_path, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, indent=2)

        ic_path = _resolve_keyconfig_filepath("Industry_Compatible")
        if not ic_path:
            self.report({"ERROR"}, "Industry_Compatible keyconfig preset not found")
            return {"CANCELLED"}

        from . import ops_maya_axes
        from .preferences import get_prefs

        addon_prefs = get_prefs(context)
        bpy.ops.preferences.keyconfig_activate(filepath=ic_path)
        prefs.inputs.use_rotate_around_active = True
        prefs.inputs.use_zoom_to_mouse = True
        prefs.inputs.use_auto_perspective = False
        prefs.inputs.view_zoom_method = "DOLLY"
        prefs.inputs.view_zoom_axis = "VERTICAL"
        prefs.inputs.invert_mouse_zoom = bool(getattr(addon_prefs, "maya_invert_mouse_zoom", True))
        if is_macos_layout(context):
            # Ensure ⌥ Option + Click Orbit works cleanly without 3-button emulation conflict
            prefs.inputs.use_mouse_emulate_3_button = False
        prefs.view.gizmo_size = 85

        ts = context.scene.tool_settings
        ts.snap_target = "ACTIVE"
        ts.use_snap_self = False
        ts.use_snap_nonedit = True

        ops_maya_axes.apply_maya_grid_theme(context)
        if getattr(addon_prefs, "clean_maya_startup_layout", True):
            from . import ops_startup

            ops_startup.apply_clean_maya_ui(context, remove_timeline=not bpy.app.background)
        ops_maya_axes.apply_maya_axis_colors(bool(getattr(addon_prefs, "swap_axis_colors_yup", False)), context)

        keymap.rebuild_keymaps()
        self.report({"INFO"}, "Maya Base Setup applied (backup saved)")
        return {"FINISHED"}


class MAYA_UX_OT_restore_previous_setup(bpy.types.Operator):
    """Restore the keyconfig and viewport preferences saved prior to Apply Maya Base Setup."""

    bl_idname = "maya_ux.restore_previous_setup"
    bl_label = "Restore Previous Setup"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from . import keymap

        backup_path = get_backup_path()
        if not os.path.isfile(backup_path):
            self.report({"WARNING"}, "No Maya UX Pro backup found")
            return {"CANCELLED"}

        with open(backup_path, "r", encoding="utf-8") as fh:
            snapshot = json.load(fh)

        prefs = context.preferences
        prefs.view.gizmo_size = int(snapshot.get("gizmo_size", 75))
        prefs.inputs.use_rotate_around_active = bool(snapshot.get("use_rotate_around_active", False))
        prefs.inputs.use_zoom_to_mouse = bool(snapshot.get("use_zoom_to_mouse", False))
        prefs.inputs.use_auto_perspective = bool(snapshot.get("use_auto_perspective", True))
        if "use_mouse_emulate_3_button" in snapshot:
            prefs.inputs.use_mouse_emulate_3_button = bool(snapshot["use_mouse_emulate_3_button"])
        if "invert_mouse_zoom" in snapshot:
            prefs.inputs.invert_mouse_zoom = bool(snapshot["invert_mouse_zoom"])
        if "view_zoom_axis" in snapshot:
            prefs.inputs.view_zoom_axis = snapshot["view_zoom_axis"]
        if "view_zoom_method" in snapshot:
            prefs.inputs.view_zoom_method = snapshot["view_zoom_method"]

        ts = context.scene.tool_settings
        if "snap_target" in snapshot:
            ts.snap_target = snapshot["snap_target"]
        if "use_snap_self" in snapshot:
            ts.use_snap_self = bool(snapshot["use_snap_self"])
        if "use_snap_nonedit" in snapshot:
            ts.use_snap_nonedit = bool(snapshot["use_snap_nonedit"])

        if prefs.themes and "axis_x" in snapshot:
            ui_theme = prefs.themes[0].user_interface
            v3d_theme = prefs.themes[0].view_3d
            ui_theme.axis_x = snapshot["axis_x"]
            ui_theme.axis_y = snapshot["axis_y"]
            ui_theme.axis_z = snapshot["axis_z"]
            if "grid" in snapshot:
                v3d_theme.grid = snapshot["grid"]
            if "grid_major" in snapshot:
                v3d_theme.grid_major = snapshot["grid_major"]
            if "bg_type" in snapshot:
                v3d_theme.space.gradients.background_type = snapshot["bg_type"]
            if "bg_high" in snapshot:
                v3d_theme.space.gradients.high_gradient = snapshot["bg_high"]
            if "bg_grad" in snapshot:
                v3d_theme.space.gradients.gradient = snapshot["bg_grad"]
            for key, attr in (
                ("v3d_object_active", "object_active"),
                ("v3d_object_selected", "object_selected"),
                ("v3d_wire", "wire"),
                ("v3d_wire_edit", "wire_edit"),
                ("v3d_vertex_select", "vertex_select"),
                ("v3d_edge_select", "edge_select"),
                ("v3d_face_select", "face_select"),
            ):
                if key in snapshot:
                    setattr(v3d_theme, attr, snapshot[key])

        prev_kc = snapshot.get("active_keyconfig", "Blender")
        kc_path = _resolve_keyconfig_filepath(prev_kc) or _resolve_keyconfig_filepath("Blender")
        if kc_path:
            bpy.ops.preferences.keyconfig_activate(filepath=kc_path)

        os.remove(backup_path)
        keymap.rebuild_keymaps()
        self.report({"INFO"}, f"Restored previous setup ({prev_kc})")
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_apply_maya_setup,
    MAYA_UX_OT_restore_previous_setup,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
