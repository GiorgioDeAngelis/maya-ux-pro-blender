from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper


class MAYA_UX_OT_export_maya_fbx(bpy.types.Operator, ExportHelper):
    """Export FBX preconfigured for Maya Y-Up (Up=Y, Forward=-Z, Unit Scale)."""

    bl_idname = "maya_ux.export_maya_fbx"
    bl_label = "Export Maya FBX (Y-Up)"
    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})
    selected_only: BoolProperty(name="Selected Only", default=True)

    def execute(self, context):
        bpy.ops.export_scene.fbx(
            filepath=self.filepath,
            use_selection=self.selected_only,
            axis_up="Y",
            axis_forward="-Z",
            apply_scale_options="FBX_SCALE_UNITS",
        )
        return {"FINISHED"}


class MAYA_UX_OT_import_maya_fbx(bpy.types.Operator, ImportHelper):
    """Import Maya Y-Up FBX (Up=Y, Forward=-Z)."""

    bl_idname = "maya_ux.import_maya_fbx"
    bl_label = "Import Maya FBX (Y-Up)"
    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def execute(self, context):
        bpy.ops.import_scene.fbx(
            filepath=self.filepath,
            axis_up="Y",
            axis_forward="-Z",
        )
        return {"FINISHED"}


class MAYA_UX_OT_export_maya_obj(bpy.types.Operator, ExportHelper):
    """Export OBJ preconfigured for Maya Y-Up (Up=Y, Forward=-Z)."""

    bl_idname = "maya_ux.export_maya_obj"
    bl_label = "Export Maya OBJ (Y-Up)"
    filename_ext = ".obj"
    filter_glob: StringProperty(default="*.obj", options={"HIDDEN"})
    selected_only: BoolProperty(name="Selected Only", default=True)

    def execute(self, context):
        bpy.ops.wm.obj_export(
            filepath=self.filepath,
            export_selected_objects=self.selected_only,
            up_axis="Y",
            forward_axis="NEGATIVE_Z",
        )
        return {"FINISHED"}


class MAYA_UX_OT_import_maya_obj(bpy.types.Operator, ImportHelper):
    """Import Maya Y-Up OBJ (Up=Y, Forward=-Z)."""

    bl_idname = "maya_ux.import_maya_obj"
    bl_label = "Import Maya OBJ (Y-Up)"
    filename_ext = ".obj"
    filter_glob: StringProperty(default="*.obj", options={"HIDDEN"})

    def execute(self, context):
        bpy.ops.wm.obj_import(
            filepath=self.filepath,
            up_axis="Y",
            forward_axis="NEGATIVE_Z",
        )
        return {"FINISHED"}


class MAYA_UX_OT_export_maya_usd(bpy.types.Operator, ExportHelper):
    """Export USD preconfigured for Maya Y-Up (Up=Y, Forward=-Z, Centimeters)."""

    bl_idname = "maya_ux.export_maya_usd"
    bl_label = "Export Maya USD (Y-Up)"
    filename_ext = ".usd"
    filter_glob: StringProperty(default="*.usd;*.usda;*.usdc", options={"HIDDEN"})
    selected_only: BoolProperty(name="Selected Only", default=True)

    def execute(self, context):
        bpy.ops.wm.usd_export(
            filepath=self.filepath,
            selected_objects_only=self.selected_only,
            export_global_up_selection="Y",
            export_global_forward_selection="NEGATIVE_Z",
            convert_scene_units="CENTIMETERS",
        )
        return {"FINISHED"}


class MAYA_UX_OT_import_maya_usd(bpy.types.Operator, ImportHelper):
    """Import Maya USD with automatic unit conversion."""

    bl_idname = "maya_ux.import_maya_usd"
    bl_label = "Import Maya USD (Y-Up)"
    filename_ext = ".usd"
    filter_glob: StringProperty(default="*.usd;*.usda;*.usdc", options={"HIDDEN"})

    def execute(self, context):
        bpy.ops.wm.usd_import(
            filepath=self.filepath,
            apply_unit_conversion_scale=True,
        )
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_export_maya_fbx,
    MAYA_UX_OT_import_maya_fbx,
    MAYA_UX_OT_export_maya_obj,
    MAYA_UX_OT_import_maya_obj,
    MAYA_UX_OT_export_maya_usd,
    MAYA_UX_OT_import_maya_usd,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
