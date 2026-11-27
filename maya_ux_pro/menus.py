from __future__ import annotations

import bpy

from .preferences import is_macos_layout


class VIEW3D_MT_maya_component_pie(bpy.types.Menu):
    """Maya RMB Marking Menu for Object & Component mode switching."""

    bl_idname = "VIEW3D_MT_maya_component_pie"
    bl_label = "Maya Component Marking Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        # W: Vertex
        op = pie.operator("maya_ux.component_mode", text="Vertex", icon="VERTEXSEL")
        op.mode = "VERT"

        # E: Face
        op = pie.operator("maya_ux.component_mode", text="Face", icon="FACESEL")
        op.mode = "FACE"

        # S: Object Mode
        op = pie.operator("maya_ux.component_mode", text="Object Mode", icon="OBJECT_DATAMODE")
        op.mode = "OBJECT"

        # N: Edge
        op = pie.operator("maya_ux.component_mode", text="Edge", icon="EDGESEL")
        op.mode = "EDGE"

        # NW: Multi-Component
        op = pie.operator("maya_ux.component_mode", text="Multi-Component", icon="UV_VERTEXSEL")
        op.mode = "MULTI"

        # NE: Edge Loop (Edit) or Object Shading & Frame Selected (Object)
        if context.mode == "EDIT_MESH":
            if hasattr(bpy.ops.mesh, "select_edge_loop_multi"):
                pie.operator("mesh.select_edge_loop_multi", text="Select Edge Loop", icon="EDGESEL")
            else:
                pie.operator("mesh.loop_multi_select", text="Select Edge Loop", icon="EDGESEL").ring = False
        else:
            col = pie.box().column(align=True)
            col.operator("object.shade_smooth", text="Shade Smooth", icon="SHADING_RENDERED")
            col.operator("object.shade_auto_smooth", text="Shade Auto Smooth", icon="MOD_SMOOTH")
            col.operator("object.shade_flat", text="Shade Flat", icon="SHADING_SOLID")
            col.separator()
            col.operator("view3d.view_selected", text="Frame Selected (F)", icon="ZOOM_SELECTED")

        # SW: Isolate Select
        pie.operator("maya_ux.isolate_select", text="Isolate Select", icon="HIDE_OFF")

        # SE: Center Pivot
        pie.operator("maya_ux.pivot_action", text="Center Pivot", icon="PIVOT_BOUNDBOX").action = "CENTER"


class VIEW3D_MT_maya_modeling_pie(bpy.types.Menu):
    """Maya Shift+RMB context-aware Modeling Marking Menu."""

    bl_idname = "VIEW3D_MT_maya_modeling_pie"
    bl_label = "Maya Modeling Marking Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()

        if context.mode == "EDIT_MESH":
            # W / E / S / N / NW / NE / SW / SE
            pie.operator("mesh.bevel", text="Bevel", icon="MOD_BEVEL")
            pie.operator("maya_ux.maya_extrude", text="Extrude (Maya)", icon="FACESEL")
            pie.operator("maya_ux.target_weld", text="Target Weld", icon="AUTOMERGE_ON")
            op = pie.operator("wm.tool_set_by_id", text="Insert Edge Loop", icon="MOD_MULTIRES")
            op.name = "builtin.loop_cut"
            pie.operator("mesh.knife_tool", text="Multi-Cut (Knife)", icon="SCULPTMODE_HLT")
            pie.operator("mesh.bridge_edge_loops", text="Bridge Loops", icon="MOD_SOLIDIFY")
            pie.operator("wm.call_menu", text="Merge (M)", icon="SNAP_VERTEX").name = "VIEW3D_MT_edit_mesh_merge"
            pie.operator("mesh.vertices_smooth", text="Smooth Vertices", icon="MOD_SMOOTH")
        else:
            pie.operator("mesh.primitive_cube_add", text="Polygon Cube", icon="MESH_CUBE")
            pie.operator("mesh.primitive_uv_sphere_add", text="Polygon Sphere", icon="MESH_UVSPHERE")
            pie.operator("maya_ux.freeze_transforms", text="Freeze Transforms", icon="FREEZE")
            pie.operator("mesh.primitive_cylinder_add", text="Polygon Cylinder", icon="MESH_CYLINDER")
            pie.operator("mesh.primitive_plane_add", text="Polygon Plane", icon="MESH_PLANE")
            pie.operator("maya_ux.combine", text="Combine", icon="SELECT_EXTEND")
            pie.operator("maya_ux.delete_history", text="Delete History", icon="TRASH")
            pie.operator("maya_ux.separate", text="Separate", icon="UNLINKED")


class VIEW3D_MT_maya_view_pie(bpy.types.Menu):
    """Maya Spacebar View & Quad Camera Pie Menu."""

    bl_idname = "VIEW3D_MT_maya_view_pie"
    bl_label = "Maya View Marking Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        pie.operator("view3d.view_axis", text="Left", icon="TRIA_LEFT").type = "LEFT"
        pie.operator("view3d.view_axis", text="Right", icon="TRIA_RIGHT").type = "RIGHT"
        pie.operator("view3d.view_axis", text="Bottom", icon="TRIA_DOWN").type = "BOTTOM"
        pie.operator("view3d.view_axis", text="Top", icon="TRIA_UP").type = "TOP"
        pie.operator("view3d.view_axis", text="Front", icon="AXIS_FRONT").type = "FRONT"
        pie.operator("view3d.view_axis", text="Back", icon="AXIS_SIDE").type = "BACK"
        pie.operator("view3d.view_camera", text="Camera", icon="CAMERA_DATA")
        pie.operator("maya_ux.toggle_quad_view", text="Toggle Quad View", icon="VIEW_ORTHO")


class VIEW3D_MT_maya_pivot_pie(bpy.types.Menu):
    """Maya Alt+D Pivot Operations Pie Menu."""

    bl_idname = "VIEW3D_MT_maya_pivot_pie"
    bl_label = "Maya Pivot Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        pie.operator("maya_ux.pivot_action", text="World Origin (0,0,0)", icon="WORLD").action = "WORLD_ORIGIN"
        pie.operator("maya_ux.pivot_action", text="Match Active Pivot", icon="PIVOT_ACTIVE").action = "TO_ACTIVE"
        pie.operator("maya_ux.pivot_action", text="Bottom Center", icon="ANCHOR_BOTTOM").action = "BOTTOM_CENTER"
        pie.operator("maya_ux.pivot_action", text="Center Pivot", icon="PIVOT_BOUNDBOX").action = "CENTER"
        pie.operator("maya_ux.toggle_edit_pivot", text="Edit Pivot (D)", icon="OBJECT_ORIGIN")
        pie.operator("maya_ux.reset_transforms", text="Reset Transforms", icon="LOOP_BACK").channel = "ALL"


class GRAPH_MT_maya_tangents_pie(bpy.types.Menu):
    """Maya Graph Editor Tangents & View Marking Menu (T)."""

    bl_idname = "GRAPH_MT_maya_tangents_pie"
    bl_label = "Maya Graph Tangents"

    def draw(self, context):
        pie = self.layout.menu_pie()
        pie.operator("maya_ux.graph_tangent", text="Linear (1)", icon="IPO_LINEAR").preset = "LINEAR"
        pie.operator("maya_ux.graph_tangent", text="Spline (4)", icon="IPO_BEZIER").preset = "SPLINE"
        pie.operator("maya_ux.graph_tangent", text="Stepped (3)", icon="IPO_CONSTANT").preset = "STEPPED"
        pie.operator("maya_ux.graph_tangent", text="Auto / Flat (2)", icon="HANDLE_AUTO").preset = "AUTO_FLAT"
        pie.operator("maya_ux.graph_tangent", text="Break Tangents (Free)", icon="HANDLE_FREE").preset = "FREE"
        pie.operator("maya_ux.graph_tangent", text="Unify Tangents (Aligned)", icon="HANDLE_ALIGNED").preset = "ALIGNED"
        pie.operator("graph.view_selected", text="Frame Selected (F)", icon="ZOOM_SELECTED")
        pie.operator("graph.view_all", text="Frame All (A)", icon="VIEWALL")


class IMAGE_MT_maya_uv_pie(bpy.types.Menu):
    """Maya UV Editor RMB Marking Menu."""

    bl_idname = "IMAGE_MT_maya_uv_pie"
    bl_label = "Maya UV Marking Menu"

    def draw(self, context):
        pie = self.layout.menu_pie()
        m = "⌘" if is_macos_layout(context) else "Ctrl+"
        s = "⇧" if is_macos_layout(context) else "Shift+"
        pie.operator("maya_ux.uv_mode", text="UV Vertex", icon="UV_VERTEXSEL").mode = "VERTEX"
        pie.operator("maya_ux.uv_mode", text="UV Face", icon="UV_FACESEL").mode = "FACE"
        pie.operator("maya_ux.uv_mode", text="UV Shell (Island)", icon="UV_ISLANDSEL").mode = "ISLAND"
        pie.operator("maya_ux.uv_mode", text="UV Edge", icon="UV_EDGESEL").mode = "EDGE"
        pie.operator("uv.mark_seam", text=f"Cut Seams ({s}X)", icon="MOD_EDGESPLIT").clear = False
        pie.operator("uv.stitch", text=f"Sew / Stitch ({s}S)", icon="AUTOMERGE_ON")
        pie.operator("uv.unwrap", text=f"Unfold ({m}U)", icon="MOD_UVPROJECT")
        pie.operator("uv.pack_islands", text=f"Layout UVs ({m}L)", icon="UV_DATA")


CLASSES = (
    VIEW3D_MT_maya_component_pie,
    VIEW3D_MT_maya_modeling_pie,
    VIEW3D_MT_maya_view_pie,
    VIEW3D_MT_maya_pivot_pie,
    GRAPH_MT_maya_tangents_pie,
    IMAGE_MT_maya_uv_pie,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
