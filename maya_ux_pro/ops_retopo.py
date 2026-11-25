from __future__ import annotations

import bpy
from bpy.props import BoolProperty, StringProperty

_SHRINKWRAP_NAME = "MayaQuadDrawShrinkwrap"
_MIRROR_NAME = "MayaQuadDrawMirror"


class MAYA_UX_OT_make_live(bpy.types.Operator):
    """Set the active Mesh object as Maya Live Surface for Quad Draw retopology."""

    bl_idname = "maya_ux.make_live"
    bl_label = "Make Live"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            context.scene.maya_ux_live_surface = ""
            self.report({"INFO"}, "Live Surface cleared")
            return {"FINISHED"}

        if context.scene.maya_ux_live_surface == obj.name:
            context.scene.maya_ux_live_surface = ""
            self.report({"INFO"}, "Live Surface cleared")
        else:
            context.scene.maya_ux_live_surface = obj.name
            self.report({"INFO"}, f"Live Surface: {obj.name}")
        return {"FINISHED"}


class MAYA_UX_OT_clear_live(bpy.types.Operator):
    """Clear the active Maya Live Surface."""

    bl_idname = "maya_ux.clear_live"
    bl_label = "Exit Live"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.scene.maya_ux_live_surface = ""
        return {"FINISHED"}


class MAYA_UX_OT_start_quad_draw(bpy.types.Operator):
    """Start Maya-style Quad Draw retopology onto the Live Surface using Poly Build + Shrinkwrap."""

    bl_idname = "maya_ux.start_quad_draw"
    bl_label = "Quad Draw"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        live_obj = bpy.data.objects.get(scene.maya_ux_live_surface)

        if live_obj is None or live_obj.type != "MESH":
            active = context.active_object
            if active is not None and active.type == "MESH":
                live_obj = active
                scene.maya_ux_live_surface = live_obj.name
            else:
                self.report({"WARNING"}, "Select a Mesh object to Make Live for Quad Draw")
                return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        active = context.active_object
        if active is not None and active.type == "MESH" and active != live_obj:
            retopo_obj = active
        else:
            retopo_name = f"Retopo_{live_obj.name}"
            retopo_obj = bpy.data.objects.get(retopo_name)
            if retopo_obj is None or retopo_obj.type != "MESH":
                mesh_data = bpy.data.meshes.new(retopo_name)
                retopo_obj = bpy.data.objects.new(retopo_name, mesh_data)
                col = live_obj.users_collection[0] if live_obj.users_collection else scene.collection
                col.objects.link(retopo_obj)

        # Configure optional Mirror modifier first, then Shrinkwrap onto Live Surface
        if scene.maya_ux_retopo_mirror:
            mirror = retopo_obj.modifiers.get(_MIRROR_NAME)
            if mirror is None:
                mirror = retopo_obj.modifiers.new(name=_MIRROR_NAME, type="MIRROR")
            mirror.use_axis[0] = True
            mirror.use_clip = True

        sw = retopo_obj.modifiers.get(_SHRINKWRAP_NAME)
        if sw is None:
            sw = retopo_obj.modifiers.new(name=_SHRINKWRAP_NAME, type="SHRINKWRAP")
        sw.target = live_obj
        sw.wrap_method = "NEAREST_SURFACEPOINT"
        sw.show_in_editmode = True
        sw.show_on_cage = True

        # Ensure retopo object is active and visible over the live surface
        bpy.ops.object.select_all(action="DESELECT")
        retopo_obj.select_set(True)
        context.view_layer.objects.active = retopo_obj
        retopo_obj.show_in_front = True

        ts = scene.tool_settings
        ts.snap_elements = {"FACE_PROJECT"}
        ts.use_snap = True
        ts.use_snap_backface_culling = True
        ts.use_snap_translate = True

        space = getattr(context, "space_data", None)
        if space is not None and space.type == "VIEW_3D":
            space.overlay.show_retopology = True

        bpy.ops.object.mode_set(mode="EDIT")
        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.poly_build")
        except Exception:
            pass

        self.report({"INFO"}, f"Quad Draw active on '{retopo_obj.name}' -> Live '{live_obj.name}'")
        return {"FINISHED"}


class MAYA_UX_OT_retopo_relax(bpy.types.Operator):
    """Relax selected retopology vertices while Shrinkwrap keeps them glued to the Live Surface."""

    bl_idname = "maya_ux.retopo_relax"
    bl_label = "Relax on Live"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode != "EDIT_MESH":
            self.report({"WARNING"}, "Enter Edit Mode on your retopology mesh first")
            return {"CANCELLED"}
        bpy.ops.mesh.vertices_smooth(factor=0.5, repeat=2)
        return {"FINISHED"}


class MAYA_UX_OT_finish_quad_draw(bpy.types.Operator):
    """Bake Quad Draw Shrinkwrap modifier and exit retopology overlays."""

    bl_idname = "maya_ux.finish_quad_draw"
    bl_label = "Finish / Bake Retopo"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        sw = obj.modifiers.get(_SHRINKWRAP_NAME)
        if sw is not None:
            try:
                bpy.ops.object.modifier_apply(modifier=sw.name)
            except RuntimeError:
                obj.modifiers.remove(sw)

        obj.show_in_front = False
        ts = context.scene.tool_settings
        if "FACE_PROJECT" in ts.snap_elements:
            ts.use_snap = False

        space = getattr(context, "space_data", None)
        if space is not None and space.type == "VIEW_3D":
            space.overlay.show_retopology = False

        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_make_live,
    MAYA_UX_OT_clear_live,
    MAYA_UX_OT_start_quad_draw,
    MAYA_UX_OT_retopo_relax,
    MAYA_UX_OT_finish_quad_draw,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.maya_ux_live_surface = StringProperty(
        name="Live Surface",
        description="Name of the active Maya Live Surface mesh",
        default="",
    )
    bpy.types.Scene.maya_ux_retopo_mirror = BoolProperty(
        name="Retopo X Symmetry",
        description="Automatically add clipped X Mirror modifier when starting Quad Draw",
        default=True,
    )


def unregister():
    if hasattr(bpy.types.Scene, "maya_ux_retopo_mirror"):
        del bpy.types.Scene.maya_ux_retopo_mirror
    if hasattr(bpy.types.Scene, "maya_ux_live_surface"):
        del bpy.types.Scene.maya_ux_live_surface
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
