from __future__ import annotations

import bpy
from bpy.props import EnumProperty
from mathutils import Vector


def _next_group_name(existing_names) -> str:
    idx = 1
    while f"group{idx}" in existing_names:
        idx += 1
    return f"group{idx}"


class MAYA_UX_OT_group_selected(bpy.types.Operator):
    """Group selected objects (Ctrl+G) as Maya Null Empty or Blender Collection."""

    bl_idname = "maya_ux.group_selected"
    bl_label = "Group Selected (Maya)"
    bl_options = {"REGISTER", "UNDO"}

    mode_override: EnumProperty(
        name="Mode Override",
        items=[
            ("PREFS", "From Preferences", "Use addon preferences"),
            ("EMPTY", "Null Empty", "Create Empty group"),
            ("COLLECTION", "Collection", "Create Collection group"),
        ],
        default="PREFS",
    )
    pivot_override: EnumProperty(
        name="Pivot Override",
        items=[
            ("PREFS", "From Preferences", "Use addon preferences"),
            ("CENTER", "Selection Center", "Center on selection"),
            ("ORIGIN", "World Origin", "Place at (0, 0, 0)"),
        ],
        default="PREFS",
    )

    def execute(self, context):
        from .preferences import get_prefs

        selected = list(context.selected_objects)
        if not selected:
            self.report({"WARNING"}, "Select at least one object to Group")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        prefs = get_prefs(context)
        mode = prefs.group_mode if self.mode_override == "PREFS" else self.mode_override
        pivot = prefs.group_pivot if self.pivot_override == "PREFS" else self.pivot_override

        if mode == "COLLECTION":
            col_name = _next_group_name(bpy.data.collections)
            new_col = bpy.data.collections.new(col_name)
            context.scene.collection.children.link(new_col)
            for obj in selected:
                for old_col in list(obj.users_collection):
                    old_col.objects.unlink(obj)
                new_col.objects.link(obj)
            self.report({"INFO"}, f"Grouped {len(selected)} object(s) into Collection '{col_name}'")
            return {"FINISHED"}

        # EMPTY mode (Maya Null Group)
        grp_name = _next_group_name(bpy.data.objects)
        grp = bpy.data.objects.new(grp_name, None)
        grp.empty_display_type = "PLAIN_AXES"
        grp.empty_display_size = 0.5

        target_col = (
            context.active_object.users_collection[0]
            if context.active_object and context.active_object.users_collection
            else context.scene.collection
        )
        target_col.objects.link(grp)

        if pivot == "CENTER":
            center = sum((obj.matrix_world.translation for obj in selected), Vector((0.0, 0.0, 0.0))) / len(selected)
            grp.location = center
        else:
            grp.location = Vector((0.0, 0.0, 0.0))

        context.view_layer.update()
        inv_grp = grp.matrix_world.inverted()

        # Preserve sub-hierarchies: only re-parent selected roots whose parent isn't also selected.
        selected_set = set(selected)
        for obj in selected:
            if obj.parent in selected_set:
                continue
            obj.parent = grp
            obj.matrix_parent_inverse = inv_grp

        bpy.ops.object.select_all(action="DESELECT")
        grp.select_set(True)
        context.view_layer.objects.active = grp
        self.report({"INFO"}, f"Created Maya group '{grp_name}'")
        return {"FINISHED"}


class MAYA_UX_OT_parent_to_active(bpy.types.Operator):
    """Parent selected objects to active object preserving world transforms (P)."""

    bl_idname = "maya_ux.parent_to_active"
    bl_label = "Parent to Active"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.active_object
        if active is None:
            self.report({"WARNING"}, "No active object to parent to")
            return {"CANCELLED"}

        children = [obj for obj in context.selected_objects if obj != active]
        if not children:
            self.report({"WARNING"}, "Select children and an active parent object")
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        inv_active = active.matrix_world.inverted()
        for obj in children:
            obj.parent = active
            obj.matrix_parent_inverse = inv_active
        return {"FINISHED"}


class MAYA_UX_OT_unparent_keep_transform(bpy.types.Operator):
    """Unparent selected objects while keeping world transforms (Shift+P)."""

    bl_idname = "maya_ux.unparent_keep_transform"
    bl_label = "Unparent (Keep Transform)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            return {"CANCELLED"}

        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        for obj in selected:
            if obj.parent is None:
                continue
            world_mat = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = world_mat
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_group_selected,
    MAYA_UX_OT_parent_to_active,
    MAYA_UX_OT_unparent_keep_transform,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
