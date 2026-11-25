from __future__ import annotations

import math

import bpy
from bpy.props import BoolProperty, EnumProperty
from mathutils import Vector

_PRESET_DEFS = {
    "LAMBERT1": ("lambert1", (0.5, 0.5, 0.5, 1.0), 0.85, 0.0, 0.2),
    "BLINN1": ("blinn1", (0.48, 0.50, 0.53, 1.0), 0.22, 0.0, 0.5),
    "CLAY_SCULPT": ("maya_clay", (0.55, 0.24, 0.16, 1.0), 0.55, 0.0, 0.35),
    "CHROME_CHECK": ("maya_chrome", (0.92, 0.92, 0.94, 1.0), 0.04, 1.0, 0.5),
    "UV_CHECKER": ("maya_uv_checker", (1.0, 1.0, 1.0, 1.0), 0.60, 0.0, 0.3),
    "GLASS_BASIC": ("maya_glass", (0.95, 0.98, 1.0, 1.0), 0.05, 0.0, 0.5),
}

_STUDIO_COL_NAME = "MayaStudioLights"


def get_or_create_maya_material(preset: str) -> bpy.types.Material:
    """Return existing or newly created Maya starter Principled BSDF material."""
    name, color, roughness, metallic, spec = _PRESET_DEFS[preset]
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")

    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec

    if preset == "BLINN1" and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.4
        bsdf.inputs["Coat Roughness"].default_value = 0.15
    elif preset == "GLASS_BASIC" and "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.95
        bsdf.inputs["IOR"].default_value = 1.45
    elif preset == "UV_CHECKER":
        img = bpy.data.images.get("MayaUVChecker")
        if img is None:
            img = bpy.data.images.new("MayaUVChecker", width=1024, height=1024)
            img.generated_type = "COLOR_GRID"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-320, 260)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    return mat


class MAYA_UX_OT_assign_maya_material(bpy.types.Operator):
    """Assign a Maya starter material (Lambert1, Blinn, Clay, Chrome, UV Grid, Glass) to selection."""

    bl_idname = "maya_ux.assign_maya_material"
    bl_label = "Assign Maya Material"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(
        name="Material Preset",
        items=[
            ("LAMBERT1", "Lambert1", "Neutral Maya matte gray"),
            ("BLINN1", "Blinn1", "Glossy Blinn for highlight inspection"),
            ("CLAY_SCULPT", "Clay Sculpt", "Warm terracotta clay"),
            ("CHROME_CHECK", "Chrome Check", "Mirror surface for curvature reflection check"),
            ("UV_CHECKER", "UV Checker", "Procedural Color Grid for UV unwrap verification"),
            ("GLASS_BASIC", "Glass", "Refractive basic glass"),
        ],
        default="LAMBERT1",
    )

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type in {"MESH", "CURVE", "SURFACE", "FONT", "META"}]
        if not targets and context.active_object and context.active_object.type in {"MESH", "CURVE", "SURFACE"}:
            targets = [context.active_object]
        if not targets:
            self.report({"WARNING"}, "Select at least one object")
            return {"CANCELLED"}

        mat = get_or_create_maya_material(self.preset)
        for obj in targets:
            if len(obj.data.materials) == 0:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat
        self.report({"INFO"}, f"Assigned '{mat.name}' to {len(targets)} object(s)")
        return {"FINISHED"}


def _aim_light_at(light_obj: bpy.types.Object, target: Vector):
    direction = target - light_obj.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    light_obj.rotation_euler = rot_quat.to_euler()


class MAYA_UX_OT_setup_studio_lighting(bpy.types.Operator):
    """Create or remove a 3-point Maya Studio Lighting rig around the selection."""

    bl_idname = "maya_ux.setup_studio_lighting"
    bl_label = "Toggle 3-Point Studio Lights"
    bl_options = {"REGISTER", "UNDO"}

    remove: BoolProperty(name="Remove Existing Lights", default=False)

    def execute(self, context):
        existing = bpy.data.collections.get(_STUDIO_COL_NAME)
        if existing is not None:
            for obj in list(existing.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(existing)
            if self.remove:
                self.report({"INFO"}, "Removed Maya Studio Lights")
                return {"FINISHED"}
            self.report({"INFO"}, "Removed Maya Studio Lights")
            return {"FINISHED"}

        if self.remove:
            return {"CANCELLED"}

        target = context.active_object.matrix_world.translation.copy() if context.active_object else Vector((0.0, 0.0, 0.0))
        col = bpy.data.collections.new(_STUDIO_COL_NAME)
        context.scene.collection.children.link(col)

        specs = (
            ("MayaKeyLight", Vector((4.5, -4.5, 5.0)), 250.0, 2.5, (1.0, 0.96, 0.90)),
            ("MayaFillLight", Vector((-5.0, -3.5, 2.5)), 90.0, 4.0, (0.82, 0.90, 1.0)),
            ("MayaRimLight", Vector((-2.5, 5.5, 4.5)), 180.0, 2.0, (0.95, 0.98, 1.0)),
        )
        for name, offset, energy, size, color in specs:
            ldata = bpy.data.lights.new(name=name, type="AREA")
            ldata.energy = energy
            ldata.size = size
            ldata.color = color
            lobj = bpy.data.objects.new(name, ldata)
            lobj.location = target + offset
            _aim_light_at(lobj, target)
            col.objects.link(lobj)

        self.report({"INFO"}, "Created 3-Point Maya Studio Lights")
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_assign_maya_material,
    MAYA_UX_OT_setup_studio_lighting,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
