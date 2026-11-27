from __future__ import annotations

import bpy
from bpy.props import EnumProperty

from .ops_smooth import get_smooth_preview_level
from .preferences import get_prefs


def draw_maya_shelf(self, context):
    """Maya Top Shelf with 4 Menu Set tabs (Poly / Retopo / LookDev / Display) in 3D Viewport header."""
    prefs = get_prefs(context)
    if not prefs.show_top_shelf:
        return

    layout = self.layout
    scene = context.scene
    ts = scene.tool_settings
    space = context.space_data

    layout.separator(factor=0.6)
    row = layout.row(align=True)

    # Live badges: EDIT PIVOT & LIVE SURFACE
    if ts.use_transform_data_origin:
        sub = row.row(align=True)
        sub.alert = True
        sub.operator("maya_ux.toggle_edit_pivot", text="EDIT PIVOT", icon="OBJECT_ORIGIN", depress=True)
    else:
        row.operator("maya_ux.toggle_edit_pivot", text="", icon="OBJECT_ORIGIN")

    live_name = getattr(scene, "maya_ux_live_surface", "")
    if live_name:
        sub_live = row.row(align=True)
        sub_live.operator("maya_ux.clear_live", text=f"LIVE: {live_name[:10]}", icon="SNAP_ON", depress=True)

    # Menu Set tab selector
    tab = getattr(scene, "maya_ux_shelf_tab", "DISPLAY")
    row.prop(scene, "maya_ux_shelf_tab", text="", expand=False)

    if tab == "POLY":
        row.operator("mesh.primitive_cube_add", text="", icon="MESH_CUBE")
        row.operator("mesh.primitive_uv_sphere_add", text="", icon="MESH_UVSPHERE")
        row.operator("mesh.primitive_cylinder_add", text="", icon="MESH_CYLINDER")
        row.operator("mesh.primitive_plane_add", text="", icon="MESH_PLANE")
        row.operator("maya_ux.combine", text="", icon="SELECT_EXTEND")
        row.operator("maya_ux.separate", text="", icon="UNLINKED")
        row.operator("maya_ux.maya_extrude", text="Extrude", icon="FACESEL")
        row.operator("maya_ux.add_divisions", text="Div", icon="MESH_GRID")
        row.operator("maya_ux.smooth_mesh", text="Smooth", icon="MOD_SUBSURF")
        row.operator("maya_ux.target_weld", text="Weld", icon="AUTOMERGE_ON")
        row.operator("maya_ux.pivot_action", text="", icon="PIVOT_BOUNDBOX").action = "CENTER"
        row.operator("maya_ux.freeze_transforms", text="", icon="FREEZE")
        row.operator("maya_ux.delete_history", text="", icon="TRASH")

    elif tab == "RETOPO":
        row.operator("maya_ux.make_live", text="Live", icon="SNAP_FACE" if live_name else "SNAP_OFF", depress=bool(live_name))
        row.operator("maya_ux.start_quad_draw", text="Quad Draw", icon="MOD_BUILD")
        row.operator("maya_ux.retopo_relax", text="Relax", icon="MOD_SMOOTH")
        row.operator("maya_ux.target_weld", text="Weld", icon="AUTOMERGE_ON")
        row.operator("maya_ux.finish_quad_draw", text="Bake", icon="CHECKMARK")

    elif tab == "LOOKDEV":
        for preset, lbl in (
            ("LAMBERT1", "Lamb"),
            ("BLINN1", "Blinn"),
            ("CLAY_SCULPT", "Clay"),
            ("CHROME_CHECK", "Chrome"),
            ("UV_CHECKER", "UV"),
        ):
            row.operator("maya_ux.assign_maya_material", text=lbl).preset = preset
        row.operator("maya_ux.setup_studio_lighting", text="", icon="LIGHT_AREA")
        row.operator("maya_ux.cam_from_view", text="", icon="CAMERA_DATA")

    else:  # DISPLAY
        active_snaps = set(ts.snap_elements) if ts.use_snap else set()
        for stype, lbl in (("GRID", "X"), ("EDGE", "C"), ("VERTEX", "V")):
            row.operator("maya_ux.maya_snap", text=lbl, depress=(stype in active_snaps)).snap_type = stype
        row.operator("maya_ux.toggle_discrete_snap", text="J", depress=("INCREMENT" in active_snaps))

        soft_on = ts.use_proportional_edit if context.mode == "EDIT_MESH" else ts.use_proportional_edit_objects
        row.operator("maya_ux.toggle_soft_select", text="B", depress=bool(soft_on))

        cur_smooth = get_smooth_preview_level(context.active_object)
        for lvl in (1, 2, 3):
            row.operator("maya_ux.smooth_preview", text=str(lvl), depress=(cur_smooth == lvl)).level = lvl

        if space and space.type == "VIEW_3D":
            cur_sh = space.shading.type
            for sh_type, lbl in (("WIREFRAME", "4"), ("SOLID", "5"), ("MATERIAL", "6"), ("RENDERED", "7")):
                row.operator("maya_ux.set_shading", text=lbl, depress=(cur_sh == sh_type)).shading_type = sh_type

        row.operator(
            "maya_ux.toggle_poly_count_hud",
            text="HUD",
            depress=bool(getattr(prefs, "show_poly_count_hud", True)),
        )
        row.operator("maya_ux.pivot_action", text="", icon="PIVOT_BOUNDBOX").action = "CENTER"
        row.operator("maya_ux.freeze_transforms", text="", icon="FREEZE")
        row.operator("maya_ux.delete_history", text="", icon="TRASH")

    row.operator("maya_ux.cheatsheet", text="", icon="HELP")


def register():
    bpy.types.Scene.maya_ux_shelf_tab = EnumProperty(
        name="Maya Shelf Tab",
        description="Switch Maya Top Shelf Menu Set",
        items=[
            ("DISPLAY", "Display", "Display, Snap, Soft Select, Smooth & Shading"),
            ("POLY", "Poly", "Polygon Primitives, Combine, Separate, Weld, Freeze & History"),
            ("RETOPO", "Retopo", "Make Live, Quad Draw, Relax, Weld & Bake"),
            ("LOOKDEV", "LookDev", "Maya Materials, Studio Lights & Camera"),
        ],
        default="DISPLAY",
    )
    bpy.types.VIEW3D_HT_header.append(draw_maya_shelf)


def unregister():
    try:
        bpy.types.VIEW3D_HT_header.remove(draw_maya_shelf)
    except ValueError:
        pass
    if hasattr(bpy.types.Scene, "maya_ux_shelf_tab"):
        del bpy.types.Scene.maya_ux_shelf_tab
