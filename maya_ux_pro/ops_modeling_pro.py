from __future__ import annotations

import bmesh
import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


def weld_vertices_bmesh(obj: bpy.types.Object, src_idx: int, dst_idx: int) -> bool:
    """Merge src_idx vertex into dst_idx vertex at dst's position using bmesh."""
    if obj is None or obj.type != "MESH" or src_idx == dst_idx:
        return False
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    if not (0 <= src_idx < len(bm.verts) and 0 <= dst_idx < len(bm.verts)):
        return False
    src_v = bm.verts[src_idx]
    dst_v = bm.verts[dst_idx]
    if not src_v.is_valid or not dst_v.is_valid:
        return False
    target_co = dst_v.co.copy()
    src_v.co = target_co
    bmesh.ops.pointmerge(bm, verts=[src_v, dst_v], merge_co=target_co)
    bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
    return True


def _find_nearest_vert_2d(
    context,
    obj: bpy.types.Object,
    mouse_2d: tuple[float, float],
    max_px: float = 24.0,
    exclude_idx: int = -1,
) -> tuple[int, Vector] | None:
    region = context.region
    rv3d = getattr(context.space_data, "region_3d", None)
    if region is None or rv3d is None or obj is None or obj.type != "MESH":
        return None

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    mw = obj.matrix_world
    mx, my = mouse_2d

    best_idx = -1
    best_dist = max_px
    best_pos: Vector | None = None

    for v in bm.verts:
        if not v.is_valid or v.hide or v.index == exclude_idx:
            continue
        p2d = location_3d_to_region_2d(region, rv3d, mw @ v.co)
        if p2d is None:
            continue
        dist = ((p2d.x - mx) ** 2 + (p2d.y - my) ** 2) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_idx = v.index
            best_pos = p2d

    if best_idx >= 0 and best_pos is not None:
        return (best_idx, best_pos)
    return None


def _draw_target_weld_overlay(op, context):
    if op._hover_pos is None and op._src_pos is None:
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")

    if op._src_pos is not None:
        end_pos = op._dst_pos if op._dst_pos is not None else Vector(op._mouse_2d)
        line_coords = [(op._src_pos.x, op._src_pos.y), (end_pos.x, end_pos.y)]
        gpu.state.line_width_set(2.5)
        batch = batch_for_shader(shader, "LINES", {"pos": line_coords})
        shader.bind()
        shader.uniform_float("color", (0.15, 0.90, 1.0, 0.95))
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

        gpu.state.point_size_set(10.0)
        src_batch = batch_for_shader(shader, "POINTS", {"pos": [(op._src_pos.x, op._src_pos.y)]})
        shader.uniform_float("color", (1.0, 0.55, 0.1, 1.0))
        src_batch.draw(shader)

        if op._dst_pos is not None:
            dst_batch = batch_for_shader(shader, "POINTS", {"pos": [(op._dst_pos.x, op._dst_pos.y)]})
            shader.uniform_float("color", (0.2, 1.0, 0.4, 1.0))
            dst_batch.draw(shader)
        gpu.state.point_size_set(1.0)

    elif op._hover_pos is not None:
        gpu.state.point_size_set(9.0)
        hov_batch = batch_for_shader(shader, "POINTS", {"pos": [(op._hover_pos.x, op._hover_pos.y)]})
        shader.bind()
        shader.uniform_float("color", (1.0, 0.90, 0.15, 1.0))
        hov_batch.draw(shader)
        gpu.state.point_size_set(1.0)

    gpu.state.blend_set("NONE")


class MAYA_UX_OT_target_weld(bpy.types.Operator):
    """Maya-style Interactive Target Weld: drag or click Vert A -> Vert B (RMB/ESC to finish)."""

    bl_idname = "maya_ux.target_weld"
    bl_label = "Target Weld"
    bl_options = {"REGISTER", "UNDO"}

    _handle = None
    _src_idx: int = -1
    _src_pos: Vector | None = None
    _dst_idx: int = -1
    _dst_pos: Vector | None = None
    _hover_pos: Vector | None = None
    _mouse_2d: tuple[float, float] = (0.0, 0.0)
    _dragging: bool = False

    def _cleanup(self, context):
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()

    def _reset_pick(self):
        self._src_idx = -1
        self._src_pos = None
        self._dst_idx = -1
        self._dst_pos = None
        self._dragging = False

    def invoke(self, context, event):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, "Select a Mesh object for Target Weld")
            return {"CANCELLED"}

        if context.mode != "EDIT_MESH":
            bpy.ops.object.mode_set(mode="EDIT")
        context.tool_settings.mesh_select_mode = (True, False, False)

        self._reset_pick()
        self._mouse_2d = (event.mouse_region_x, event.mouse_region_y)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_target_weld_overlay, (self, context), "WINDOW", "POST_PIXEL"
        )
        if context.area is not None:
            context.area.header_text_set("Target Weld: Drag or Click Source Vert -> Target Vert  |  RMB / ESC: Exit")
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.alt or event.type in {"WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM"}:
            return {"PASS_THROUGH"}

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            self._cleanup(context)
            return {"FINISHED"}

        obj = context.active_object
        if obj is None or context.mode != "EDIT_MESH":
            self._cleanup(context)
            return {"CANCELLED"}

        self._mouse_2d = (event.mouse_region_x, event.mouse_region_y)

        if event.type == "MOUSEMOVE":
            if self._src_idx >= 0:
                hit = _find_nearest_vert_2d(context, obj, self._mouse_2d, exclude_idx=self._src_idx)
                self._dst_idx, self._dst_pos = hit if hit else (-1, None)
            else:
                hit = _find_nearest_vert_2d(context, obj, self._mouse_2d)
                self._hover_pos = hit[1] if hit else None
            if context.area is not None:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self._src_idx < 0:
                hit = _find_nearest_vert_2d(context, obj, self._mouse_2d)
                if hit:
                    self._src_idx, self._src_pos = hit
                    self._hover_pos = None
                    self._dragging = True
            else:
                hit = _find_nearest_vert_2d(context, obj, self._mouse_2d, exclude_idx=self._src_idx)
                if hit:
                    if weld_vertices_bmesh(obj, self._src_idx, hit[0]):
                        bpy.ops.ed.undo_push(message="Target Weld")
                    self._reset_pick()
            if context.area is not None:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._dragging:
            self._dragging = False
            if self._src_idx >= 0:
                hit = _find_nearest_vert_2d(context, obj, self._mouse_2d, exclude_idx=self._src_idx)
                if hit and hit[0] != self._src_idx:
                    if weld_vertices_bmesh(obj, self._src_idx, hit[0]):
                        bpy.ops.ed.undo_push(message="Target Weld")
                    self._reset_pick()
            if context.area is not None:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}


class MAYA_UX_OT_merge_to_last(bpy.types.Operator):
    """Merge selected vertices to active (last selected) vertex, falling back to center."""

    bl_idname = "maya_ux.merge_to_last"
    bl_label = "Merge to Last"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode != "EDIT_MESH":
            self.report({"WARNING"}, "Switch to Edit Mode first")
            return {"CANCELLED"}
        try:
            bpy.ops.mesh.merge(type="LAST")
        except RuntimeError:
            bpy.ops.mesh.merge(type="CENTER")
        return {"FINISHED"}


CLASSES = (
    MAYA_UX_OT_target_weld,
    MAYA_UX_OT_merge_to_last,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
