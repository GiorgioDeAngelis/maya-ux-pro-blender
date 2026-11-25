from __future__ import annotations

import bpy
from bpy.props import EnumProperty, StringProperty


class MAYA_UX_OT_uv_mode(bpy.types.Operator):
    """Switch UV selection mode (Vertex, Edge, Face, or UV Shell/Island)."""

    bl_idname = "maya_ux.uv_mode"
    bl_label = "Maya UV Select Mode"
    bl_options = {"REGISTER", "UNDO"}

    mode: EnumProperty(
        name="UV Mode",
        items=[
            ("VERTEX", "UV Vertex", "Select UV vertices"),
            ("EDGE", "UV Edge", "Select UV edges"),
            ("FACE", "UV Face", "Select UV faces"),
            ("ISLAND", "UV Shell (Island)", "Select UV islands/shells"),
        ],
        default="VERTEX",
    )

    def execute(self, context):
        ts = context.scene.tool_settings
        if self.mode == "ISLAND":
            ts.uv_select_mode = "FACE"
            if hasattr(ts, "use_uv_select_island"):
                ts.use_uv_select_island = True
        else:
            if hasattr(ts, "use_uv_select_island"):
                ts.use_uv_select_island = False
            ts.uv_select_mode = self.mode
        return {"FINISHED"}


class MAYA_UX_OT_uv_tool(bpy.types.Operator):
    """Switch UV Editor active tool (Q/W/E/R)."""

    bl_idname = "maya_ux.uv_tool"
    bl_label = "Maya UV Tool"
    bl_options = {"REGISTER"}

    tool_id: StringProperty(name="Tool ID", default="builtin.select_box")

    def execute(self, context):
        try:
            bpy.ops.wm.tool_set_by_id(name=self.tool_id)
        except Exception as exc:
            self.report({"WARNING"}, f"Could not set UV tool {self.tool_id}: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_uv_mode,
    MAYA_UX_OT_uv_tool,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
