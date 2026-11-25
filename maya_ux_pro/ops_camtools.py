from __future__ import annotations

import json

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Euler, Quaternion, Vector


def _next_cam_name() -> str:
    idx = 1
    while f"persp{idx}" in bpy.data.objects:
        idx += 1
    return f"persp{idx}"


def _get_view3d(context):
    space = getattr(context, "space_data", None)
    if space is not None and space.type == "VIEW_3D":
        return space
    screen = getattr(context, "screen", None)
    if screen is not None:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                return area.spaces.active
    return None


def _load_bookmarks(scene) -> dict:
    raw = getattr(scene, "maya_ux_cam_slots", "") or "{}"
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_bookmarks(scene, data: dict):
    scene.maya_ux_cam_slots = json.dumps(data)


def has_bookmark(scene, slot: int) -> bool:
    return str(slot) in _load_bookmarks(scene)


class MAYA_UX_OT_cam_from_view(bpy.types.Operator):
    """Create a Maya-style camera aligned to the current 3D View and set it active."""

    bl_idname = "maya_ux.cam_from_view"
    bl_label = "Create Camera from View"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        cam_name = _next_cam_name()
        cam_data = bpy.data.cameras.new(cam_name)
        cam_data.clip_start = 0.01
        cam_data.clip_end = 10000.0
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        context.scene.collection.objects.link(cam_obj)
        context.scene.camera = cam_obj

        space = _get_view3d(context)
        aligned = False
        if space is not None and getattr(context, "area", None) is not None and context.area.type == "VIEW_3D":
            try:
                bpy.ops.view3d.camera_to_view()
                aligned = True
            except Exception:
                aligned = False
        if not aligned:
            cam_obj.location = Vector((7.0, -7.0, 5.0))
            cam_obj.rotation_euler = Euler((1.1, 0.0, 0.785), "XYZ")

        bpy.ops.object.select_all(action="DESELECT")
        cam_obj.select_set(True)
        context.view_layer.objects.active = cam_obj
        self.report({"INFO"}, f"Created Camera '{cam_name}'")
        return {"FINISHED"}


class MAYA_UX_OT_toggle_lock_camera(bpy.types.Operator):
    """Toggle Lock Camera to View (CamTools)."""

    bl_idname = "maya_ux.toggle_lock_camera"
    bl_label = "Lock Camera to View"
    bl_options = {"REGISTER"}

    def execute(self, context):
        space = _get_view3d(context)
        if space is None:
            return {"CANCELLED"}
        space.lock_camera = not space.lock_camera
        return {"FINISHED"}


class MAYA_UX_OT_set_cam_lens(bpy.types.Operator):
    """Set focal length on active scene camera and 3D Viewport."""

    bl_idname = "maya_ux.set_cam_lens"
    bl_label = "Set Camera Focal Length"
    bl_options = {"REGISTER", "UNDO"}

    lens: FloatProperty(name="Focal Length (mm)", default=50.0, min=1.0, max=500.0)

    def execute(self, context):
        cam = context.scene.camera
        if cam is not None and cam.type == "CAMERA":
            cam.data.lens = self.lens
        space = _get_view3d(context)
        if space is not None:
            space.lens = self.lens
        return {"FINISHED"}


class MAYA_UX_OT_fix_cam_clip(bpy.types.Operator):
    """Set Maya-friendly clipping planes (0.01 .. 10000) on camera & viewport."""

    bl_idname = "maya_ux.fix_cam_clip"
    bl_label = "Fix Camera Clipping"
    bl_options = {"REGISTER"}

    def execute(self, context):
        cam = context.scene.camera
        if cam is not None and cam.type == "CAMERA":
            cam.data.clip_start = 0.01
            cam.data.clip_end = 10000.0
        space = _get_view3d(context)
        if space is not None:
            space.clip_start = 0.01
            space.clip_end = 10000.0
        self.report({"INFO"}, "Clipping set to 0.01 - 10000")
        return {"FINISHED"}


class MAYA_UX_OT_cam_bookmark(bpy.types.Operator):
    """Save, Load, or Clear up to 4 Maya-style Camera Bookmarks in the scene."""

    bl_idname = "maya_ux.cam_bookmark"
    bl_label = "Camera Bookmark"
    bl_options = {"REGISTER", "UNDO"}

    slot: IntProperty(name="Slot", min=1, max=4, default=1)
    action: EnumProperty(
        name="Action",
        items=[
            ("SAVE", "Save", "Save current view/camera into slot"),
            ("LOAD", "Load", "Jump to saved view/camera bookmark"),
            ("CLEAR", "Clear", "Clear bookmark slot"),
        ],
        default="SAVE",
    )

    def execute(self, context):
        scene = context.scene
        data = _load_bookmarks(scene)
        key = str(self.slot)

        if self.action == "CLEAR":
            data.pop(key, None)
            _save_bookmarks(scene, data)
            return {"FINISHED"}

        space = _get_view3d(context)
        rv3d = getattr(space, "region_3d", None) if space is not None else None
        cam = scene.camera

        if self.action == "SAVE":
            if rv3d is None and cam is None:
                return {"CANCELLED"}
            entry = {}
            if rv3d is not None:
                entry["rv3d"] = {
                    "loc": list(rv3d.view_location),
                    "rot": list(rv3d.view_rotation),
                    "dist": float(rv3d.view_distance),
                    "persp": str(rv3d.view_perspective),
                }
            if cam is not None:
                entry["cam"] = {
                    "loc": list(cam.location),
                    "rot": list(cam.rotation_euler),
                }
            data[key] = entry
            _save_bookmarks(scene, data)
            self.report({"INFO"}, f"Saved Camera Bookmark {self.slot}")
            return {"FINISHED"}

        # LOAD
        entry = data.get(key)
        if not entry:
            self.report({"WARNING"}, f"Camera Bookmark {self.slot} is empty")
            return {"CANCELLED"}
        if "rv3d" in entry and rv3d is not None:
            r = entry["rv3d"]
            rv3d.view_location = Vector(r["loc"])
            rv3d.view_rotation = Quaternion(r["rot"])
            rv3d.view_distance = float(r["dist"])
            rv3d.view_perspective = r["persp"]
        if "cam" in entry and cam is not None and (rv3d is None or rv3d.view_perspective == "CAMERA"):
            c = entry["cam"]
            cam.location = Vector(c["loc"])
            cam.rotation_euler = Euler(c["rot"], "XYZ")
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_cam_from_view,
    MAYA_UX_OT_toggle_lock_camera,
    MAYA_UX_OT_set_cam_lens,
    MAYA_UX_OT_fix_cam_clip,
    MAYA_UX_OT_cam_bookmark,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.maya_ux_cam_slots = StringProperty(
        name="Maya Camera Bookmarks JSON",
        default="{}",
    )


def unregister():
    if hasattr(bpy.types.Scene, "maya_ux_cam_slots"):
        del bpy.types.Scene.maya_ux_cam_slots
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
