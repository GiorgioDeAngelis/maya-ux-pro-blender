from __future__ import annotations

import bpy
from bpy.props import EnumProperty

_KEYING_SET_MAP = {
    "ALL": "LocRotScale",
    "LOC": "Location",
    "ROT": "Rotation",
    "SCALE": "Scaling",
}


class MAYA_UX_OT_set_keyframe(bpy.types.Operator):
    """Insert Maya-style keyframes (S = Loc/Rot/Scale, Shift+W/E/R = Location/Rotation/Scale)."""

    bl_idname = "maya_ux.set_keyframe"
    bl_label = "Maya Set Keyframe"
    bl_options = {"REGISTER", "UNDO"}

    channels: EnumProperty(
        name="Channels",
        items=[
            ("ALL", "All (S)", "Keyframe Location, Rotation, and Scale"),
            ("LOC", "Translate (Shift+W)", "Keyframe Location"),
            ("ROT", "Rotate (Shift+E)", "Keyframe Rotation"),
            ("SCALE", "Scale (Shift+R)", "Keyframe Scale"),
        ],
        default="ALL",
    )

    def execute(self, context):
        ks_name = _KEYING_SET_MAP[self.channels]
        try:
            res = bpy.ops.anim.keyframe_insert_by_name(type=ks_name)
            if res == {"FINISHED"}:
                return {"FINISHED"}
        except Exception:
            pass

        # Fallback direct data-path keyframing for headless / pose / multi-object contexts
        targets = list(context.selected_pose_bones) if context.mode == "POSE" else list(context.selected_objects)
        if not targets and context.active_object is not None:
            targets = [context.active_object]
        if not targets:
            return {"CANCELLED"}

        frame = context.scene.frame_current
        paths = []
        if self.channels in {"ALL", "LOC"}:
            paths.append("location")
        if self.channels in {"ALL", "ROT"}:
            paths.append("rotation_euler")
        if self.channels in {"ALL", "SCALE"}:
            paths.append("scale")

        for item in targets:
            for dp in paths:
                if dp == "rotation_euler" and getattr(item, "rotation_mode", "XYZ") == "QUATERNION":
                    item.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                else:
                    item.keyframe_insert(data_path=dp, frame=frame)
        return {"FINISHED"}


class MAYA_UX_OT_goto_min_frame(bpy.types.Operator):
    """Jump timeline playhead to scene start frame (Maya Alt+Shift+V)."""

    bl_idname = "maya_ux.goto_min_frame"
    bl_label = "Go to Min Frame"
    bl_options = {"REGISTER"}

    def execute(self, context):
        context.scene.frame_set(context.scene.frame_start)
        return {"FINISHED"}


class MAYA_UX_OT_toggle_autokey(bpy.types.Operator):
    """Toggle Auto-Keyframing (Maya Alt+K)."""

    bl_idname = "maya_ux.toggle_autokey"
    bl_label = "Toggle Auto-Key"
    bl_options = {"REGISTER"}

    def execute(self, context):
        ts = context.scene.tool_settings
        ts.use_keyframe_insert_auto = not ts.use_keyframe_insert_auto
        self.report({"INFO"}, f"Auto-Key: {'ON' if ts.use_keyframe_insert_auto else 'OFF'}")
        return {"FINISHED"}


class MAYA_UX_OT_graph_tangent(bpy.types.Operator):
    """Apply Maya-style tangent / interpolation presets in Graph Editor."""

    bl_idname = "maya_ux.graph_tangent"
    bl_label = "Maya Graph Tangent"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(
        name="Tangent Preset",
        items=[
            ("LINEAR", "Linear (1)", "Linear keyframe interpolation"),
            ("AUTO_FLAT", "Auto / Flat (2)", "Bezier with Auto-Clamped handles"),
            ("STEPPED", "Stepped (3)", "Constant stepped interpolation"),
            ("SPLINE", "Spline (4)", "Smooth Bezier spline interpolation"),
            ("FREE", "Free (Break Tangents)", "Break tangent handle alignment"),
            ("ALIGNED", "Aligned (Unify Tangents)", "Unify tangent handle alignment"),
        ],
        default="AUTO_FLAT",
    )

    def execute(self, context):
        try:
            if self.preset == "LINEAR":
                bpy.ops.graph.interpolation_type(type="LINEAR")
            elif self.preset == "STEPPED":
                bpy.ops.graph.interpolation_type(type="CONSTANT")
            elif self.preset == "SPLINE":
                bpy.ops.graph.interpolation_type(type="BEZIER")
            elif self.preset == "AUTO_FLAT":
                bpy.ops.graph.interpolation_type(type="BEZIER")
                bpy.ops.graph.handle_type(type="AUTO_CLAMPED")
            elif self.preset == "FREE":
                bpy.ops.graph.handle_type(type="FREE")
            elif self.preset == "ALIGNED":
                bpy.ops.graph.handle_type(type="ALIGNED")
        except Exception as exc:
            self.report({"WARNING"}, f"Graph Editor tangent failed: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_set_keyframe,
    MAYA_UX_OT_goto_min_frame,
    MAYA_UX_OT_toggle_autokey,
    MAYA_UX_OT_graph_tangent,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
