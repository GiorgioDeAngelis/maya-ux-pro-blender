from __future__ import annotations

import bpy

from .preferences import get_prefs, is_macos_layout

addon_keymaps: list[tuple[bpy.types.KeyMap, bpy.types.KeyMapItem]] = []
_disabled_builtin_kmis: list[bpy.types.KeyMapItem] = []
_transform_modal_swapped: bool = False


def _sync_transform_modal_yz(enable: bool) -> bool:
    """Swap Y and Z keys in Transform Modal Map so pressing Y constrains to vertical Up (Blender Z)."""
    global _transform_modal_swapped
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return False
    user_kc = getattr(wm.keyconfigs, "user", None)
    if user_kc is None:
        return False
    km = user_kc.keymaps.get("Transform Modal Map")
    if km is None:
        return False

    for kmi in km.keymap_items:
        pv = getattr(kmi, "propvalue", "")
        if enable:
            if pv in {"AXIS_Y", "PLANE_Y"} and kmi.type == "Y":
                kmi.type = "Z"
            elif pv in {"AXIS_Z", "PLANE_Z"} and kmi.type == "Z":
                kmi.type = "Y"
        else:
            if pv in {"AXIS_Y", "PLANE_Y"} and kmi.type == "Z":
                kmi.type = "Y"
            elif pv in {"AXIS_Z", "PLANE_Z"} and kmi.type == "Y":
                kmi.type = "Z"

    _transform_modal_swapped = bool(enable)
    return True


def _disable_builtin_spacebar_play() -> bool:
    """Disable built-in bare-Spacebar timeline playback so Maya Spacebar takes priority."""
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return False

    found_user_frames = False
    seen_kms: set[int] = set()
    user_kc = getattr(wm.keyconfigs, "user", None)
    active_kc = getattr(wm.keyconfigs, "active", None)

    for kc in (user_kc, active_kc):
        if kc is None:
            continue
        km = kc.keymaps.get("Frames")
        if km is None:
            continue
        if kc is user_kc:
            found_user_frames = True
        km_ptr = km.as_pointer()
        if km_ptr in seen_kms:
            continue
        seen_kms.add(km_ptr)

        for kmi in km.keymap_items:
            if (
                kmi.active
                and kmi.idname == "screen.animation_play"
                and kmi.type == "SPACE"
                and not kmi.ctrl
                and not kmi.shift
                and not kmi.alt
                and not kmi.oskey
            ):
                kmi.active = False
                if kmi not in _disabled_builtin_kmis:
                    _disabled_builtin_kmis.append(kmi)

    return found_user_frames


def _restore_builtin_spacebar_play():
    """Restore any built-in Spacebar bindings disabled by the addon."""
    for kmi in _disabled_builtin_kmis:
        try:
            kmi.active = True
        except Exception:
            pass
    _disabled_builtin_kmis.clear()


def _deferred_spacebar_sync():
    """One-shot startup retry in case user keymaps loaded after addon register."""
    prefs = get_prefs()
    if getattr(prefs, "enable_marking_menus", True) and getattr(prefs, "spacebar_mode", "HYBRID") != "DISABLED":
        _disable_builtin_spacebar_play()
    if getattr(prefs, "swap_axis_colors_yup", False):
        _sync_transform_modal_yz(True)
    return None


def _add_kmi(
    km: bpy.types.KeyMap,
    idname: str,
    key_type: str,
    value: str = "PRESS",
    *,
    ctrl: bool = False,
    shift: bool = False,
    alt: bool = False,
    oskey: bool = False,
    repeat: bool = True,
    props: dict | None = None,
) -> bpy.types.KeyMapItem:
    """Register a keymap item with explicit modifier flags (oskey=False protects macOS Cmd)."""
    kmi = km.keymap_items.new(
        idname,
        type=key_type,
        value=value,
        ctrl=ctrl,
        shift=shift,
        alt=alt,
        oskey=oskey,
        repeat=repeat,
    )
    if props:
        for attr, val in props.items():
            setattr(kmi.properties, attr, val)
    addon_keymaps.append((km, kmi))
    return kmi


def _add_primary_kmi(
    km: bpy.types.KeyMap,
    idname: str,
    key_type: str,
    value: str = "PRESS",
    *,
    is_mac: bool,
    shift: bool = False,
    alt: bool = False,
    allow_cmd: bool = True,
    props: dict | None = None,
):
    """Bind Ctrl+<key>, plus Cmd+<key> on macOS when safe (never hijacking OS shortcuts)."""
    _add_kmi(km, idname, key_type, value, ctrl=True, shift=shift, alt=alt, oskey=False, props=props)
    if is_mac and allow_cmd:
        _add_kmi(km, idname, key_type, value, ctrl=False, shift=shift, alt=alt, oskey=True, props=props)


def register_keymaps():
    wm = bpy.context.window_manager
    if wm is None:
        return
    kc = wm.keyconfigs.addon
    if kc is None:
        return

    prefs = get_prefs()
    is_mac = is_macos_layout()

    km_window = kc.keymaps.new(name="Window", space_type="EMPTY")
    km_screen = kc.keymaps.new(name="Screen", space_type="EMPTY")
    km_view3d = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
    km_view2d = kc.keymaps.new(name="View2D", space_type="EMPTY")
    km_object = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
    km_mesh = kc.keymaps.new(name="Mesh", space_type="EMPTY")
    km_outliner = kc.keymaps.new(name="Outliner", space_type="OUTLINER")
    km_pose = kc.keymaps.new(name="Pose", space_type="EMPTY")
    km_curve = kc.keymaps.new(name="Curve", space_type="EMPTY")
    km_frames = kc.keymaps.new(name="Frames", space_type="EMPTY")
    km_graph = kc.keymaps.new(name="Graph Editor", space_type="GRAPH_EDITOR")
    km_dope = kc.keymaps.new(name="Dopesheet", space_type="DOPESHEET_EDITOR")
    km_uv = kc.keymaps.new(name="UV Editor", space_type="EMPTY")

    # 1. Core UX & Viewport
    if prefs.enable_viewport_keys:
        if is_mac and getattr(prefs, "enable_mac_trackpad_nav", True):
            # Explicit MacBook Pro Trackpad & No-MMB Maya navigation (⌥ Option = alt)
            _add_kmi(km_view3d, "view3d.rotate", "LEFTMOUSE", alt=True)
            _add_kmi(km_view3d, "view3d.move", "MIDDLEMOUSE", alt=True)
            _add_kmi(km_view3d, "view3d.move", "LEFTMOUSE", alt=True, shift=True)
            _add_kmi(km_view3d, "view3d.zoom", "RIGHTMOUSE", alt=True)
            _add_kmi(km_view3d, "view3d.zoom", "LEFTMOUSE", alt=True, ctrl=True)
            _add_kmi(km_view3d, "view3d.rotate", "TRACKPADPAN", value="ANY")
            _add_kmi(km_view3d, "view3d.move", "TRACKPADPAN", value="ANY", shift=True)
            _add_kmi(km_view3d, "view3d.zoom", "TRACKPADZOOM", value="ANY")

            _add_kmi(km_view2d, "view2d.pan", "LEFTMOUSE", alt=True)
            _add_kmi(km_view2d, "view2d.pan", "MIDDLEMOUSE", alt=True)
            _add_kmi(km_view2d, "view2d.pan", "LEFTMOUSE", alt=True, shift=True)
            _add_kmi(km_view2d, "view2d.zoom", "RIGHTMOUSE", alt=True)
            _add_kmi(km_view2d, "view2d.zoom", "LEFTMOUSE", alt=True, ctrl=True)

        if getattr(prefs, "enable_maya_mmb_drag", True):
            # Ensure Option+MMB always pans, and bare MMB does Maya Smart Pan / Virtual Transform
            _add_kmi(km_view3d, "view3d.move", "MIDDLEMOUSE", alt=True)
            _add_kmi(km_view3d, "maya_ux.mmb_smart_drag", "MIDDLEMOUSE")
            for km in (km_object, km_mesh, km_pose, km_curve):
                _add_kmi(km, "maya_ux.mmb_smart_drag", "MIDDLEMOUSE")
            for tool_km_name in (
                "3D View Tool: Move",
                "3D View Tool: Rotate",
                "3D View Tool: Scale",
                "3D View Tool: Transform",
                "3D View Tool: Select Box",
                "3D View Tool: Tweak",
                "3D View Tool: Select Circle",
                "3D View Tool: Select Lasso",
            ):
                km_tool = kc.keymaps.new(name=tool_km_name, space_type="VIEW_3D", region_type="WINDOW")
                _add_kmi(km_tool, "maya_ux.mmb_smart_drag", "MIDDLEMOUSE")

        for km in (km_object, km_mesh):
            for key, tool_id in (
                ("Q", "builtin.select_box"),
                ("W", "builtin.move"),
                ("E", "builtin.rotate"),
                ("R", "builtin.scale"),
                ("T", "builtin.transform"),
            ):
                _add_kmi(km, "maya_ux.set_tool", key, props={"tool_id": tool_id})

            _add_kmi(km, "maya_ux.smart_hide", "H", props={"action": "TOGGLE"})
            # Ctrl+H (never Cmd+H on macOS)
            _add_kmi(km, "maya_ux.smart_hide", "H", ctrl=True, props={"action": "HIDE"})
            _add_kmi(km, "maya_ux.smart_hide", "H", shift=True, props={"action": "UNHIDE"})
            _add_kmi(km, "maya_ux.smart_hide", "H", alt=True, props={"action": "HIDE_UNSELECTED"})
            _add_kmi(km, "maya_ux.smart_hide", "H", ctrl=True, shift=True, props={"action": "UNHIDE_LAST"})
            _add_kmi(km, "screen.repeat_last", "Y")
            _add_primary_kmi(km, "ed.redo", "Y", is_mac=is_mac, allow_cmd=True)

            if prefs.enable_maya_z_undo:
                _add_kmi(km, "ed.undo", "Z")
                _add_kmi(km, "ed.redo", "Z", shift=True)

            _add_kmi(km, "maya_ux.component_mode", "F8", props={"mode": "TOGGLE"})
            _add_kmi(km, "maya_ux.component_mode", "ONE", alt=True, props={"mode": "OBJECT"})
            for fkey, opt_key, comp_mode in (
                ("F9", "TWO", "VERT"),
                ("F10", "THREE", "EDGE"),
                ("F11", "FOUR", "FACE"),
            ):
                _add_kmi(km, "maya_ux.component_mode", fkey, props={"mode": comp_mode})
                # MacBook Pro Fn-free ergonomic aliases: ⌥+1/2/3/4
                _add_kmi(km, "maya_ux.component_mode", opt_key, alt=True, props={"mode": comp_mode})

            for key, direction in (
                ("UP_ARROW", "UP"),
                ("DOWN_ARROW", "DOWN"),
                ("LEFT_ARROW", "LEFT"),
                ("RIGHT_ARROW", "RIGHT"),
            ):
                _add_kmi(km, "maya_ux.screen_nudge", key, alt=True, props={"direction": direction})

        _add_kmi(km_outliner, "maya_ux.smart_hide", "H", props={"action": "TOGGLE"})
        _add_kmi(km_outliner, "maya_ux.smart_hide", "H", ctrl=True, props={"action": "HIDE"})
        _add_kmi(km_outliner, "maya_ux.smart_hide", "H", shift=True, props={"action": "UNHIDE"})
        _add_kmi(km_outliner, "maya_ux.smart_hide", "H", ctrl=True, shift=True, props={"action": "UNHIDE_LAST"})

        _add_kmi(km_view3d, "maya_ux.gizmo_size", "EQUAL", props={"delta": 10})
        _add_kmi(km_view3d, "maya_ux.gizmo_size", "NUMPAD_PLUS", props={"delta": 10})
        _add_kmi(km_view3d, "maya_ux.gizmo_size", "MINUS", props={"delta": -10})
        _add_kmi(km_view3d, "maya_ux.gizmo_size", "NUMPAD_MINUS", props={"delta": -10})

        for key, sh_type in (
            ("FOUR", "WIREFRAME"),
            ("FIVE", "SOLID"),
            ("SIX", "MATERIAL"),
            ("SEVEN", "RENDERED"),
        ):
            _add_kmi(km_view3d, "maya_ux.set_shading", key, props={"shading_type": sh_type})

        _add_kmi(km_view3d, "maya_ux.toggle_wireframe_on_shaded", "FIVE", alt=True)
        _add_kmi(km_view3d, "maya_ux.toggle_xray", "X", alt=True)
        _add_kmi(km_view3d, "maya_ux.default_display", "ZERO")
        _add_primary_kmi(km_view3d, "maya_ux.isolate_select", "ONE", is_mac=is_mac, allow_cmd=True)
        _add_kmi(km_view3d, "maya_ux.isolate_select", "I", shift=True)
        for km in (km_view3d, km_object, km_mesh, km_pose, km_curve):
            _add_kmi(km, "view3d.view_selected", "F")
        _add_kmi(km_view3d, "maya_ux.frame_all_views", "A", shift=True, props={"selected_only": False})
        _add_kmi(km_view3d, "maya_ux.frame_all_views", "F", shift=True, props={"selected_only": True})
        # Ctrl+Space (never Cmd+Space Spotlight) & Ctrl+A (never Cmd+A Select All)
        _add_kmi(km_view3d, "maya_ux.expert_mode", "SPACE", ctrl=True)
        _add_kmi(km_screen, "maya_ux.expert_mode", "SPACE", ctrl=True)
        _add_kmi(km_view3d, "maya_ux.toggle_channel_box", "A", ctrl=True)
        _add_kmi(km_view3d, "maya_ux.cycle_viewport_bg", "B", alt=True)
        _add_kmi(km_view3d, "maya_ux.camera_view_undo", "LEFT_BRACKET")
        _add_kmi(km_view3d, "maya_ux.camera_view_redo", "RIGHT_BRACKET")
        _add_kmi(km_view3d, "maya_ux.cheatsheet", "F1")
        _add_kmi(km_view3d, "maya_ux.cheatsheet", "SLASH", shift=True)
        _add_primary_kmi(km_window, "maya_ux.increment_save", "S", is_mac=is_mac, alt=True, allow_cmd=True)

    # 2. Marking Menus
    if prefs.enable_marking_menus:
        rmb_val = prefs.rmb_trigger
        for km in (km_object, km_mesh):
            _add_kmi(
                km,
                "wm.call_menu_pie",
                "RIGHTMOUSE",
                value=rmb_val,
                props={"name": "VIEW3D_MT_maya_component_pie"},
            )
            _add_kmi(
                km,
                "wm.call_menu_pie",
                "RIGHTMOUSE",
                value="PRESS",
                shift=True,
                props={"name": "VIEW3D_MT_maya_modeling_pie"},
            )

        sp_mode = prefs.spacebar_mode
        if sp_mode == "HYBRID":
            _add_kmi(km_view3d, "maya_ux.spacebar_maya", "SPACE", value="PRESS", repeat=False)
            _add_kmi(km_frames, "maya_ux.spacebar_maya", "SPACE", value="PRESS", repeat=False)
            _add_kmi(km_screen, "maya_ux.spacebar_maya", "SPACE", value="PRESS", repeat=False)
            _add_kmi(
                km_view3d,
                "wm.call_menu_pie",
                "SPACE",
                value="PRESS",
                shift=True,
                props={"name": "VIEW3D_MT_maya_view_pie"},
            )
        elif sp_mode == "QUAD_ONLY":
            _add_kmi(km_view3d, "maya_ux.spacebar_maya", "SPACE", value="PRESS", repeat=False)
            _add_kmi(km_frames, "maya_ux.spacebar_maya", "SPACE", value="PRESS", repeat=False)
            _add_kmi(km_screen, "maya_ux.spacebar_maya", "SPACE", value="PRESS", repeat=False)
        elif sp_mode == "VIEW_PIE_ONLY":
            _add_kmi(
                km_view3d,
                "wm.call_menu_pie",
                "SPACE",
                value="PRESS",
                props={"name": "VIEW3D_MT_maya_view_pie"},
            )

        if sp_mode != "DISABLED":
            found_frames = _disable_builtin_spacebar_play()
            if not found_frames and not bpy.app.timers.is_registered(_deferred_spacebar_sync):
                bpy.app.timers.register(_deferred_spacebar_sync, first_interval=0.5)

    # 3. Pivot & Snapping
    if prefs.enable_pivot_snap:
        if getattr(prefs, "pivot_hold_mode", "HOLD") == "HOLD":
            for km in (km_object, km_view3d):
                _add_kmi(
                    km,
                    "maya_ux.maya_pivot_hold",
                    "D",
                    value="PRESS",
                    repeat=False,
                    props={"active": True},
                )
                _add_kmi(
                    km,
                    "maya_ux.maya_pivot_hold",
                    "D",
                    value="RELEASE",
                    props={"active": False},
                )
        else:
            _add_kmi(km_object, "maya_ux.toggle_edit_pivot", "D", repeat=False)
        if not is_mac:
            _add_kmi(km_object, "maya_ux.toggle_edit_pivot", "INSERT")
        _add_kmi(
            km_object,
            "wm.call_menu_pie",
            "D",
            alt=True,
            props={"name": "VIEW3D_MT_maya_pivot_pie"},
        )
        snap_hold = getattr(prefs, "snap_hold_mode", "HOLD") == "HOLD"
        for km in (km_view3d, km_object, km_mesh):
            for key, stype in (("X", "GRID"), ("C", "EDGE"), ("V", "VERTEX")):
                if snap_hold:
                    _add_kmi(
                        km,
                        "maya_ux.maya_snap_hold",
                        key,
                        value="PRESS",
                        repeat=False,
                        props={"snap_type": stype, "active": True},
                    )
                    _add_kmi(
                        km,
                        "maya_ux.maya_snap_hold",
                        key,
                        value="RELEASE",
                        props={"snap_type": stype, "active": False},
                    )
                else:
                    _add_kmi(km, "maya_ux.maya_snap", key, repeat=False, props={"snap_type": stype})

    # 4. Smooth Preview (1 / 2 / 3 & Page Up / Page Down)
    if prefs.enable_smooth_preview:
        for km in (km_object, km_mesh):
            for key, lvl in (("ONE", 1), ("TWO", 2), ("THREE", 3)):
                _add_kmi(km, "maya_ux.smooth_preview", key, props={"level": lvl})
            _add_kmi(km, "maya_ux.smooth_preview_step", "PAGE_UP", props={"delta": 1})
            _add_kmi(km, "maya_ux.smooth_preview_step", "PAGE_DOWN", props={"delta": -1})

    # 5. Modeling & Outliner
    if prefs.enable_outliner_ops:
        _add_primary_kmi(km_object, "maya_ux.group_selected", "G", is_mac=is_mac, allow_cmd=True)
        _add_primary_kmi(km_outliner, "maya_ux.group_selected", "G", is_mac=is_mac, allow_cmd=True)
        _add_kmi(km_object, "maya_ux.parent_to_active", "P")
        _add_kmi(km_object, "maya_ux.unparent_keep_transform", "P", shift=True)
        _add_kmi(km_object, "screen.repeat_last", "G")
        _add_kmi(km_mesh, "screen.repeat_last", "G")

    # 6. Selection, Pick Walk & Soft Select
    if prefs.enable_selection_keys:
        if getattr(prefs, "maya_face_center_select", True):
            _add_kmi(
                km_mesh,
                "maya_ux.select_face_center",
                "LEFTMOUSE",
                value="CLICK",
                props={"toggle": False, "deselect": False},
            )
            _add_kmi(
                km_mesh,
                "maya_ux.select_face_center",
                "LEFTMOUSE",
                value="CLICK",
                shift=True,
                props={"toggle": True, "deselect": False},
            )
            _add_kmi(
                km_mesh,
                "maya_ux.select_face_center",
                "LEFTMOUSE",
                value="CLICK",
                ctrl=True,
                props={"toggle": False, "deselect": True},
            )

        # Maya Grow (>) / Shrink (<) Selection across US ANSI (Shift+. / Shift+,),
        # ISO European/PC (GRLESS / Shift+GRLESS), and Italian/EU Mac ISO (ACCENT_GRAVE '<' / '>').
        for km in (km_mesh, km_curve):
            _add_kmi(km, "maya_ux.grow_shrink_selection", "PERIOD", shift=True, props={"action": "GROW"})
            _add_kmi(km, "maya_ux.grow_shrink_selection", "COMMA", shift=True, props={"action": "SHRINK"})
            _add_kmi(km, "maya_ux.grow_shrink_selection", "GRLESS", shift=True, props={"action": "GROW"})
            _add_kmi(km, "maya_ux.grow_shrink_selection", "GRLESS", shift=False, props={"action": "SHRINK"})
            _add_kmi(km, "maya_ux.grow_shrink_selection", "ACCENT_GRAVE", shift=True, props={"action": "AUTO"})
            _add_kmi(km, "maya_ux.grow_shrink_selection", "ACCENT_GRAVE", shift=False, props={"action": "AUTO"})

        _add_primary_kmi(km_object, "object.select_all", "I", is_mac=is_mac, shift=True, allow_cmd=True, props={"action": "INVERT"})
        _add_primary_kmi(km_mesh, "mesh.select_all", "I", is_mac=is_mac, shift=True, allow_cmd=True, props={"action": "INVERT"})
        _add_primary_kmi(km_pose, "pose.select_all", "I", is_mac=is_mac, shift=True, allow_cmd=True, props={"action": "INVERT"})

        _add_kmi(km_mesh, "maya_ux.convert_selection", "F9", ctrl=True, props={"target": "VERT"})
        _add_kmi(km_mesh, "maya_ux.convert_selection", "F10", ctrl=True, props={"target": "EDGE"})
        _add_kmi(km_mesh, "maya_ux.convert_selection", "F11", ctrl=True, props={"target": "FACE"})

        for km in (km_object, km_mesh):
            _add_kmi(km, "maya_ux.toggle_soft_select", "B")
            _add_kmi(km, "maya_ux.smart_delete", "BACK_SPACE", props={"delete_verts": False})
            _add_kmi(km, "maya_ux.smart_delete", "DEL", props={"delete_verts": False})
        _add_primary_kmi(km_mesh, "maya_ux.smart_delete", "BACK_SPACE", is_mac=is_mac, allow_cmd=True, props={"delete_verts": True})
        _add_primary_kmi(km_mesh, "maya_ux.smart_delete", "DEL", is_mac=is_mac, allow_cmd=True, props={"delete_verts": True})

        _add_kmi(km_view3d, "maya_ux.soft_select_radius", "LEFT_BRACKET", shift=True, props={"factor": 0.8})
        _add_kmi(km_view3d, "maya_ux.soft_select_radius", "RIGHT_BRACKET", shift=True, props={"factor": 1.25})

        if prefs.enable_pick_walk_arrows:
            for km in (km_object, km_outliner):
                for key, direction in (
                    ("UP_ARROW", "UP"),
                    ("DOWN_ARROW", "DOWN"),
                    ("LEFT_ARROW", "LEFT"),
                    ("RIGHT_ARROW", "RIGHT"),
                ):
                    _add_kmi(km, "maya_ux.pick_walk", key, props={"direction": direction})

    # 7. Maya Modeling & Duplication
    if prefs.enable_modeling_keys:
        _add_primary_kmi(km_object, "maya_ux.duplicate_in_place", "D", is_mac=is_mac, allow_cmd=True)
        _add_kmi(km_object, "maya_ux.duplicate_with_transform", "D", shift=True)
        _add_primary_kmi(km_object, "maya_ux.duplicate_special", "D", is_mac=is_mac, shift=True, allow_cmd=True)
        _add_kmi(km_object, "maya_ux.delete_history", "D", alt=True, shift=True)
        if getattr(prefs, "snap_hold_mode", "HOLD") == "HOLD":
            for km in (km_view3d, km_object, km_mesh):
                _add_kmi(
                    km,
                    "maya_ux.maya_snap_hold",
                    "J",
                    value="PRESS",
                    repeat=False,
                    props={"snap_type": "INCREMENT", "active": True},
                )
                _add_kmi(
                    km,
                    "maya_ux.maya_snap_hold",
                    "J",
                    value="RELEASE",
                    props={"snap_type": "INCREMENT", "active": False},
                )
        else:
            _add_kmi(km_view3d, "maya_ux.toggle_discrete_snap", "J")
        _add_kmi(km_view3d, "maya_ux.toggle_relative_snap", "J", shift=True)

        _add_primary_kmi(km_mesh, "view3d.edit_mesh_extrude_move_normal", "E", is_mac=is_mac, allow_cmd=True)
        _add_primary_kmi(km_mesh, "mesh.bevel", "B", is_mac=is_mac, allow_cmd=True)
        _add_primary_kmi(km_mesh, "mesh.knife_tool", "X", is_mac=is_mac, shift=True, allow_cmd=True)
        _add_primary_kmi(km_mesh, "mesh.bridge_edge_loops", "B", is_mac=is_mac, shift=True, allow_cmd=True)
        _add_kmi(km_mesh, "wm.call_menu", "M", props={"name": "VIEW3D_MT_edit_mesh_merge"})
        _add_primary_kmi(
            km_mesh,
            "wm.call_menu",
            "M",
            is_mac=is_mac,
            alt=True,
            allow_cmd=True,
            props={"name": "VIEW3D_MT_edit_mesh_merge"},
        )
        _add_kmi(km_mesh, "mesh.flip_normals", "N", alt=True)

    # 8. Animation, Timeline & Graph Editor
    if prefs.enable_animation_keys:
        for km in (km_object, km_pose):
            _add_kmi(km, "maya_ux.set_keyframe", "S", props={"channels": "ALL"})
            _add_kmi(km, "maya_ux.set_keyframe", "W", shift=True, props={"channels": "LOC"})
            _add_kmi(km, "maya_ux.set_keyframe", "E", shift=True, props={"channels": "ROT"})
            _add_kmi(km, "maya_ux.set_keyframe", "R", shift=True, props={"channels": "SCALE"})

        for km in (km_frames, km_view3d):
            _add_kmi(km, "screen.animation_play", "V", alt=True)
            _add_kmi(km, "maya_ux.goto_min_frame", "V", alt=True, shift=True)
            _add_kmi(km, "screen.frame_offset", "COMMA", alt=True, props={"delta": -1})
            _add_kmi(km, "screen.frame_offset", "PERIOD", alt=True, props={"delta": 1})
            _add_kmi(km, "screen.keyframe_jump", "COMMA", props={"next": False})
            _add_kmi(km, "screen.keyframe_jump", "PERIOD", props={"next": True})
            _add_kmi(km, "maya_ux.toggle_autokey", "K", alt=True)

        _add_kmi(km_graph, "graph.view_selected", "F")
        _add_kmi(km_graph, "graph.view_all", "A")
        _add_kmi(km_graph, "graph.keyframe_insert", "I", alt=True, props={"type": "ALL"})
        _add_kmi(km_graph, "maya_ux.graph_tangent", "ONE", props={"preset": "LINEAR"})
        _add_kmi(km_graph, "maya_ux.graph_tangent", "TWO", props={"preset": "AUTO_FLAT"})
        _add_kmi(km_graph, "maya_ux.graph_tangent", "THREE", props={"preset": "STEPPED"})
        _add_kmi(km_graph, "maya_ux.graph_tangent", "FOUR", props={"preset": "SPLINE"})
        _add_kmi(
            km_graph,
            "wm.call_menu_pie",
            "T",
            props={"name": "GRAPH_MT_maya_tangents_pie"},
        )

        _add_kmi(km_dope, "action.view_selected", "F")
        _add_kmi(km_dope, "action.view_all", "A")

    # 9. UV Editor (Maya Style)
    if prefs.enable_uv_keys:
        _add_kmi(
            km_uv,
            "wm.call_menu_pie",
            "RIGHTMOUSE",
            value=prefs.rmb_trigger,
            props={"name": "IMAGE_MT_maya_uv_pie"},
        )
        for key, tool_id in (
            ("Q", "builtin.select_box"),
            ("W", "builtin.move"),
            ("E", "builtin.rotate"),
            ("R", "builtin.scale"),
        ):
            _add_kmi(km_uv, "maya_ux.uv_tool", key, props={"tool_id": tool_id})

        _add_kmi(km_uv, "image.view_selected", "F")
        _add_kmi(km_uv, "image.view_all", "A")
        _add_kmi(km_uv, "maya_ux.grow_shrink_selection", "PERIOD", shift=True, props={"action": "GROW"})
        _add_kmi(km_uv, "maya_ux.grow_shrink_selection", "COMMA", shift=True, props={"action": "SHRINK"})
        _add_kmi(km_uv, "maya_ux.grow_shrink_selection", "GRLESS", shift=True, props={"action": "GROW"})
        _add_kmi(km_uv, "maya_ux.grow_shrink_selection", "GRLESS", shift=False, props={"action": "SHRINK"})
        _add_kmi(km_uv, "maya_ux.grow_shrink_selection", "ACCENT_GRAVE", shift=True, props={"action": "AUTO"})
        _add_kmi(km_uv, "maya_ux.grow_shrink_selection", "ACCENT_GRAVE", shift=False, props={"action": "AUTO"})
        _add_primary_kmi(km_uv, "uv.select_linked", "F12", is_mac=is_mac, allow_cmd=True)
        _add_kmi(km_uv, "uv.mark_seam", "X", shift=True, props={"clear": False})
        _add_kmi(km_uv, "uv.stitch", "S", shift=True)
        _add_primary_kmi(km_uv, "uv.unwrap", "U", is_mac=is_mac, allow_cmd=True)
        _add_primary_kmi(km_uv, "uv.pack_islands", "L", is_mac=is_mac, allow_cmd=True)

    yup_modal = bool(getattr(prefs, "swap_axis_colors_yup", False))
    found_modal = _sync_transform_modal_yz(yup_modal)
    if yup_modal and not found_modal and not bpy.app.timers.is_registered(_deferred_spacebar_sync):
        bpy.app.timers.register(_deferred_spacebar_sync, first_interval=0.5)


def unregister_keymaps():
    if bpy.app.timers.is_registered(_deferred_spacebar_sync):
        bpy.app.timers.unregister(_deferred_spacebar_sync)
    _restore_builtin_spacebar_play()
    _sync_transform_modal_yz(False)
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()


def rebuild_keymaps():
    unregister_keymaps()
    register_keymaps()


def register():
    register_keymaps()


def unregister():
    unregister_keymaps()
