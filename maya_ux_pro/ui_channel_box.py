from __future__ import annotations

import bpy

from . import ops_camtools, ops_viewport
from .ops_smooth import get_smooth_preview_level
from .preferences import get_prefs, is_macos_layout


class MAYA_UX_PT_channel_box(bpy.types.Panel):
    """Maya-style Channel Box in the 3D Viewport N-Panel."""

    bl_label = "Channel Box"
    bl_idname = "MAYA_UX_PT_channel_box"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        top_row = layout.row(align=True)
        hk_txt = "Hotkeys (?)" if is_macos_layout(context) else "Hotkeys (F1)"
        top_row.operator("maya_ux.cheatsheet", text=hk_txt, icon="HELP")
        top_row.operator("preferences.addon_show", text="Prefs", icon="PREFERENCES").module = __package__

        if obj is None:
            layout.label(text="No active object selected", icon="INFO")
            return

        layout.prop(obj, "name", text="")

        prefs = get_prefs(context)
        yup_mode = bool(getattr(prefs, "channel_box_yup", False))
        yup_proxy = getattr(context.window_manager, "maya_ux_yup", None)

        mode_row = layout.row(align=True)
        mode_row.operator(
            "maya_ux.toggle_channel_box_yup",
            text="Y-Up (Maya)" if yup_mode else "Z-Up (Blender)",
            icon="ORIENTATION_GLOBAL",
            depress=yup_mode,
        )

        box = layout.box()
        if yup_mode and yup_proxy is not None:
            for label, proxy_prop, lock_prop, reset_key in (
                ("Translate (Y-Up)", "translate", "lock_location", "LOC"),
                ("Rotate (Y-Up)", "rotate", "lock_rotation", "ROT"),
                ("Scale (Y-Up)", "scale", "lock_scale", "SCALE"),
            ):
                header = box.row(align=True)
                header.label(text=label)
                op = header.operator("maya_ux.reset_transforms", text="0", icon="LOOP_BACK")
                op.channel = reset_key

                # Maya (X, Y-Up, Z-Depth) maps to Blender indices (0, 2, 1)
                for p_idx, b_idx, axis in ((0, 0, "X"), (1, 2, "Y (Up)"), (2, 1, "Z")):
                    row = box.row(align=True)
                    row.prop(yup_proxy, proxy_prop, index=p_idx, text=axis)
                    locked = getattr(obj, lock_prop)[b_idx]
                    row.prop(
                        obj,
                        lock_prop,
                        index=b_idx,
                        text="",
                        icon="LOCKED" if locked else "UNLOCKED",
                        toggle=True,
                    )
        else:
            for label, prop_name, lock_prop, reset_key in (
                ("Translate", "location", "lock_location", "LOC"),
                ("Rotate", "rotation_euler", "lock_rotation", "ROT"),
                ("Scale", "scale", "lock_scale", "SCALE"),
            ):
                header = box.row(align=True)
                header.label(text=label)
                op = header.operator("maya_ux.reset_transforms", text="0", icon="LOOP_BACK")
                op.channel = reset_key

                for idx, axis in enumerate(("X", "Y", "Z")):
                    row = box.row(align=True)
                    row.prop(obj, prop_name, index=idx, text=axis)
                    locked = getattr(obj, lock_prop)[idx]
                    row.prop(
                        obj,
                        lock_prop,
                        index=idx,
                        text="",
                        icon="LOCKED" if locked else "UNLOCKED",
                        toggle=True,
                    )

        vis_row = layout.row(align=True)
        vis_row.prop(obj, "hide_viewport", text="Viewport", toggle=True)
        vis_row.prop(obj, "hide_render", text="Render", toggle=True)

        if obj.type == "MESH" and obj.data is not None:
            mesh = obj.data
            stat = layout.row(align=True)
            stat.label(text=f"V: {len(mesh.vertices)}  E: {len(mesh.edges)}  F: {len(mesh.polygons)}")


class MAYA_UX_PT_transform_pivot(bpy.types.Panel):
    """Maya Transform, Pivot, History, and Modeling actions."""

    bl_label = "Pivot & Modeling"
    bl_idname = "MAYA_UX_PT_transform_pivot"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"

    def draw(self, context):
        layout = self.layout
        ts = context.scene.tool_settings

        pivot_row = layout.row(align=True)
        pivot_row.alert = bool(ts.use_transform_data_origin)
        pivot_row.operator(
            "maya_ux.toggle_edit_pivot",
            text="Edit Pivot (D)" if not ts.use_transform_data_origin else "EXIT Edit Pivot (D)",
            icon="OBJECT_ORIGIN",
            depress=bool(ts.use_transform_data_origin),
        )

        grid = layout.grid_flow(columns=2, align=True)
        grid.operator("maya_ux.pivot_action", text="Center Pivot").action = "CENTER"
        grid.operator("maya_ux.pivot_action", text="World Origin").action = "WORLD_ORIGIN"
        grid.operator("maya_ux.pivot_action", text="Bottom Center").action = "BOTTOM_CENTER"
        grid.operator("maya_ux.pivot_action", text="Match Active").action = "TO_ACTIVE"

        mod_col = layout.column(align=True)
        row1 = mod_col.row(align=True)
        row1.operator("maya_ux.freeze_transforms", text="Freeze", icon="FREEZE")
        row1.operator("maya_ux.delete_history", text="History", icon="TRASH")

        row2 = mod_col.row(align=True)
        row2.operator("maya_ux.combine", text="Combine")
        row2.operator("maya_ux.separate", text="Separate")

        cmd_lbl = "⌘" if is_macos_layout(context) else "Ctrl+"
        sh_lbl = "⇧" if is_macos_layout(context) else "Shift+"

        row3 = mod_col.row(align=True)
        row3.operator("maya_ux.group_selected", text=f"Group ({cmd_lbl}G)", icon="OUTLINER_OB_EMPTY")
        row3.operator("maya_ux.unparent_keep_transform", text="Unparent")

        row4 = mod_col.row(align=True)
        row4.operator("maya_ux.duplicate_in_place", text=f"Dup ({cmd_lbl}D)")
        row4.operator("maya_ux.duplicate_with_transform", text=f"{sh_lbl}D")
        row4.operator("maya_ux.duplicate_special", text="Special")

        # MMB Virtual Drag Axis Lock
        yup_mode = bool(getattr(get_prefs(context), "channel_box_yup", False))
        cur_mmb = ops_viewport._MMB_LOCKED_AXIS
        mmb_row = layout.row(align=True)
        mmb_row.label(text="MMB:")
        mmb_row.operator("maya_ux.set_mmb_axis", text="Free", depress=(cur_mmb is None)).axis = "FREE"
        axis_specs = (("X", "X"), ("Y", "Z"), ("Z", "Y")) if yup_mode else (("X", "X"), ("Y", "Y"), ("Z", "Z"))
        for lbl, b_axis in axis_specs:
            b_idx = {"X": 0, "Y": 1, "Z": 2}[b_axis]
            is_dep = cur_mmb is not None and cur_mmb[b_idx]
            mmb_row.operator("maya_ux.set_mmb_axis", text=lbl, depress=is_dep).axis = b_axis


class MAYA_UX_PT_display_smooth(bpy.types.Panel):
    """Maya Smooth Preview (1/2/3), Shading (4/5/6/7), Snap (X/C/V), and Symmetry."""

    bl_label = "Display, Snap & Smooth"
    bl_idname = "MAYA_UX_PT_display_smooth"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"

    def draw(self, context):
        layout = self.layout
        ts = context.scene.tool_settings
        space = context.space_data

        # Smooth Preview 1 / 2 / 3
        cur_smooth = get_smooth_preview_level(context.active_object)
        layout.label(text="Smooth Mesh Preview:")
        s_row = layout.row(align=True)
        for lvl, lbl in ((1, "1 Rough"), (2, "2 Cage"), (3, "3 Smooth")):
            s_row.operator("maya_ux.smooth_preview", text=lbl, depress=(cur_smooth == lvl)).level = lvl

        # Shading 4 / 5 / 6 / 7
        if space and space.type == "VIEW_3D":
            layout.label(text="Shading:")
            sh_row = layout.row(align=True)
            cur_sh = space.shading.type
            for sh_type, lbl in (
                ("WIREFRAME", "4 Wire"),
                ("SOLID", "5 Solid"),
                ("MATERIAL", "6 Tex"),
                ("RENDERED", "7 Light"),
            ):
                sh_row.operator("maya_ux.set_shading", text=lbl, depress=(cur_sh == sh_type)).shading_type = sh_type

            ov_row = layout.row(align=True)
            ov_row.operator(
                "maya_ux.toggle_wireframe_on_shaded",
                text="Wire Shaded",
                depress=bool(space.overlay.show_wireframes),
            )
            ov_row.operator(
                "maya_ux.toggle_xray",
                text="X-Ray",
                depress=bool(space.shading.show_xray),
            )
            ov_row.operator(
                "maya_ux.isolate_select",
                text="Isolate",
                depress=(space.local_view is not None),
            )

        layout.operator(
            "maya_ux.toggle_poly_count_hud",
            text="Poly Count HUD",
            icon="LINENUMBERS_ON",
            depress=bool(getattr(get_prefs(context), "show_poly_count_hud", True)),
        )

        # Snap X / C / V + Discrete J
        layout.label(text="Snap (X / C / V / J):")
        snap_row = layout.row(align=True)
        active_snaps = set(ts.snap_elements) if ts.use_snap else set()
        for stype, lbl in (("GRID", "X Grid"), ("EDGE", "C Edge"), ("VERTEX", "V Vert")):
            snap_row.operator("maya_ux.maya_snap", text=lbl, depress=(stype in active_snaps)).snap_type = stype
        snap_row.operator("maya_ux.toggle_discrete_snap", text="J Step", depress=("INCREMENT" in active_snaps))

        # Soft Selection B & Auto-Key Alt+K
        soft_on = ts.use_proportional_edit if context.mode == "EDIT_MESH" else ts.use_proportional_edit_objects
        util_row = layout.row(align=True)
        util_row.operator("maya_ux.toggle_soft_select", text="Soft Select (B)", icon="PROP_ON", depress=bool(soft_on))
        util_row.operator(
            "maya_ux.toggle_autokey",
            text="AutoKey",
            icon="REC",
            depress=bool(ts.use_keyframe_insert_auto),
        )

        # Symmetry
        obj = context.active_object
        layout.label(text="Live Symmetry:")
        sym_row = layout.row(align=True)
        for axis in ("X", "Y", "Z"):
            is_on = bool(getattr(obj, f"use_mesh_mirror_{axis.lower()}", False)) if obj else False
            sym_row.operator("maya_ux.toggle_symmetry", text=axis, depress=is_on).axis = axis
        sym_row.operator("maya_ux.add_mirror_modifier", text="Mirror Mod", icon="MOD_MIRROR")


class MAYA_UX_PT_inputs_history(bpy.types.Panel):
    """Maya-style Inputs / Construction History stack (Modifiers)."""

    bl_label = "Inputs (History)"
    bl_idname = "MAYA_UX_PT_inputs_history"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or not obj.modifiers:
            layout.label(text="No construction history", icon="INFO")
            return

        for mod in obj.modifiers:
            box = layout.box()
            row = box.row(align=True)
            row.prop(mod, "name", text="")
            row.prop(mod, "show_viewport", text="", icon="RESTRICT_VIEW_OFF" if mod.show_viewport else "RESTRICT_VIEW_ON")
            row.prop(mod, "show_render", text="", icon="RESTRICT_RENDER_OFF" if mod.show_render else "RESTRICT_RENDER_ON")
            if mod.type == "SUBSURF":
                box.prop(mod, "levels", text="Subdivisions")

        layout.operator("maya_ux.delete_history", text="Collapse All History", icon="TRASH")


class MAYA_UX_PT_maya_io_axes(bpy.types.Panel):
    """Maya Y-Up Axis Conversion, Grid Theme, Units, and 1-Click FBX/OBJ/USD I/O."""

    bl_label = "Maya Y-Up I/O & Grid"
    bl_idname = "MAYA_UX_PT_maya_io_axes"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        layout.label(text="Convert Up-Axis (±90° X):")
        conv_row = layout.row(align=True)
        conv_row.operator("maya_ux.convert_up_axis", text="Y -> Z (+90°)").direction = "Y_TO_Z"
        conv_row.operator("maya_ux.convert_up_axis", text="Z -> Y (-90°)").direction = "Z_TO_Y"

        layout.label(text="Export Maya Y-Up:")
        exp_row = layout.row(align=True)
        exp_row.operator("maya_ux.export_maya_fbx", text="FBX")
        exp_row.operator("maya_ux.export_maya_obj", text="OBJ")
        exp_row.operator("maya_ux.export_maya_usd", text="USD")

        layout.label(text="Import Maya Y-Up:")
        imp_row = layout.row(align=True)
        imp_row.operator("maya_ux.import_maya_fbx", text="FBX")
        imp_row.operator("maya_ux.import_maya_obj", text="OBJ")
        imp_row.operator("maya_ux.import_maya_usd", text="USD")

        layout.label(text="Maya Scene & Grid:")
        env_row = layout.row(align=True)
        env_row.operator("maya_ux.apply_maya_grid_theme", text="Grid & Green-Up", icon="GRID")
        cur_unit = context.scene.unit_settings.length_unit
        env_row.operator(
            "maya_ux.set_maya_cm_units",
            text="Units: cm" if cur_unit == "CENTIMETERS" else "Units: m -> cm",
        )


class MAYA_UX_PT_retopo(bpy.types.Panel):
    """Maya Make Live, Quad Draw Retopology, Relax, and Target Weld."""

    bl_label = "Retopo & Quad Draw"
    bl_idname = "MAYA_UX_PT_retopo"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        live_name = getattr(scene, "maya_ux_live_surface", "")

        live_row = layout.row(align=True)
        live_row.operator(
            "maya_ux.make_live",
            text=f"LIVE: {live_name}" if live_name else "Make Live Surface",
            icon="SNAP_ON" if live_name else "SNAP_FACE",
            depress=bool(live_name),
        )
        if live_name:
            live_row.operator("maya_ux.clear_live", text="", icon="X")

        layout.prop(scene, "maya_ux_retopo_mirror")

        q_row = layout.row(align=True)
        q_row.scale_y = 1.2
        q_row.operator("maya_ux.start_quad_draw", text="Quad Draw", icon="MOD_BUILD")
        q_row.operator("maya_ux.retopo_relax", text="Relax", icon="MOD_SMOOTH")

        b_row = layout.row(align=True)
        b_row.operator("maya_ux.target_weld", text="Target Weld", icon="AUTOMERGE_ON")
        b_row.operator("maya_ux.finish_quad_draw", text="Finish / Bake", icon="CHECKMARK")


class MAYA_UX_PT_camtools(bpy.types.Panel):
    """Maya CamTools Pro: Camera from View, Lock, Clip, Lens, DOF, Guides & Bookmarks."""

    bl_label = "CamTools Pro"
    bl_idname = "MAYA_UX_PT_camtools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        space = context.space_data
        cam = scene.camera

        top = layout.row(align=True)
        top.operator("maya_ux.cam_from_view", text="Cam from View", icon="CAMERA_DATA")
        if space and space.type == "VIEW_3D":
            top.operator("maya_ux.toggle_lock_camera", text="Lock", icon="LOCKED", depress=bool(space.lock_camera))
        top.operator("maya_ux.fix_cam_clip", text="Clip", icon="DRIVER_DISTANCE")

        lens_row = layout.row(align=True)
        for mm in (24.0, 35.0, 50.0, 85.0):
            lens_row.operator("maya_ux.set_cam_lens", text=f"{int(mm)}").lens = mm

        if cam is not None and cam.type == "CAMERA":
            cdata = cam.data
            box = layout.box()
            box.prop(cam, "name", text="Active")
            box.prop(cdata, "lens", text="Focal (mm)")
            clip_row = box.row(align=True)
            clip_row.prop(cdata, "clip_start", text="Near")
            clip_row.prop(cdata, "clip_end", text="Far")
            box.prop(cdata, "passepartout_alpha", text="Passepartout")

            g_row = box.row(align=True)
            g_row.prop(cdata, "show_composition_thirds", text="Thirds", toggle=True)
            g_row.prop(cdata, "show_composition_center", text="Center", toggle=True)
            g_row.prop(cdata, "show_safe_areas", text="Safe", toggle=True)

            box.prop(cdata.dof, "use_dof", text="Depth of Field")
            if cdata.dof.use_dof:
                box.prop(cdata.dof, "focus_object", text="Focus")

        layout.label(text="Camera Bookmarks:")
        for slot in (1, 2, 3, 4):
            b_row = layout.row(align=True)
            is_set = ops_camtools.has_bookmark(scene, slot)
            op_load = b_row.operator(
                "maya_ux.cam_bookmark",
                text=f"Cam {slot}" if is_set else f"Slot {slot} (Empty)",
                icon="BOOKMARKS" if is_set else "DOT",
                depress=is_set,
            )
            op_load.slot = slot
            op_load.action = "LOAD"

            op_save = b_row.operator("maya_ux.cam_bookmark", text="", icon="ADD")
            op_save.slot = slot
            op_save.action = "SAVE"

            if is_set:
                op_clr = b_row.operator("maya_ux.cam_bookmark", text="", icon="X")
                op_clr.slot = slot
                op_clr.action = "CLEAR"


class MAYA_UX_PT_materials_lookdev(bpy.types.Panel):
    """Maya Starter Materials, 3-Point Studio Lights, Theme & Workspace."""

    bl_label = "Materials, Theme & Workspace"
    bl_idname = "MAYA_UX_PT_materials_lookdev"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Maya"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Maya Quick Materials:")
        grid = layout.grid_flow(columns=2, align=True)
        for preset, lbl in (
            ("LAMBERT1", "Lambert1"),
            ("BLINN1", "Blinn1"),
            ("CLAY_SCULPT", "Clay Sculpt"),
            ("CHROME_CHECK", "Chrome"),
            ("UV_CHECKER", "UV Checker"),
            ("GLASS_BASIC", "Glass"),
        ):
            grid.operator("maya_ux.assign_maya_material", text=lbl).preset = preset

        has_lights = "MayaStudioLights" in bpy.data.collections
        layout.operator(
            "maya_ux.setup_studio_lighting",
            text="Remove Studio Lights" if has_lights else "Add 3-Point Studio Lights",
            icon="LIGHT_AREA",
            depress=has_lights,
        )

        layout.separator()
        row = layout.row(align=True)
        row.operator("maya_ux.apply_maya_theme", text="Maya Dark Theme", icon="COLOR")
        row.operator("maya_ux.create_maya_workspace", text="'Maya Pro' WS", icon="WORKSPACE")


CLASSES = (
    MAYA_UX_PT_channel_box,
    MAYA_UX_PT_transform_pivot,
    MAYA_UX_PT_display_smooth,
    MAYA_UX_PT_inputs_history,
    MAYA_UX_PT_maya_io_axes,
    MAYA_UX_PT_retopo,
    MAYA_UX_PT_camtools,
    MAYA_UX_PT_materials_lookdev,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
