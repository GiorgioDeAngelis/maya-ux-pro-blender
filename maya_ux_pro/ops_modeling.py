from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty
from mathutils import Euler, Vector

from .ops_smooth import SMOOTH_MOD_NAME

_LAST_DUP_STATE: dict | None = None


def _snapshot_xform(obj: bpy.types.Object) -> tuple[Vector, Euler, Vector]:
    return (
        obj.location.copy(),
        obj.rotation_euler.copy(),
        obj.scale.copy(),
    )


class MAYA_UX_OT_freeze_transforms(bpy.types.Operator):
    """Freeze Location, Rotation, and Scale on selected objects (Maya Modify > Freeze Transformations)."""

    bl_idname = "maya_ux.freeze_transforms"
    bl_label = "Freeze Transforms"
    bl_options = {"REGISTER", "UNDO"}

    location: BoolProperty(name="Translate", default=True)
    rotation: BoolProperty(name="Rotate", default=True)
    scale: BoolProperty(name="Scale", default=True)
    make_single_user: BoolProperty(
        name="Make Multi-User Data Single User",
        description="Duplicate shared mesh data before applying transforms instead of skipping",
        default=False,
    )

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            self.report({"WARNING"}, "Select at least one object")
            return {"CANCELLED"}

        was_edit = context.mode != "OBJECT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")

        view_layer = context.view_layer
        prev_active = context.active_object
        applied = 0
        skipped = 0

        try:
            for obj in selected:
                if obj.data is not None and obj.data.users > 1:
                    if self.make_single_user:
                        obj.data = obj.data.copy()
                    else:
                        skipped += 1
                        continue
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                view_layer.objects.active = obj
                bpy.ops.object.transform_apply(
                    location=self.location,
                    rotation=self.rotation,
                    scale=self.scale,
                )
                applied += 1
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in selected:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if prev_active is not None and prev_active.name in bpy.data.objects:
                view_layer.objects.active = prev_active
            if was_edit and context.active_object is not None:
                bpy.ops.object.mode_set(mode="EDIT")

        if skipped:
            self.report({"WARNING"}, f"Froze {applied} object(s); skipped {skipped} multi-user object(s)")
        else:
            self.report({"INFO"}, f"Froze transforms on {applied} object(s)")
        return {"FINISHED"}


class MAYA_UX_OT_reset_transforms(bpy.types.Operator):
    """Reset unlocked Location/Rotation/Scale channels to default Maya values."""

    bl_idname = "maya_ux.reset_transforms"
    bl_label = "Reset Transforms"
    bl_options = {"REGISTER", "UNDO"}

    channel: EnumProperty(
        name="Channel",
        items=[
            ("ALL", "All Channels", "Reset Translate, Rotate, and Scale"),
            ("LOC", "Translate", "Reset Location to (0, 0, 0)"),
            ("ROT", "Rotate", "Reset Rotation to (0, 0, 0)"),
            ("SCALE", "Scale", "Reset Scale to (1, 1, 1)"),
        ],
        default="ALL",
    )

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            return {"CANCELLED"}

        for obj in selected:
            if self.channel in {"ALL", "LOC"}:
                for i in range(3):
                    if not obj.lock_location[i]:
                        obj.location[i] = 0.0
            if self.channel in {"ALL", "ROT"}:
                for i in range(3):
                    if not obj.lock_rotation[i]:
                        obj.rotation_euler[i] = 0.0
            if self.channel in {"ALL", "SCALE"}:
                for i in range(3):
                    if not obj.lock_scale[i]:
                        obj.scale[i] = 1.0
        return {"FINISHED"}


class MAYA_UX_OT_delete_history(bpy.types.Operator):
    """Apply active modifiers to bake construction history (Maya Edit > Delete by Type > History)."""

    bl_idname = "maya_ux.delete_history"
    bl_label = "Delete History"
    bl_options = {"REGISTER", "UNDO"}

    keep_smooth_preview: BoolProperty(
        name="Keep Maya Smooth Preview",
        description="Preserve MayaSmoothPreview modifier instead of baking it",
        default=False,
    )

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not meshes:
            self.report({"WARNING"}, "Select at least one Mesh object")
            return {"CANCELLED"}

        was_edit = context.mode != "OBJECT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")

        view_layer = context.view_layer
        prev_active = context.active_object
        prev_selected = list(context.selected_objects)

        try:
            for obj in meshes:
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                view_layer.objects.active = obj
                for mod in list(obj.modifiers):
                    if self.keep_smooth_preview and mod.name == SMOOTH_MOD_NAME:
                        continue
                    if mod.show_viewport:
                        try:
                            bpy.ops.object.modifier_apply(modifier=mod.name)
                        except RuntimeError:
                            obj.modifiers.remove(mod)
                    else:
                        obj.modifiers.remove(mod)
        finally:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in prev_selected:
                if obj.name in bpy.data.objects:
                    obj.select_set(True)
            if prev_active is not None and prev_active.name in bpy.data.objects:
                view_layer.objects.active = prev_active
            if was_edit and context.active_object is not None:
                bpy.ops.object.mode_set(mode="EDIT")

        return {"FINISHED"}


class MAYA_UX_OT_combine(bpy.types.Operator):
    """Combine selected Mesh objects into one (Maya Mesh > Combine)."""

    bl_idname = "maya_ux.combine"
    bl_label = "Combine"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if len(meshes) < 2:
            self.report({"WARNING"}, "Select at least 2 Mesh objects to Combine")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        if context.active_object not in meshes:
            context.view_layer.objects.active = meshes[0]

        bpy.ops.object.join()
        return {"FINISHED"}


class MAYA_UX_OT_separate(bpy.types.Operator):
    """Separate loose shells in Object Mode or selected faces in Edit Mode (Maya Mesh > Separate)."""

    bl_idname = "maya_ux.separate"
    bl_label = "Separate"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode == "EDIT_MESH":
            bpy.ops.mesh.separate(type="SELECTED")
            return {"FINISHED"}

        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not meshes:
            self.report({"WARNING"}, "Select a Mesh object to Separate")
            return {"CANCELLED"}

        if context.active_object not in meshes:
            context.view_layer.objects.active = meshes[0]

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.mesh.separate(type="LOOSE")
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        return {"FINISHED"}


class MAYA_UX_OT_toggle_symmetry(bpy.types.Operator):
    """Toggle Maya-style live mesh symmetry on X, Y, or Z axis."""

    bl_idname = "maya_ux.toggle_symmetry"
    bl_label = "Toggle Symmetry"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(
        name="Axis",
        items=[("X", "X", "Mirror X"), ("Y", "Y", "Mirror Y"), ("Z", "Z", "Mirror Z")],
        default="X",
    )

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not meshes and context.active_object and context.active_object.type == "MESH":
            meshes = [context.active_object]
        if not meshes:
            return {"CANCELLED"}

        attr_obj = f"use_mesh_mirror_{self.axis.lower()}"
        attr_data = f"use_mirror_{self.axis.lower()}"
        new_val = not getattr(meshes[0], attr_obj)
        for obj in meshes:
            setattr(obj, attr_obj, new_val)
            if obj.data is not None and hasattr(obj.data, attr_data):
                setattr(obj.data, attr_data, new_val)
        return {"FINISHED"}


class MAYA_UX_OT_add_mirror_modifier(bpy.types.Operator):
    """Add or toggle a clipped X Mirror modifier on selected meshes."""

    bl_idname = "maya_ux.add_mirror_modifier"
    bl_label = "Toggle Mirror Modifier"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not meshes and context.active_object and context.active_object.type == "MESH":
            meshes = [context.active_object]
        if not meshes:
            return {"CANCELLED"}

        for obj in meshes:
            mod = next((m for m in obj.modifiers if m.type == "MIRROR"), None)
            if mod is None:
                mod = obj.modifiers.new(name="MayaMirror", type="MIRROR")
                mod.use_axis[0] = True
                mod.use_clip = True
            else:
                mod.show_viewport = not mod.show_viewport
        return {"FINISHED"}


class MAYA_UX_OT_duplicate_in_place(bpy.types.Operator):
    """Duplicate selected objects in place without interactive move (Maya Ctrl+D)."""

    bl_idname = "maya_ux.duplicate_in_place"
    bl_label = "Duplicate In Place"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global _LAST_DUP_STATE

        if not context.selected_objects:
            self.report({"WARNING"}, "Select at least one object to duplicate")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.duplicate(linked=False)
        active = context.active_object
        if active is not None:
            loc, rot, scale = _snapshot_xform(active)
            _LAST_DUP_STATE = {
                "dup_name": active.name,
                "base_loc": loc,
                "base_rot": rot,
                "base_scale": scale,
                "last_delta": None,
            }
        return {"FINISHED"}


class MAYA_UX_OT_duplicate_with_transform(bpy.types.Operator):
    """Duplicate and repeat the last duplicate transform delta (Maya Shift+D)."""

    bl_idname = "maya_ux.duplicate_with_transform"
    bl_label = "Duplicate with Transform"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        global _LAST_DUP_STATE

        active = context.active_object
        if not context.selected_objects or active is None:
            self.report({"WARNING"}, "Select at least one object")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        delta_loc = Vector((0.0, 0.0, 0.0))
        delta_rot = Euler((0.0, 0.0, 0.0), "XYZ")
        delta_scale = Vector((1.0, 1.0, 1.0))

        if _LAST_DUP_STATE is not None and _LAST_DUP_STATE.get("dup_name") == active.name:
            base_loc: Vector = _LAST_DUP_STATE["base_loc"]
            base_rot: Euler = _LAST_DUP_STATE["base_rot"]
            base_scale: Vector = _LAST_DUP_STATE["base_scale"]

            moved_loc = active.location - base_loc
            moved_rot = Euler(
                (
                    active.rotation_euler.x - base_rot.x,
                    active.rotation_euler.y - base_rot.y,
                    active.rotation_euler.z - base_rot.z,
                ),
                "XYZ",
            )
            moved_scale = Vector(
                (
                    active.scale.x / base_scale.x if abs(base_scale.x) > 1e-6 else 1.0,
                    active.scale.y / base_scale.y if abs(base_scale.y) > 1e-6 else 1.0,
                    active.scale.z / base_scale.z if abs(base_scale.z) > 1e-6 else 1.0,
                )
            )

            has_moved = (
                moved_loc.length > 1e-5
                or abs(moved_rot.x) > 1e-5
                or abs(moved_rot.y) > 1e-5
                or abs(moved_rot.z) > 1e-5
                or (moved_scale - Vector((1.0, 1.0, 1.0))).length > 1e-5
            )
            if has_moved:
                delta_loc, delta_rot, delta_scale = moved_loc, moved_rot, moved_scale
            elif _LAST_DUP_STATE.get("last_delta") is not None:
                delta_loc, delta_rot, delta_scale = _LAST_DUP_STATE["last_delta"]

        bpy.ops.object.duplicate(linked=False)
        for obj in context.selected_objects:
            obj.location += delta_loc
            obj.rotation_euler.x += delta_rot.x
            obj.rotation_euler.y += delta_rot.y
            obj.rotation_euler.z += delta_rot.z
            obj.scale.x *= delta_scale.x
            obj.scale.y *= delta_scale.y
            obj.scale.z *= delta_scale.z

        new_active = context.active_object
        if new_active is not None:
            loc, rot, scale = _snapshot_xform(new_active)
            _LAST_DUP_STATE = {
                "dup_name": new_active.name,
                "base_loc": loc,
                "base_rot": rot,
                "base_scale": scale,
                "last_delta": (delta_loc.copy(), delta_rot.copy(), delta_scale.copy()),
            }
        return {"FINISHED"}


class MAYA_UX_OT_duplicate_special(bpy.types.Operator):
    """Duplicate Special dialog with copies, instancing, and incremental transforms (Maya Ctrl+Shift+D)."""

    bl_idname = "maya_ux.duplicate_special"
    bl_label = "Duplicate Special"
    bl_options = {"REGISTER", "UNDO"}

    copies: IntProperty(name="Number of Copies", default=3, min=1, max=100)
    linked: BoolProperty(name="Instance (Linked Data)", default=False)
    offset_loc: FloatVectorProperty(name="Translate Offset", size=3, default=(2.0, 0.0, 0.0))
    offset_rot: FloatVectorProperty(name="Rotate Offset", size=3, subtype="EULER", default=(0.0, 0.0, 0.0))
    offset_scale: FloatVectorProperty(name="Scale Factor", size=3, default=(1.0, 1.0, 1.0))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def execute(self, context):
        sources = list(context.selected_objects)
        if not sources:
            self.report({"WARNING"}, "Select at least one object")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        created: list[bpy.types.Object] = []
        current_batch = sources
        for _step in range(self.copies):
            bpy.ops.object.select_all(action="DESELECT")
            for src in current_batch:
                src.select_set(True)
            context.view_layer.objects.active = current_batch[0]
            bpy.ops.object.duplicate(linked=self.linked)

            new_batch = list(context.selected_objects)
            for obj in new_batch:
                obj.location.x += self.offset_loc[0]
                obj.location.y += self.offset_loc[1]
                obj.location.z += self.offset_loc[2]
                obj.rotation_euler.x += self.offset_rot[0]
                obj.rotation_euler.y += self.offset_rot[1]
                obj.rotation_euler.z += self.offset_rot[2]
                obj.scale.x *= self.offset_scale[0]
                obj.scale.y *= self.offset_scale[1]
                obj.scale.z *= self.offset_scale[2]
            created.extend(new_batch)
            current_batch = new_batch

        bpy.ops.object.select_all(action="DESELECT")
        for obj in created:
            obj.select_set(True)
        if created:
            context.view_layer.objects.active = created[-1]
        return {"FINISHED"}


class MAYA_UX_OT_toggle_discrete_snap(bpy.types.Operator):
    """Toggle Maya Discrete Move/Rotate/Scale step snap (J)."""

    bl_idname = "maya_ux.toggle_discrete_snap"
    bl_label = "Toggle Discrete Snap (J)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        ts = context.scene.tool_settings
        if ts.use_snap and "INCREMENT" in ts.snap_elements:
            ts.use_snap = False
            self.report({"INFO"}, "Discrete Snap: OFF")
        else:
            ts.snap_elements = {"INCREMENT"}
            ts.use_snap = True
            ts.use_snap_translate = True
            ts.use_snap_rotate = True
            ts.use_snap_scale = True
            self.report({"INFO"}, "Discrete Snap: ON")
        return {"FINISHED"}


class MAYA_UX_OT_toggle_relative_snap(bpy.types.Operator):
    """Toggle Absolute vs Relative Grid Snapping (Maya Shift+J)."""

    bl_idname = "maya_ux.toggle_relative_snap"
    bl_label = "Toggle Relative Grid Snap"
    bl_options = {"REGISTER"}

    def execute(self, context):
        ts = context.scene.tool_settings
        ts.use_snap_grid_absolute = not ts.use_snap_grid_absolute
        mode = "Absolute Grid Snap" if ts.use_snap_grid_absolute else "Relative Grid Snap"
        self.report({"INFO"}, mode)
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_freeze_transforms,
    MAYA_UX_OT_reset_transforms,
    MAYA_UX_OT_delete_history,
    MAYA_UX_OT_combine,
    MAYA_UX_OT_separate,
    MAYA_UX_OT_toggle_symmetry,
    MAYA_UX_OT_add_mirror_modifier,
    MAYA_UX_OT_duplicate_in_place,
    MAYA_UX_OT_duplicate_with_transform,
    MAYA_UX_OT_duplicate_special,
    MAYA_UX_OT_toggle_discrete_snap,
    MAYA_UX_OT_toggle_relative_snap,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    global _LAST_DUP_STATE
    _LAST_DUP_STATE = None
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
