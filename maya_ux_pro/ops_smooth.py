from __future__ import annotations

import bpy
from bpy.props import IntProperty

SMOOTH_MOD_NAME = "MayaSmoothPreview"


def _target_meshes(context) -> list[bpy.types.Object]:
    objs = [obj for obj in context.selected_objects if obj.type == "MESH"]
    active = context.active_object
    if active is not None and active.type == "MESH" and active not in objs:
        objs.append(active)
    return objs


def get_smooth_preview_level(obj: bpy.types.Object | None) -> int:
    """Return active Maya smooth preview level (1, 2, or 3) for display in UI."""
    if obj is None or obj.type != "MESH":
        return 1
    mod = obj.modifiers.get(SMOOTH_MOD_NAME)
    if mod is None or not mod.show_viewport:
        return 1
    return 3 if mod.show_on_cage else 2


class MAYA_UX_OT_smooth_preview(bpy.types.Operator):
    """Maya Smooth Mesh Preview: 1 = Rough Cage, 2 = Cage + Smooth Proxy, 3 = Full Smooth."""

    bl_idname = "maya_ux.smooth_preview"
    bl_label = "Maya Smooth Preview"
    bl_options = {"REGISTER", "UNDO"}

    level: IntProperty(name="Preview Level", min=1, max=3, default=1)

    def execute(self, context):
        from .preferences import get_prefs

        meshes = _target_meshes(context)
        if not meshes:
            self.report({"WARNING"}, "Select at least one Mesh object")
            return {"CANCELLED"}

        pref_levels = max(1, int(get_prefs(context).smooth_preview_levels))

        for obj in meshes:
            mod = obj.modifiers.get(SMOOTH_MOD_NAME)

            if self.level == 1:
                if mod is not None:
                    mod.show_viewport = False
                continue

            if mod is None:
                mod = obj.modifiers.new(name=SMOOTH_MOD_NAME, type="SUBSURF")

            mod.show_viewport = True
            mod.show_in_editmode = True
            mod.render_levels = pref_levels

            if self.level == 2:
                mod.levels = max(1, pref_levels - 1)
                mod.show_on_cage = False
                mod.show_only_control_edges = False
            else:
                mod.levels = pref_levels
                mod.show_on_cage = True
                mod.show_only_control_edges = True

        return {"FINISHED"}


class MAYA_UX_OT_smooth_preview_step(bpy.types.Operator):
    """Increment or decrement Maya Smooth Preview subdivision levels (Page Up / Page Down)."""

    bl_idname = "maya_ux.smooth_preview_step"
    bl_label = "Maya Smooth Preview Step"
    bl_options = {"REGISTER", "UNDO"}

    delta: IntProperty(name="Level Delta", default=1)

    def execute(self, context):
        meshes = _target_meshes(context)
        if not meshes:
            self.report({"WARNING"}, "Select at least one Mesh object")
            return {"CANCELLED"}

        for obj in meshes:
            mod = obj.modifiers.get(SMOOTH_MOD_NAME)
            if self.delta > 0:
                if mod is None:
                    mod = obj.modifiers.new(name=SMOOTH_MOD_NAME, type="SUBSURF")
                    mod.show_viewport = True
                    mod.show_in_editmode = True
                    mod.show_on_cage = True
                    mod.levels = 1
                elif not mod.show_viewport:
                    mod.show_viewport = True
                    mod.show_in_editmode = True
                    mod.levels = max(1, mod.levels)
                else:
                    mod.levels = min(4, mod.levels + self.delta)
            else:
                if mod is not None and mod.show_viewport:
                    if mod.levels <= 1:
                        mod.show_viewport = False
                    else:
                        mod.levels = max(1, mod.levels + self.delta)
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_smooth_preview,
    MAYA_UX_OT_smooth_preview_step,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
