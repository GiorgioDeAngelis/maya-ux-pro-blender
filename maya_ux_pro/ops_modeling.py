from __future__ import annotations

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from mathutils import Euler, Vector

from .ops_smooth import SMOOTH_MOD_NAME

_LAST_DUP_STATE: dict | None = None
MAX_ADD_DIVISIONS_FACES = 500_000


def _compute_add_divisions_cuts(method: str, divisions: int) -> tuple[int, int]:
    """Convert Maya Add Divisions parameters into BMesh edge cut counts (quads, triangles)."""
    if method == "EXPONENTIAL":
        lvl = max(1, min(int(divisions), 4))
        quad_cuts = (2 ** lvl) - 1
        tri_sub_cuts = (2 ** (lvl - 1)) - 1
    else:
        lvl = max(1, int(divisions))
        quad_cuts = lvl
        tri_sub_cuts = lvl - 1
    return quad_cuts, tri_sub_cuts


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


class MAYA_UX_OT_add_divisions(bpy.types.Operator):
    """Linearly subdivide selected polygon meshes, faces, or edges (Maya Edit Mesh > Add Divisions)."""

    bl_idname = "maya_ux.add_divisions"
    bl_label = "Add Divisions"
    bl_description = "Linearly subdivide selected polygon meshes, faces, or edges (Maya Edit Mesh > Add Divisions)"
    bl_options = {"REGISTER", "UNDO"}

    method: EnumProperty(
        name="Method",
        items=[
            ("EXPONENTIAL", "Exponentially", "Multiply divisions exponentially (2^n segments per edge, Maya default)"),
            ("LINEAR", "Linearly", "Add exact linear cuts per edge (n cuts = n+1 segments)"),
        ],
        default="EXPONENTIAL",
    )
    subdivide_mode: EnumProperty(
        name="Mode",
        items=[
            ("QUADS", "Quads", "Subdivide faces into clean quad grids"),
            ("TRIANGLES", "Triangles", "Subdivide faces into centered triangles"),
        ],
        default="QUADS",
    )
    divisions: IntProperty(
        name="Divisions",
        description="Division levels (Exponential) or cuts per edge (Linear)",
        default=1,
        min=1,
        max=16,
        soft_max=4,
    )
    smoothness: FloatProperty(
        name="Smoothness",
        description="0.0 preserves flat Maya Add Divisions silhouette",
        default=0.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    @classmethod
    def poll(cls, context):
        if context.mode == "EDIT_MESH":
            in_mode = getattr(context, "objects_in_mode", ()) or ()
            if any(o is not None and o.type == "MESH" for o in in_mode):
                return True
            active = getattr(context, "active_object", None)
            return active is not None and active.type == "MESH"
        selected = getattr(context, "selected_objects", ()) or ()
        if any(o is not None and o.type == "MESH" for o in selected):
            return True
        active = getattr(context, "active_object", None)
        return active is not None and active.type == "MESH"

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "method")
        layout.prop(self, "subdivide_mode")
        layout.prop(
            self,
            "divisions",
            text="Division Levels" if self.method == "EXPONENTIAL" else "Linear Cuts",
        )
        layout.prop(self, "smoothness")

    def execute(self, context):
        quad_cuts, tri_sub_cuts = _compute_add_divisions_cuts(self.method, self.divisions)
        modified = 0
        before_faces = 0
        after_faces = 0
        before_verts = 0
        after_verts = 0

        if context.mode == "EDIT_MESH":
            objs = [
                o
                for o in (getattr(context, "objects_in_mode_unique_data", ()) or ())
                if o is not None and o.type == "MESH"
            ]
            if not objs:
                active = getattr(context, "active_object", None)
                if active is not None and active.type == "MESH":
                    objs = [active]

            for obj in objs:
                bm = bmesh.from_edit_mesh(obj.data)
                sel_faces = [f for f in bm.faces if f.select]
                sel_edges = [e for e in bm.edges if e.select]

                if sel_faces:
                    est = (
                        len(sel_faces) * ((quad_cuts + 1) ** 2)
                        if self.subdivide_mode == "QUADS"
                        else len(sel_faces) * ((tri_sub_cuts + 1) ** 2) * 4
                    )
                    if est > MAX_ADD_DIVISIONS_FACES:
                        self.report(
                            {"WARNING"},
                            f"Add Divisions aborted: estimated {est:,} faces exceeds {MAX_ADD_DIVISIONS_FACES:,} safety limit",
                        )
                        return {"CANCELLED"}

                    before_faces += len(bm.faces)
                    before_verts += len(bm.verts)
                    tag_layer = bm.faces.layers.int.new("_maya_add_div")
                    try:
                        for f in bm.faces:
                            f[tag_layer] = 1 if f.select else 0
                        # Adding a BMesh custom layer reallocates face blocks, invalidating pre-layer BMFace refs.
                        target_edges = list({e for f in bm.faces if f[tag_layer] == 1 for e in f.edges})
                        if self.subdivide_mode == "QUADS":
                            bmesh.ops.subdivide_edges(
                                bm,
                                edges=target_edges,
                                cuts=quad_cuts,
                                use_grid_fill=True,
                                smooth=self.smoothness,
                                quad_corner_type="STRAIGHT_CUT",
                            )
                            for f in bm.faces:
                                if f.is_valid and f[tag_layer] == 1:
                                    f.select_set(True)
                        else:
                            if tri_sub_cuts > 0:
                                bmesh.ops.subdivide_edges(
                                    bm,
                                    edges=target_edges,
                                    cuts=tri_sub_cuts,
                                    use_grid_fill=True,
                                    smooth=self.smoothness,
                                    quad_corner_type="STRAIGHT_CUT",
                                )
                            poke_faces = [f for f in bm.faces if f.is_valid and f[tag_layer] == 1]
                            res_poke = bmesh.ops.poke(bm, faces=poke_faces)
                            for f in res_poke.get("faces", ()):
                                if f.is_valid:
                                    f.select_set(True)
                    finally:
                        bm.faces.layers.int.remove(tag_layer)

                    bm.select_flush_mode()
                    bm.normal_update()
                    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
                    after_faces += len(bm.faces)
                    after_verts += len(bm.verts)
                    modified += 1
                elif sel_edges:
                    before_faces += len(bm.faces)
                    before_verts += len(bm.verts)
                    res = bmesh.ops.subdivide_edges(
                        bm,
                        edges=sel_edges,
                        cuts=quad_cuts,
                        use_grid_fill=False,
                        smooth=self.smoothness,
                    )
                    for g in res.get("geom", ()):
                        if isinstance(g, bmesh.types.BMEdge) and g.is_valid:
                            g.select_set(True)
                    bm.select_flush_mode()
                    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
                    after_faces += len(bm.faces)
                    after_verts += len(bm.verts)
                    modified += 1

            if modified == 0:
                self.report({"WARNING"}, "Select faces or edges to Add Divisions")
                return {"CANCELLED"}

            self.report(
                {"INFO"},
                f"Add Divisions: {before_faces} -> {after_faces} faces ({before_verts} -> {after_verts} verts)",
            )
            return {"FINISHED"}

        # Object Mode
        meshes = [o for o in (getattr(context, "selected_objects", ()) or ()) if o.type == "MESH"]
        if not meshes and context.active_object is not None and context.active_object.type == "MESH":
            meshes = [context.active_object]

        seen_ptrs: set[int] = set()
        unique_meshes = []
        for obj in meshes:
            data = obj.data
            if data is None:
                continue
            ptr = data.as_pointer()
            if ptr not in seen_ptrs:
                seen_ptrs.add(ptr)
                unique_meshes.append(data)

        total_est = 0
        mult = ((quad_cuts + 1) ** 2) if self.subdivide_mode == "QUADS" else (((tri_sub_cuts + 1) ** 2) * 4)
        for mesh in unique_meshes:
            total_est += len(mesh.polygons) * mult
        if total_est > MAX_ADD_DIVISIONS_FACES:
            self.report(
                {"WARNING"},
                f"Add Divisions aborted: estimated {total_est:,} faces exceeds {MAX_ADD_DIVISIONS_FACES:,} safety limit",
            )
            return {"CANCELLED"}

        for mesh in unique_meshes:
            bm = bmesh.new()
            try:
                bm.from_mesh(mesh)
                if len(bm.edges) == 0:
                    continue
                before_faces += len(bm.faces)
                before_verts += len(bm.verts)
                if self.subdivide_mode == "QUADS":
                    bmesh.ops.subdivide_edges(
                        bm,
                        edges=list(bm.edges),
                        cuts=quad_cuts,
                        use_grid_fill=True,
                        smooth=self.smoothness,
                        quad_corner_type="STRAIGHT_CUT",
                    )
                else:
                    if tri_sub_cuts > 0:
                        bmesh.ops.subdivide_edges(
                            bm,
                            edges=list(bm.edges),
                            cuts=tri_sub_cuts,
                            use_grid_fill=True,
                            smooth=self.smoothness,
                            quad_corner_type="STRAIGHT_CUT",
                        )
                    if len(bm.faces) > 0:
                        bmesh.ops.poke(bm, faces=list(bm.faces))
                bm.normal_update()
                bm.to_mesh(mesh)
                mesh.update()
                after_faces += len(bm.faces)
                after_verts += len(bm.verts)
                modified += 1
            finally:
                bm.free()

        if modified == 0:
            self.report({"WARNING"}, "Select a Mesh object with geometry to Add Divisions")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Add Divisions: {before_faces} -> {after_faces} faces ({before_verts} -> {after_verts} verts)",
        )
        return {"FINISHED"}


class MAYA_UX_OT_smooth_mesh(bpy.types.Operator):
    """Subdivide and smooth polygon meshes or selected faces using Catmull-Clark (Maya Mesh > Smooth)."""

    bl_idname = "maya_ux.smooth_mesh"
    bl_label = "Smooth"
    bl_description = "Subdivide and smooth polygon meshes or selected faces using Catmull-Clark (Maya Mesh > Smooth)"
    bl_options = {"REGISTER", "UNDO"}

    divisions: IntProperty(
        name="Division Levels",
        description="Number of Catmull-Clark subdivision smooth iterations",
        default=1,
        min=1,
        max=4,
    )
    keep_border: BoolProperty(
        name="Keep Border",
        description="Preserve boundary corners when smoothing open meshes (Maya Keep Border)",
        default=True,
    )
    use_creases: BoolProperty(
        name="Use Creases",
        description="Respect edge crease weights during Catmull-Clark smoothing",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        if context.mode == "EDIT_MESH":
            in_mode = getattr(context, "objects_in_mode", ()) or ()
            if any(o is not None and o.type == "MESH" for o in in_mode):
                return True
            active = getattr(context, "active_object", None)
            return active is not None and active.type == "MESH"
        selected = getattr(context, "selected_objects", ()) or ()
        if any(o is not None and o.type == "MESH" for o in selected):
            return True
        active = getattr(context, "active_object", None)
        return active is not None and active.type == "MESH"

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "divisions")
        layout.prop(self, "keep_border")
        layout.prop(self, "use_creases")

    def execute(self, context):
        modified = 0
        before_faces = 0
        after_faces = 0
        before_verts = 0
        after_verts = 0

        if context.mode == "EDIT_MESH":
            objs = [
                o
                for o in (getattr(context, "objects_in_mode_unique_data", ()) or ())
                if o is not None and o.type == "MESH"
            ]
            if not objs:
                active = getattr(context, "active_object", None)
                if active is not None and active.type == "MESH":
                    objs = [active]

            cuts = (2 ** max(1, min(int(self.divisions), 4))) - 1

            for obj in objs:
                bm = bmesh.from_edit_mesh(obj.data)
                sel_faces = [f for f in bm.faces if f.select]
                if not sel_faces:
                    continue

                est = len(sel_faces) * ((cuts + 1) ** 2)
                if est > MAX_ADD_DIVISIONS_FACES:
                    self.report(
                        {"WARNING"},
                        f"Smooth aborted: estimated {est:,} faces exceeds {MAX_ADD_DIVISIONS_FACES:,} safety limit",
                    )
                    return {"CANCELLED"}

                before_faces += len(bm.faces)
                before_verts += len(bm.verts)
                tag_layer = bm.faces.layers.int.new("_maya_smooth_sel")
                try:
                    for f in bm.faces:
                        f[tag_layer] = 1 if f.select else 0
                    target_edges = list({e for f in bm.faces if f[tag_layer] == 1 for e in f.edges})
                    bmesh.ops.subdivide_edges(
                        bm,
                        edges=target_edges,
                        cuts=cuts,
                        use_grid_fill=True,
                        smooth=1.0,
                        smooth_falloff="SMOOTH",
                        quad_corner_type="STRAIGHT_CUT",
                    )
                    child_faces = [f for f in bm.faces if f.is_valid and f[tag_layer] == 1]
                    child_verts = list({v for f in child_faces for v in f.verts if v.is_valid})
                    if self.keep_border:
                        smooth_verts = [
                            v
                            for v in child_verts
                            if not v.is_boundary
                            and all(lf.is_valid and lf[tag_layer] == 1 for lf in v.link_faces)
                        ]
                    else:
                        smooth_verts = child_verts
                    if smooth_verts:
                        for _step in range(max(1, min(int(self.divisions), 4))):
                            bmesh.ops.smooth_vert(
                                bm,
                                verts=smooth_verts,
                                factor=0.5,
                                use_axis_x=True,
                                use_axis_y=True,
                                use_axis_z=True,
                            )
                    for f in child_faces:
                        f.select_set(True)
                finally:
                    bm.faces.layers.int.remove(tag_layer)

                bm.select_flush_mode()
                bm.normal_update()
                bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
                after_faces += len(bm.faces)
                after_verts += len(bm.verts)
                modified += 1

            if modified == 0:
                self.report({"WARNING"}, "Select faces to Smooth")
                return {"CANCELLED"}

            self.report(
                {"INFO"},
                f"Smooth: {before_faces} -> {after_faces} faces ({before_verts} -> {after_verts} verts)",
            )
            return {"FINISHED"}

        # Object Mode: genuine Catmull-Clark evaluation without mutating existing modifiers
        meshes = [o for o in (getattr(context, "selected_objects", ()) or ()) if o.type == "MESH"]
        if not meshes and context.active_object is not None and context.active_object.type == "MESH":
            meshes = [context.active_object]

        seen_ptrs: set[int] = set()
        unique_meshes = []
        for obj in meshes:
            data = obj.data
            if data is None:
                continue
            ptr = data.as_pointer()
            if ptr not in seen_ptrs:
                seen_ptrs.add(ptr)
                unique_meshes.append(data)

        mult = 4 ** max(1, min(int(self.divisions), 4))
        total_est = sum(len(mesh.polygons) * mult for mesh in unique_meshes)
        if total_est > MAX_ADD_DIVISIONS_FACES:
            self.report(
                {"WARNING"},
                f"Smooth aborted: estimated {total_est:,} faces exceeds {MAX_ADD_DIVISIONS_FACES:,} safety limit",
            )
            return {"CANCELLED"}

        for mesh in unique_meshes:
            if len(mesh.polygons) == 0:
                continue
            before_faces += len(mesh.polygons)
            before_verts += len(mesh.vertices)

            tmp_obj = bpy.data.objects.new("_maya_smooth_tmp", mesh)
            context.scene.collection.objects.link(tmp_obj)
            try:
                mod = tmp_obj.modifiers.new(name="Subsurf", type="SUBSURF")
                mod.subdivision_type = "CATMULL_CLARK"
                mod.levels = self.divisions
                mod.render_levels = self.divisions
                mod.boundary_smooth = "PRESERVE_CORNERS" if self.keep_border else "ALL"
                mod.use_creases = self.use_creases

                dg = context.evaluated_depsgraph_get()
                ev = tmp_obj.evaluated_get(dg)
                sub_me = ev.to_mesh()
                try:
                    bm = bmesh.new()
                    bm.from_mesh(sub_me)
                    bm.normal_update()
                    bm.to_mesh(mesh)
                    bm.free()
                finally:
                    ev.to_mesh_clear()
                mesh.update()
            finally:
                bpy.data.objects.remove(tmp_obj, do_unlink=True)

            after_faces += len(mesh.polygons)
            after_verts += len(mesh.vertices)
            modified += 1

        if modified == 0:
            self.report({"WARNING"}, "Select a Mesh object with faces to Smooth")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"Smooth: {before_faces} -> {after_faces} faces ({before_verts} -> {after_verts} verts)",
        )
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
    MAYA_UX_OT_add_divisions,
    MAYA_UX_OT_smooth_mesh,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    global _LAST_DUP_STATE
    _LAST_DUP_STATE = None
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
