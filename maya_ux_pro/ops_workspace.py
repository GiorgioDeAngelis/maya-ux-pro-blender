from __future__ import annotations

import bpy
from bpy.props import StringProperty

from . import ops_maya_axes


def apply_maya_dark_theme(context=None):
    """Apply classic Maya Dark selection/wireframe colors, grid, and Green-Up/Blue-Depth axes."""
    ctx = context or bpy.context
    prefs = getattr(ctx, "preferences", None)
    if prefs is not None and prefs.themes:
        v3d = prefs.themes[0].view_3d
        v3d.object_active = (0.30, 1.0, 0.35)
        v3d.object_selected = (0.95, 0.95, 0.95)
        v3d.wire = (0.04, 0.08, 0.22)
        v3d.wire_edit = (0.12, 0.35, 0.72)
        v3d.vertex_select = (1.0, 0.88, 0.12)
        v3d.edge_select = (1.0, 0.55, 0.08)
        v3d.face_select = (1.0, 0.48, 0.10, 0.35)

    ops_maya_axes.apply_maya_grid_theme(ctx)
    from .preferences import get_prefs

    ops_maya_axes.apply_maya_axis_colors(bool(getattr(get_prefs(ctx), "swap_axis_colors_yup", False)), ctx)
    from . import ops_selection

    ops_selection.reset_component_color_cache(ctx)


class MAYA_UX_OT_apply_maya_theme(bpy.types.Operator):
    """Apply Maya Dark selection/wireframe colors, gradient background, and Green-Up axes."""

    bl_idname = "maya_ux.apply_maya_theme"
    bl_label = "Apply Maya Dark Theme"
    bl_options = {"REGISTER"}

    def execute(self, context):
        apply_maya_dark_theme(context)
        self.report({"INFO"}, "Maya Dark Theme applied")
        return {"FINISHED"}


class MAYA_UX_OT_create_maya_workspace(bpy.types.Operator):
    """Create or switch to a target Maya or Blender workspace."""

    bl_idname = "maya_ux.create_maya_workspace"
    bl_label = "Open 'Maya Pro' Workspace"
    bl_options = {"REGISTER"}

    workspace_name: StringProperty(
        name="Workspace Name",
        description="Target workspace to switch to or create",
        default="Maya Pro",
    )

    def execute(self, context):
        target = (self.workspace_name or "").strip() or "Maya Pro"
        existing = bpy.data.workspaces.get(target)
        if existing is not None:
            if context.window is not None:
                context.window.workspace = existing
            return {"FINISHED"}

        try:
            bpy.ops.workspace.duplicate()
        except Exception as exc:
            self.report({"WARNING"}, f"Could not duplicate workspace: {exc}")
            return {"CANCELLED"}

        ws = context.workspace
        if ws is not None:
            ws.name = target
            for screen in ws.screens:
                for area in screen.areas:
                    if area.type == "VIEW_3D":
                        area.spaces.active.show_region_ui = True
                        break

        self.report({"INFO"}, f"Created '{target}' Workspace")
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_apply_maya_theme,
    MAYA_UX_OT_create_maya_workspace,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
