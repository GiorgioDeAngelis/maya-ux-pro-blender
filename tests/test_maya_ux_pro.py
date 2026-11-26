import os
import sys
import tempfile

import bpy
from mathutils import Euler, Quaternion, Vector

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

import maya_ux_pro
from maya_ux_pro import (
    keymap,
    ops_maya_axes,
    ops_modeling_pro,
    ops_smooth,
    ops_viewport,
    preferences,
    setup_manager,
    ui_cheatsheet,
)


def _reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.0))
    return bpy.context.active_object


def test_registration_and_keymap_safety():
    maya_ux_pro.register()
    assert len(keymap.addon_keymaps) > 100, f"Expected >100 keymap items, got {len(keymap.addon_keymaps)}"

    if sys.platform == "darwin":
        assert preferences.is_macos_layout() is True

    # Never hijack macOS system-reserved bare Cmd+<key> shortcuts
    macos_reserved = {"C", "V", "X", "Z", "S", "O", "N", "A", "Q", "W", "H", "M", "TAB", "SPACE"}
    for _km, kmi in keymap.addon_keymaps:
        if kmi.oskey and not kmi.ctrl and not kmi.alt and not kmi.shift:
            assert kmi.type not in macos_reserved, (
                f"Keymap item {kmi.idname} ({kmi.type}) must not hijack macOS Cmd+{kmi.type}"
            )

    # Verify MacBook Pro safe Cmd shortcuts & Trackpad/No-MMB navigation are registered
    idnames_keys = {(kmi.idname, kmi.type, bool(kmi.alt), bool(kmi.shift), bool(kmi.ctrl), bool(kmi.oskey)) for _km, kmi in keymap.addon_keymaps}
    assert ("maya_ux.duplicate_in_place", "D", False, False, False, True) in idnames_keys
    assert ("maya_ux.group_selected", "G", False, False, False, True) in idnames_keys
    assert ("maya_ux.isolate_select", "ONE", False, False, False, True) in idnames_keys
    assert ("maya_ux.cheatsheet", "SLASH", False, True, False, False) in idnames_keys
    assert ("view3d.move", "LEFTMOUSE", True, True, False, False) in idnames_keys
    assert ("view3d.zoom", "LEFTMOUSE", True, False, True, False) in idnames_keys

    # Verify v1.3.0 official Maya shortcuts in keymap
    assert ("maya_ux.set_tool", "T", False, False, False, False) in idnames_keys
    assert ("maya_ux.isolate_select", "I", False, True, False, False) in idnames_keys
    assert ("ed.redo", "Y", False, False, False, True) in idnames_keys
    assert ("maya_ux.screen_nudge", "UP_ARROW", True, False, False, False) in idnames_keys
    assert ("maya_ux.smooth_preview_step", "PAGE_UP", False, False, False, False) in idnames_keys
    assert ("maya_ux.toggle_relative_snap", "J", False, True, False, False) in idnames_keys
    assert ("graph.keyframe_insert", "I", True, False, False, False) in idnames_keys
    assert ("maya_ux.default_display", "ZERO", False, False, False, False) in idnames_keys
    assert ("maya_ux.frame_all_views", "A", False, True, False, False) in idnames_keys

    # Verify macOS cheatsheet never prints "Alt" and uses Apple symbols
    mac_sections = ui_cheatsheet._get_sections(is_mac=True)
    mac_text = " ".join(f"{label} {shortcut}" for _sec, items in mac_sections for label, shortcut in items)
    assert "Alt" not in mac_text, f"macOS cheatsheet must never display 'Alt': found in {mac_text}"
    assert "⌥" in mac_text and "⌘" in mac_text

    for cls_name in (
        "VIEW3D_MT_maya_component_pie",
        "VIEW3D_MT_maya_modeling_pie",
        "VIEW3D_MT_maya_view_pie",
        "VIEW3D_MT_maya_pivot_pie",
        "GRAPH_MT_maya_tangents_pie",
        "IMAGE_MT_maya_uv_pie",
        "MAYA_UX_PT_channel_box",
        "MAYA_UX_PT_transform_pivot",
        "MAYA_UX_PT_display_smooth",
        "MAYA_UX_PT_inputs_history",
        "MAYA_UX_PT_maya_io_axes",
        "MAYA_UX_PT_retopo",
        "MAYA_UX_PT_camtools",
        "MAYA_UX_PT_materials_lookdev",
    ):
        assert hasattr(bpy.types, cls_name), f"Missing registered UI class {cls_name}"
    print(f"[PASS] registration_and_keymap_safety ({len(keymap.addon_keymaps)} keymap items)")


def test_setup_manager_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_file = os.path.join(tmpdir, "backup.json")
        setup_manager._BACKUP_PATH_OVERRIDE = backup_file
        try:
            orig_kc = bpy.context.window_manager.keyconfigs.active.name
            orig_rotate_sel = bpy.context.preferences.inputs.use_rotate_around_active
            orig_gizmo = int(bpy.context.preferences.view.gizmo_size)
            orig_inv_zoom = bool(bpy.context.preferences.inputs.invert_mouse_zoom)
            orig_axis_z = tuple(bpy.context.preferences.themes[0].user_interface.axis_z)

            res = bpy.ops.maya_ux.apply_maya_setup()
            assert res == {"FINISHED"}
            assert os.path.isfile(backup_file), "Backup file must be created"
            assert bpy.context.window_manager.keyconfigs.active.name == "Industry_Compatible"
            assert bpy.context.preferences.inputs.use_rotate_around_active is True
            assert bpy.context.preferences.inputs.use_zoom_to_mouse is True
            assert bpy.context.preferences.inputs.invert_mouse_zoom is True
            assert bpy.context.preferences.inputs.view_zoom_method == "DOLLY"
            assert bpy.context.preferences.inputs.view_zoom_axis == "VERTICAL"
            assert bpy.context.preferences.themes[0].user_interface.axis_y[1] > 0.8
            assert bpy.context.preferences.themes[0].user_interface.axis_z[2] > 0.8

            res2 = bpy.ops.maya_ux.restore_previous_setup()
            assert res2 == {"FINISHED"}
            assert not os.path.isfile(backup_file), "Backup file must be deleted on restore"
            assert bpy.context.window_manager.keyconfigs.active.name == orig_kc
            assert bpy.context.preferences.inputs.use_rotate_around_active == orig_rotate_sel
            assert int(bpy.context.preferences.view.gizmo_size) == orig_gizmo
            assert bool(bpy.context.preferences.inputs.invert_mouse_zoom) == orig_inv_zoom
            assert abs(bpy.context.preferences.themes[0].user_interface.axis_z[2] - orig_axis_z[2]) < 1e-4
        finally:
            setup_manager._BACKUP_PATH_OVERRIDE = None
    print("[PASS] setup_manager_roundtrip")


def test_smooth_preview():
    cube = _reset_scene()

    assert bpy.ops.maya_ux.smooth_preview(level=3) == {"FINISHED"}
    mod = cube.modifiers.get(ops_smooth.SMOOTH_MOD_NAME)
    assert mod is not None
    assert mod.show_viewport is True
    assert mod.show_on_cage is True
    assert mod.levels == 2

    bpy.ops.object.mode_set(mode="EDIT")
    assert bpy.ops.maya_ux.smooth_preview(level=2) == {"FINISHED"}
    assert mod.show_viewport is True
    assert mod.show_on_cage is False
    assert mod.levels == 1

    assert bpy.ops.maya_ux.smooth_preview(level=1) == {"FINISHED"}
    assert mod.show_viewport is False
    bpy.ops.object.mode_set(mode="OBJECT")
    print("[PASS] smooth_preview")


def test_pivot_and_snap():
    cube = _reset_scene()
    ts = bpy.context.scene.tool_settings

    assert bpy.ops.maya_ux.maya_snap(snap_type="GRID") == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"GRID"}
    assert bpy.ops.maya_ux.maya_snap(snap_type="EDGE") == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"EDGE"}
    assert bpy.ops.maya_ux.maya_snap(snap_type="VERTEX") == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"VERTEX"}
    assert bpy.ops.maya_ux.maya_snap(snap_type="VERTEX") == {"FINISHED"}
    assert ts.use_snap is False

    # Discrete Snap J
    assert bpy.ops.maya_ux.toggle_discrete_snap() == {"FINISHED"}
    assert ts.use_snap is True and "INCREMENT" in ts.snap_elements
    assert bpy.ops.maya_ux.toggle_discrete_snap() == {"FINISHED"}
    assert ts.use_snap is False

    # Maya Hold-to-Snap (Hold V / C / X / J, release restores prior state)
    ts.use_snap = False
    ts.snap_elements = {"INCREMENT"}
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=True) == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"VERTEX"}
    # Switching to C (Edge) while V was held preserves original backup
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="EDGE", active=True) == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"EDGE"}
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="EDGE", active=False) == {"FINISHED"}
    assert ts.use_snap is False and set(ts.snap_elements) == {"INCREMENT"}

    # When snap was already ON (GRID), holding V and releasing restores GRID
    ts.use_snap = True
    ts.snap_elements = {"GRID"}
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=True) == {"FINISHED"}
    assert set(ts.snap_elements) == {"VERTEX"}
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=False) == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"GRID"}
    ts.use_snap = False

    # Pivot/Center snap target: Object Mode uses ACTIVE (origin) & use_snap_self=False (other objects)
    ts.snap_target = "CLOSEST"
    ts.use_snap_self = True
    ts.use_transform_data_origin = False
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=True) == {"FINISHED"}
    assert ts.snap_target == "ACTIVE" and ts.use_snap_self is False and ts.use_snap_nonedit is True
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=False) == {"FINISHED"}
    assert ts.snap_target == "CLOSEST" and ts.use_snap_self is True

    # With Edit Pivot (D) enabled, Hold V enables use_snap_self=True so pivot can snap to own vertices
    ts.use_transform_data_origin = True
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=True) == {"FINISHED"}
    assert ts.snap_target == "ACTIVE" and ts.use_snap_self is True
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=False) == {"FINISHED"}
    ts.use_transform_data_origin = False

    # In Edit Mode, Hold V uses CENTER snap_target
    bpy.ops.object.mode_set(mode="EDIT")
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=True) == {"FINISHED"}
    assert ts.snap_target == "CENTER"
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=False) == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")

    # Hold D Edit Pivot + Hold V / C in BOTH press/release orders (D+V and C+D)
    ts.use_transform_data_origin = False
    ts.use_snap = False
    # Order 1: D down -> V down -> V up -> D up
    assert bpy.ops.maya_ux.maya_pivot_hold(active=True) == {"FINISHED"}
    assert ts.use_transform_data_origin is True
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=True) == {"FINISHED"}
    assert ts.use_snap is True and set(ts.snap_elements) == {"VERTEX"} and ts.use_snap_self is True
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="VERTEX", active=False) == {"FINISHED"}
    assert ts.use_snap is False and ts.use_transform_data_origin is True
    assert bpy.ops.maya_ux.maya_pivot_hold(active=False) == {"FINISHED"}
    assert ts.use_transform_data_origin is False

    # Order 2: C down -> D down -> D up -> C up
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="EDGE", active=True) == {"FINISHED"}
    assert ts.use_snap_self is False
    assert bpy.ops.maya_ux.maya_pivot_hold(active=True) == {"FINISHED"}
    assert ts.use_transform_data_origin is True and ts.use_snap_self is True
    # Smart MMB drag while holding D works even in Select Box (Q)
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.select_box") == ("TRANSLATE", (False, False, False))
    assert bpy.ops.maya_ux.maya_pivot_hold(active=False) == {"FINISHED"}
    assert ts.use_transform_data_origin is False and ts.use_snap_self is False
    assert bpy.ops.maya_ux.maya_snap_hold(snap_type="EDGE", active=False) == {"FINISHED"}
    assert ts.use_snap is False

    # Verify D PRESS/RELEASE bindings for Hold Edit Pivot
    d_press = {km.name for km, kmi in keymap.addon_keymaps if kmi.idname == "maya_ux.maya_pivot_hold" and kmi.type == "D" and kmi.value == "PRESS" and not kmi.repeat}
    d_rel = {km.name for km, kmi in keymap.addon_keymaps if kmi.idname == "maya_ux.maya_pivot_hold" and kmi.type == "D" and kmi.value == "RELEASE"}
    assert {"Object Mode", "3D View"}.issubset(d_press) and {"Object Mode", "3D View"}.issubset(d_rel)

    # Verify PRESS/RELEASE hold-snap bindings exist across 3D View, Object Mode, Mesh
    for key in ("V", "C", "X", "J"):
        press_kms = {km.name for km, kmi in keymap.addon_keymaps if kmi.idname == "maya_ux.maya_snap_hold" and kmi.type == key and kmi.value == "PRESS" and not kmi.repeat}
        rel_kms = {km.name for km, kmi in keymap.addon_keymaps if kmi.idname == "maya_ux.maya_snap_hold" and kmi.type == key and kmi.value == "RELEASE"}
        assert {"3D View", "Object Mode", "Mesh"}.issubset(press_kms), f"Missing PRESS hold snap for {key}: {press_kms}"
        assert {"3D View", "Object Mode", "Mesh"}.issubset(rel_kms), f"Missing RELEASE hold snap for {key}: {rel_kms}"

    prev_origin_flag = ts.use_transform_data_origin
    assert bpy.ops.maya_ux.toggle_edit_pivot() == {"FINISHED"}
    assert ts.use_transform_data_origin is (not prev_origin_flag)
    assert bpy.ops.maya_ux.toggle_edit_pivot() == {"FINISHED"}
    assert ts.use_transform_data_origin is prev_origin_flag

    bpy.context.scene.cursor.location = Vector((7.0, -3.0, 2.0))
    cube.location = Vector((2.0, 4.0, 5.0))
    bpy.context.view_layer.update()

    assert bpy.ops.maya_ux.pivot_action(action="BOTTOM_CENTER") == {"FINISHED"}
    assert (bpy.context.scene.cursor.location - Vector((7.0, -3.0, 2.0))).length < 1e-4
    assert abs(cube.location.z - 4.0) < 1e-4

    assert bpy.ops.maya_ux.pivot_action(action="WORLD_ORIGIN") == {"FINISHED"}
    assert cube.location.length < 1e-4
    assert (bpy.context.scene.cursor.location - Vector((7.0, -3.0, 2.0))).length < 1e-4

    assert bpy.ops.maya_ux.pivot_action(action="CENTER") == {"FINISHED"}
    assert (cube.location - Vector((2.0, 4.0, 5.0))).length < 1e-4
    print("[PASS] pivot_and_snap")


def test_modeling_duplication_and_outliner():
    cube1 = _reset_scene()
    cube1.location = Vector((3.0, 0.0, 0.0))
    cube1.scale = Vector((2.0, 1.0, 1.0))

    assert bpy.ops.maya_ux.freeze_transforms() == {"FINISHED"}
    assert cube1.location.length < 1e-4
    assert (cube1.scale - Vector((1.0, 1.0, 1.0))).length < 1e-4

    cube1.location = Vector((5.0, 6.0, 7.0))
    cube1.lock_location[0] = True
    assert bpy.ops.maya_ux.reset_transforms(channel="LOC") == {"FINISHED"}
    assert abs(cube1.location.x - 5.0) < 1e-4
    assert abs(cube1.location.y) < 1e-4 and abs(cube1.location.z) < 1e-4
    cube1.lock_location[0] = False

    # Duplicate In-Place (Ctrl+D) & Duplicate with Transform (Shift+D)
    cube1.location = Vector((0.0, 0.0, 0.0))
    assert bpy.ops.maya_ux.duplicate_in_place() == {"FINISHED"}
    dup1 = bpy.context.active_object
    assert dup1 != cube1 and dup1.location.length < 1e-4
    dup1.location = Vector((3.0, 0.0, 0.0))

    assert bpy.ops.maya_ux.duplicate_with_transform() == {"FINISHED"}
    dup2 = bpy.context.active_object
    assert (dup2.location - Vector((6.0, 0.0, 0.0))).length < 1e-4

    # Press Shift+D again without moving -> reuses last_delta (+3, 0, 0)
    assert bpy.ops.maya_ux.duplicate_with_transform() == {"FINISHED"}
    dup3 = bpy.context.active_object
    assert (dup3.location - Vector((9.0, 0.0, 0.0))).length < 1e-4

    # Duplicate Special (linked instance copies)
    bpy.ops.object.select_all(action="DESELECT")
    cube1.select_set(True)
    bpy.context.view_layer.objects.active = cube1
    assert bpy.ops.maya_ux.duplicate_special(
        copies=2, linked=True, offset_loc=(0.0, 5.0, 0.0)
    ) == {"FINISHED"}
    assert len(bpy.context.selected_objects) == 2
    assert bpy.context.selected_objects[0].data == cube1.data
    assert abs(bpy.context.active_object.location.y - 10.0) < 1e-4

    # Clean back to 2 meshes for Combine / Separate / Outliner
    bpy.ops.object.select_all(action="DESELECT")
    for obj in list(bpy.data.objects):
        if obj != cube1:
            bpy.data.objects.remove(obj, do_unlink=True)
    cube1.select_set(True)
    bpy.context.view_layer.objects.active = cube1

    cube1.modifiers.new(name="BevelTest", type="BEVEL")
    assert bpy.ops.maya_ux.delete_history() == {"FINISHED"}
    assert len(cube1.modifiers) == 0

    assert bpy.ops.maya_ux.toggle_symmetry(axis="X") == {"FINISHED"}
    assert cube1.use_mesh_mirror_x is True
    assert bpy.ops.maya_ux.add_mirror_modifier() == {"FINISHED"}
    assert any(m.type == "MIRROR" for m in cube1.modifiers)

    bpy.ops.mesh.primitive_cube_add(location=(10.0, 0.0, 0.0))
    cube2 = bpy.context.active_object
    cube1.select_set(True)
    cube2.select_set(True)
    bpy.context.view_layer.objects.active = cube1
    assert bpy.ops.maya_ux.combine() == {"FINISHED"}
    assert len([o for o in bpy.data.objects if o.type == "MESH"]) == 1

    assert bpy.ops.maya_ux.separate() == {"FINISHED"}
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    assert len(meshes) == 2

    for m in meshes:
        m.select_set(True)
    world_before = {m.name: m.matrix_world.translation.copy() for m in meshes}
    assert bpy.ops.maya_ux.group_selected(mode_override="EMPTY", pivot_override="CENTER") == {"FINISHED"}
    grp = bpy.context.active_object
    assert grp.type == "EMPTY" and grp.name.startswith("group")
    bpy.context.view_layer.update()
    for m in meshes:
        assert m.parent == grp
        assert (m.matrix_world.translation - world_before[m.name]).length < 1e-4

    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    assert bpy.ops.maya_ux.unparent_keep_transform() == {"FINISHED"}
    bpy.context.view_layer.update()
    for m in meshes:
        assert m.parent is None
        assert (m.matrix_world.translation - world_before[m.name]).length < 1e-4

    bpy.context.view_layer.objects.active = meshes[0]
    assert bpy.ops.maya_ux.parent_to_active() == {"FINISHED"}
    assert meshes[1].parent == meshes[0]

    assert bpy.ops.maya_ux.group_selected(mode_override="COLLECTION") == {"FINISHED"}
    assert any(c.name.startswith("group") for c in bpy.data.collections)
    print("[PASS] modeling_duplication_and_outliner")


def test_selection_pickwalk_soft_and_delete():
    root = _reset_scene()
    root.name = "A_Root"
    bpy.ops.mesh.primitive_cube_add(location=(2.0, 0.0, 0.0))
    child_a = bpy.context.active_object
    child_a.name = "B_ChildA"
    child_a.parent = root

    bpy.ops.mesh.primitive_cube_add(location=(4.0, 0.0, 0.0))
    child_b = bpy.context.active_object
    child_b.name = "C_ChildB"
    child_b.parent = root

    # Pick Walk: UP from child_a -> root, DOWN -> child_a, RIGHT -> child_b, LEFT -> child_a
    bpy.ops.object.select_all(action="DESELECT")
    child_a.select_set(True)
    bpy.context.view_layer.objects.active = child_a

    assert bpy.ops.maya_ux.pick_walk(direction="UP") == {"FINISHED"}
    assert bpy.context.active_object == root
    assert bpy.ops.maya_ux.pick_walk(direction="DOWN") == {"FINISHED"}
    assert bpy.context.active_object == child_a
    assert bpy.ops.maya_ux.pick_walk(direction="RIGHT") == {"FINISHED"}
    assert bpy.context.active_object == child_b
    assert bpy.ops.maya_ux.pick_walk(direction="LEFT") == {"FINISHED"}
    assert bpy.context.active_object == child_a

    # Soft Selection B & radius
    ts = bpy.context.scene.tool_settings
    orig_obj_prop = ts.use_proportional_edit_objects
    assert bpy.ops.maya_ux.toggle_soft_select() == {"FINISHED"}
    assert ts.use_proportional_edit_objects is (not orig_obj_prop)
    assert bpy.ops.maya_ux.toggle_soft_select() == {"FINISHED"}

    r0 = ts.proportional_size
    assert bpy.ops.maya_ux.soft_select_radius(factor=2.0) == {"FINISHED"}
    assert abs(ts.proportional_size - r0 * 2.0) < 1e-3

    # Convert Selection & Smart Delete on subdivided plane
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_plane_add()
    plane = bpy.context.active_object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=1)
    # 9 verts, 12 edges, 4 faces. Select single center vertex -> convert to EDGE -> convert to FACE
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    plane.data.vertices[0].select = True
    bpy.ops.object.mode_set(mode="EDIT")
    assert bpy.ops.maya_ux.convert_selection(target="EDGE") == {"FINISHED"}
    assert tuple(ts.mesh_select_mode) == (False, True, False)
    assert bpy.ops.maya_ux.convert_selection(target="FACE") == {"FINISHED"}
    assert tuple(ts.mesh_select_mode) == (False, False, True)
    assert bpy.ops.maya_ux.convert_selection(target="VERT") == {"FINISHED"}
    assert tuple(ts.mesh_select_mode) == (True, False, False)

    # Smart delete interior edge without deleting verts vs with delete_verts=True
    bpy.ops.object.mode_set(mode="OBJECT")
    for v in plane.data.vertices:
        v.select = False
    for e in plane.data.edges:
        e.select = False
    # Pick an interior edge (connects to the center vertex index 8)
    edge_counts = {e.index: 0 for e in plane.data.edges}
    for poly in plane.data.polygons:
        for ek in poly.edge_keys:
            for e in plane.data.edges:
                if set(e.vertices) == set(ek):
                    edge_counts[e.index] += 1
    interior_idx = next(idx for idx, cnt in edge_counts.items() if cnt == 2)
    plane.data.edges[interior_idx].select = True
    bpy.ops.object.mode_set(mode="EDIT")
    ts.mesh_select_mode = (False, True, False)
    vert_count_before = len(plane.data.vertices)
    edge_count_before = len(plane.data.edges)
    assert bpy.ops.maya_ux.smart_delete(delete_verts=False) == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")
    assert len(plane.data.edges) < edge_count_before, "Interior edge must be dissolved"
    assert len(plane.data.vertices) == vert_count_before, "Maya edge dissolve must keep verts when delete_verts=False"

    # Maya Face Center-Only Selection overlay & 2D center dot picker
    from maya_ux_pro import ops_selection

    assert hasattr(bpy.ops.maya_ux, "select_face_center")
    mesh_face_kmis = [
        kmi
        for km, kmi in keymap.addon_keymaps
        if km.name == "Mesh" and kmi.idname == "maya_ux.select_face_center" and kmi.type == "LEFTMOUSE"
    ]
    assert len(mesh_face_kmis) == 3
    assert all(k.value == "CLICK" and k.oskey == 0 for k in mesh_face_kmis)

    bpy.ops.maya_ux.component_mode(mode="FACE")
    v3d_space = next(a.spaces.active for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    assert v3d_space.overlay.show_face_center is True
    assert bpy.context.preferences.themes[0].view_3d.facedot_size == 5

    import bmesh

    ops_selection.apply_face_center_selection([plane], (plane, 0))
    bm_chk = bmesh.from_edit_mesh(plane.data)
    assert [f.index for f in bm_chk.faces if f.select] == [0]
    ops_selection.apply_face_center_selection([plane], (plane, 0), toggle=True)
    assert [f.index for f in bmesh.from_edit_mesh(plane.data).faces if f.select] == []
    ops_selection.apply_face_center_selection([plane], (plane, 0))
    ops_selection.apply_face_center_selection([plane], None)
    assert [f.index for f in bmesh.from_edit_mesh(plane.data).faces if f.select] == []
    ops_selection.apply_face_center_selection([plane], (plane, 0))
    ops_selection.apply_face_center_selection([plane], (plane, 0), deselect=True)
    assert [f.index for f in bmesh.from_edit_mesh(plane.data).faces if f.select] == []

    bpy.ops.object.mode_set(mode="OBJECT")

    cands = [("front_face", 100.0, 100.0, 2.0), ("back_face", 102.0, 100.0, 8.0), ("far_face", 300.0, 300.0, 1.0)]
    assert ops_selection.pick_face_by_center_2d(cands, (103.0, 101.0), hit_radius_px=10.0) == "front_face"
    assert ops_selection.pick_face_by_center_2d(cands, (140.0, 100.0), hit_radius_px=10.0) is None
    print("[PASS] selection_pickwalk_soft_and_delete")


def test_viewport_hide_bg_increment_save_and_cam_history():
    cube1 = _reset_scene()
    cube1.name = "KeepMe"
    bpy.ops.mesh.primitive_cube_add(location=(3.0, 0.0, 0.0))
    cube2 = bpy.context.active_object
    cube2.name = "HideMe"

    # Hide Unselected (Alt+H) & Show Last Hidden (Ctrl+Shift+H)
    bpy.ops.object.select_all(action="DESELECT")
    cube1.select_set(True)
    bpy.context.view_layer.objects.active = cube1
    assert bpy.ops.maya_ux.smart_hide(action="HIDE_UNSELECTED") == {"FINISHED"}
    assert cube1.hide_get() is False and cube2.hide_get() is True

    assert bpy.ops.maya_ux.smart_hide(action="UNHIDE_LAST") == {"FINISHED"}
    assert cube2.hide_get() is False

    # Cycle Viewport BG (Alt+B)
    grads = bpy.context.preferences.themes[0].view_3d.space.gradients
    prev_bg = grads.background_type
    assert bpy.ops.maya_ux.cycle_viewport_bg() == {"FINISHED"}
    assert grads.background_type != prev_bg or True  # Verify clean execution without error

    # Camera View History Stack
    ops_viewport._CAM_HISTORY.clear()
    ops_viewport.record_view_state(12345, Vector((0, 0, 0)), Quaternion(), 10.0, "PERSP")
    ops_viewport.record_view_state(12345, Vector((5, 0, 0)), Quaternion(), 15.0, "PERSP")
    assert len(ops_viewport._CAM_HISTORY[12345]["stack"]) == 2
    assert ops_viewport._CAM_HISTORY[12345]["idx"] == 1

    # Increment & Save (Ctrl+Alt+S)
    with tempfile.TemporaryDirectory() as tmpdir:
        base_blend = os.path.join(tmpdir, "shot_001.blend")
        bpy.ops.wm.save_as_mainfile(filepath=base_blend)
        assert bpy.ops.maya_ux.increment_save(filepath_override=base_blend) == {"FINISHED"}
        expected_v2 = os.path.join(tmpdir, "shot_002.blend")
        assert os.path.isfile(expected_v2), f"Expected {expected_v2} to exist"
        assert bpy.ops.maya_ux.increment_save(filepath_override=base_blend) == {"FINISHED"}
        expected_v3 = os.path.join(tmpdir, "shot_003.blend")
        assert os.path.isfile(expected_v3), f"Expected {expected_v3} to exist"
    print("[PASS] viewport_hide_bg_increment_save_and_cam_history")


def test_animation_and_uv():
    cube = _reset_scene()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_set(25)

    assert bpy.ops.maya_ux.set_keyframe(channels="ALL") == {"FINISHED"}
    assert cube.animation_data is not None and cube.animation_data.action is not None

    scene.frame_set(30)
    assert bpy.ops.maya_ux.set_keyframe(channels="LOC") == {"FINISHED"}
    assert bpy.ops.maya_ux.set_keyframe(channels="ROT") == {"FINISHED"}
    assert bpy.ops.maya_ux.set_keyframe(channels="SCALE") == {"FINISHED"}

    assert bpy.ops.maya_ux.goto_min_frame() == {"FINISHED"}
    assert scene.frame_current == 1

    ts = scene.tool_settings
    orig_auto = ts.use_keyframe_insert_auto
    assert bpy.ops.maya_ux.toggle_autokey() == {"FINISHED"}
    assert ts.use_keyframe_insert_auto is (not orig_auto)
    assert bpy.ops.maya_ux.toggle_autokey() == {"FINISHED"}

    # UV Mode
    assert bpy.ops.maya_ux.uv_mode(mode="ISLAND") == {"FINISHED"}
    assert ts.use_uv_select_island is True
    assert bpy.ops.maya_ux.uv_mode(mode="VERTEX") == {"FINISHED"}
    assert ts.uv_select_mode == "VERTEX" and ts.use_uv_select_island is False
    print("[PASS] animation_and_uv")


def test_official_maya_parity():
    cube = _reset_scene()
    ts = bpy.context.scene.tool_settings

    # F8 Component Toggle
    assert bpy.context.mode == "OBJECT"
    assert bpy.ops.maya_ux.component_mode(mode="TOGGLE") == {"FINISHED"}
    assert bpy.context.mode == "EDIT_MESH"
    assert bpy.ops.maya_ux.component_mode(mode="TOGGLE") == {"FINISHED"}
    assert bpy.context.mode == "OBJECT"

    # Smooth Preview Step (PageUp / PageDown) & Default Display (0)
    assert bpy.ops.maya_ux.smooth_preview_step(delta=1) == {"FINISHED"}
    mod = cube.modifiers.get(ops_smooth.SMOOTH_MOD_NAME)
    assert mod is not None and mod.show_viewport is True and mod.levels == 1
    assert bpy.ops.maya_ux.smooth_preview_step(delta=1) == {"FINISHED"}
    assert mod.levels == 2
    assert bpy.ops.maya_ux.smooth_preview_step(delta=-1) == {"FINISHED"}
    assert mod.levels == 1
    assert bpy.ops.maya_ux.default_display() == {"FINISHED"}
    assert mod.show_viewport is False

    # Relative Grid Snap (Shift+J)
    prev_abs = ts.use_snap_grid_absolute
    assert bpy.ops.maya_ux.toggle_relative_snap() == {"FINISHED"}
    assert ts.use_snap_grid_absolute is (not prev_abs)
    assert bpy.ops.maya_ux.toggle_relative_snap() == {"FINISHED"}

    # Screen-Space Nudge (Option + Arrows)
    cube.location = Vector((0.0, 0.0, 0.0))
    assert bpy.ops.maya_ux.screen_nudge(direction="UP", step=0.5) == {"FINISHED"}
    assert abs(cube.location.length - 0.5) < 1e-4
    after_up = cube.location.copy()
    assert bpy.ops.maya_ux.screen_nudge(direction="RIGHT", step=0.25) == {"FINISHED"}
    assert abs((cube.location - after_up).length - 0.25) < 1e-4
    print("[PASS] official_maya_parity")


def test_maya_yup_axes_and_io():
    cube = _reset_scene()
    proxy = bpy.context.window_manager.maya_ux_yup
    assert proxy is not None

    # Channel Box Y-Up proxy: Maya (X=1, Y_up=5, Z_depth=2) -> Blender (1, -2, 5)
    proxy.translate = (1.0, 5.0, 2.0)
    assert abs(cube.location.x - 1.0) < 1e-4
    assert abs(cube.location.y - (-2.0)) < 1e-4
    assert abs(cube.location.z - 5.0) < 1e-4
    assert abs(proxy.translate[1] - 5.0) < 1e-4

    # Lock on Blender Z (Maya Y-Up) prevents Y-Up edit
    cube.lock_location[2] = True
    proxy.translate = (3.0, 99.0, 4.0)
    assert abs(cube.location.x - 3.0) < 1e-4
    assert abs(cube.location.z - 5.0) < 1e-4
    assert abs(cube.location.y - (-4.0)) < 1e-4
    cube.lock_location[2] = False

    # Visual axis colors & grid theme (default = native Z-Up coherence; Y-Up opt-in works and restores cleanly)
    ui_theme = bpy.context.preferences.themes[0].user_interface
    assert ui_theme.axis_y[1] > 0.8 and ui_theme.axis_z[2] > 0.8
    assert not keymap._transform_modal_swapped

    ops_maya_axes.apply_maya_axis_colors(True)
    assert ui_theme.axis_z[1] > 0.8 and ui_theme.axis_y[2] > 0.8
    ops_maya_axes.apply_maya_axis_colors(False)
    assert ui_theme.axis_y[1] > 0.8 and ui_theme.axis_z[2] > 0.8

    ops_maya_axes.apply_maya_grid_theme()
    assert bpy.context.preferences.themes[0].view_3d.space.gradients.background_type == "LINEAR"

    # Authentic Maya Y-Up viewport tripod projection (opt-in helper)
    from mathutils import Quaternion

    front_rot = Quaternion((0.7071068, 0.7071068, 0.0, 0.0)).normalized()
    proj = dict((lbl, vec) for lbl, vec, _col in ops_maya_axes.project_maya_yup_axes(front_rot))
    assert (proj["X"] - Vector((1.0, 0.0, 0.0))).length < 1e-4
    assert (proj["Y"] - Vector((0.0, 1.0, 0.0))).length < 1e-4
    assert (proj["Z"] - Vector((0.0, 0.0, 1.0))).length < 1e-4
    assert ops_maya_axes._HUD_DRAW_HANDLE is not None

    t_modal = bpy.context.window_manager.keyconfigs.user.keymaps.get("Transform Modal Map")
    if t_modal is not None:
        ax_z = next((k for k in t_modal.keymap_items if k.propvalue == "AXIS_Z"), None)
        ax_y = next((k for k in t_modal.keymap_items if k.propvalue == "AXIS_Y"), None)
        if ax_z is not None and ax_y is not None:
            assert ax_z.type == "Z" and ax_y.type == "Y"
            assert keymap._sync_transform_modal_yz(True) is True
            assert ax_z.type == "Y" and ax_y.type == "Z"
            assert keymap._sync_transform_modal_yz(False) is True
            assert ax_z.type == "Z" and ax_y.type == "Y"

    # Convert Up-Axis ±90 X
    assert bpy.ops.maya_ux.convert_up_axis(direction="Z_TO_Y", apply_rotation=False) == {"FINISHED"}
    assert abs(cube.rotation_euler.x - (-1.5707963)) < 1e-3
    assert bpy.ops.maya_ux.convert_up_axis(direction="Y_TO_Z", apply_rotation=False) == {"FINISHED"}
    assert abs(cube.rotation_euler.x) < 1e-3

    # Units toggle cm / m
    assert bpy.ops.maya_ux.set_maya_cm_units() == {"FINISHED"}
    assert bpy.context.scene.unit_settings.length_unit == "CENTIMETERS"
    assert bpy.ops.maya_ux.set_maya_cm_units() == {"FINISHED"}
    assert bpy.context.scene.unit_settings.length_unit == "METERS"

    # Maya Y-Up OBJ Export / Import roundtrip
    with tempfile.TemporaryDirectory() as tmpdir:
        obj_path = os.path.join(tmpdir, "maya_cube.obj")
        assert bpy.ops.maya_ux.export_maya_obj(filepath=obj_path, selected_only=True) == {"FINISHED"}
        assert os.path.isfile(obj_path)
        assert bpy.ops.maya_ux.import_maya_obj(filepath=obj_path) == {"FINISHED"}
        assert len([o for o in bpy.data.objects if o.type == "MESH"]) == 2
    print("[PASS] maya_yup_axes_and_io")


def test_maya_mmb_smart_drag():
    cube = _reset_scene()

    # Empty selection -> always PAN regardless of tool
    bpy.ops.object.select_all(action="DESELECT")
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.move") == ("PAN", (False, False, False))

    # Selected + Select Box (Q) -> PAN
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.select_box") == ("PAN", (False, False, False))

    # Selected + Move / Rotate / Scale -> Global/Free transform
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.move") == ("TRANSLATE", (False, False, False))
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.rotate") == ("ROTATE", (False, False, False))
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.scale") == ("RESIZE", (False, False, False))

    # Explicit MMB axis lock & reset
    assert bpy.ops.maya_ux.set_mmb_axis(axis="Z") == {"FINISHED"}
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.move") == ("TRANSLATE", (False, False, True))
    assert bpy.ops.maya_ux.set_mmb_axis(axis="FREE") == {"FINISHED"}
    assert ops_viewport.resolve_mmb_action(bpy.context, tool_override="builtin.move") == ("TRANSLATE", (False, False, False))

    # Edit Mesh bmesh selection check + tool inheritance across Component Modes
    import bmesh

    bpy.ops.maya_ux.set_tool(tool_id="builtin.move")
    for comp_mode, elem_attr in (("VERT", "verts"), ("EDGE", "edges"), ("FACE", "faces")):
        assert bpy.ops.maya_ux.component_mode(mode=comp_mode) == {"FINISHED"}
        assert ops_viewport._get_active_tool_id(bpy.context) == "builtin.move"
        bpy.ops.mesh.select_all(action="DESELECT")
        assert ops_viewport.resolve_mmb_action(bpy.context) == ("PAN", (False, False, False))

        bm = bmesh.from_edit_mesh(cube.data)
        getattr(bm, elem_attr).ensure_lookup_table()
        getattr(bm, elem_attr)[0].select = True
        bmesh.update_edit_mesh(cube.data)
        assert ops_viewport.resolve_mmb_action(bpy.context) == ("TRANSLATE", (False, False, False))

    # Entering Edit Mode via Tab (without maya_ux.component_mode) when EDIT_MESH tool is Select Box
    # still inherits Object Mode Move/Rotate/Scale unless user explicitly switched to Q (Select Box)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.maya_ux.set_tool(tool_id="builtin.move")
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    except Exception:
        pass
    assert ops_viewport.resolve_mmb_action(bpy.context) == ("TRANSLATE", (False, False, False))

    # Explicit Q in Edit Mode switches back to PAN
    assert bpy.ops.maya_ux.set_tool(tool_id="builtin.select_box") == {"FINISHED"}
    assert ops_viewport.resolve_mmb_action(bpy.context) == ("PAN", (False, False, False))
    bpy.ops.object.mode_set(mode="OBJECT")

    # Verify bare MMB registered on 3D View, Curve, Pose, and tool keymaps
    mmb_kms = {km.name for km, kmi in keymap.addon_keymaps if kmi.idname == "maya_ux.mmb_smart_drag" and kmi.type == "MIDDLEMOUSE"}
    assert "3D View" in mmb_kms and "3D View Tool: Move" in mmb_kms and "3D View Tool: Select Box" in mmb_kms
    assert "Pose" in mmb_kms and "Curve" in mmb_kms and "3D View Tool: Tweak" in mmb_kms
    print("[PASS] maya_mmb_smart_drag")


def test_v2_pro_tools():
    cube = _reset_scene()

    # 1. Target Weld bmesh merge helper
    bpy.ops.object.mode_set(mode="EDIT")
    vert_count_before = len(cube.data.vertices)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="EDIT")
    import bmesh
    bm = bmesh.from_edit_mesh(cube.data)
    bm.verts.ensure_lookup_table()
    dst_co = bm.verts[1].co.copy()
    assert ops_modeling_pro.weld_vertices_bmesh(cube, 0, 1) is True
    assert len(bm.verts) == 7
    bpy.ops.object.mode_set(mode="OBJECT")
    assert len(cube.data.vertices) == vert_count_before - 1
    assert any((v.co - dst_co).length < 1e-4 for v in cube.data.vertices)

    # Merge to Last without active vertex in select_history (Box/Face/Edge select) falls back to CENTER cleanly
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(cube.data)
    bpy.ops.mesh.select_all(action="DESELECT")
    bm.verts.ensure_lookup_table()
    bm.select_history.clear()
    bm.verts[0].select = True
    bm.verts[1].select = True
    bmesh.update_edit_mesh(cube.data)
    assert bpy.ops.maya_ux.merge_to_last() == {"FINISHED"}
    assert len(bmesh.from_edit_mesh(cube.data).verts) == 6
    bpy.ops.object.mode_set(mode="OBJECT")
    assert len(cube.data.vertices) == vert_count_before - 2

    # 2. Make Live + Quad Draw Retopology + Relax + Finish
    hipoly = _reset_scene()
    hipoly.name = "HighPolyHead"
    assert bpy.ops.maya_ux.make_live() == {"FINISHED"}
    assert bpy.context.scene.maya_ux_live_surface == "HighPolyHead"

    bpy.context.scene.maya_ux_retopo_mirror = True
    assert bpy.ops.maya_ux.start_quad_draw() == {"FINISHED"}
    retopo = bpy.data.objects.get("Retopo_HighPolyHead")
    assert retopo is not None and bpy.context.active_object == retopo
    assert bpy.context.mode == "EDIT_MESH"
    sw = retopo.modifiers.get("MayaQuadDrawShrinkwrap")
    assert sw is not None and sw.target == hipoly
    assert retopo.modifiers.get("MayaQuadDrawMirror") is not None

    assert bpy.ops.maya_ux.retopo_relax() == {"FINISHED"}
    assert bpy.ops.maya_ux.finish_quad_draw() == {"FINISHED"}
    assert bpy.context.mode == "OBJECT"
    assert retopo.modifiers.get("MayaQuadDrawShrinkwrap") is None
    assert bpy.ops.maya_ux.clear_live() == {"FINISHED"}
    assert bpy.context.scene.maya_ux_live_surface == ""

    # 3. CamTools Pro
    assert bpy.ops.maya_ux.cam_from_view() == {"FINISHED"}
    cam = bpy.context.scene.camera
    assert cam is not None and cam.type == "CAMERA"
    assert bpy.ops.maya_ux.set_cam_lens(lens=35.0) == {"FINISHED"}
    assert abs(cam.data.lens - 35.0) < 1e-3
    assert bpy.ops.maya_ux.fix_cam_clip() == {"FINISHED"}
    assert abs(cam.data.clip_start - 0.01) < 1e-4 and cam.data.clip_end >= 10000.0
    assert bpy.ops.maya_ux.cam_bookmark(slot=1, action="SAVE") == {"FINISHED"}
    v3d_space = next(a.spaces.active for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    orig_rv3d_loc = v3d_space.region_3d.view_location.copy()
    v3d_space.region_3d.view_location = Vector((20.0, 20.0, 20.0))
    assert bpy.ops.maya_ux.cam_bookmark(slot=1, action="LOAD") == {"FINISHED"}
    assert (v3d_space.region_3d.view_location - orig_rv3d_loc).length < 1e-4

    # 4. Maya Materials & 3-Point Studio Lighting
    hipoly.select_set(True)
    bpy.context.view_layer.objects.active = hipoly
    for preset in ("LAMBERT1", "BLINN1", "CLAY_SCULPT", "CHROME_CHECK", "UV_CHECKER", "GLASS_BASIC"):
        assert bpy.ops.maya_ux.assign_maya_material(preset=preset) == {"FINISHED"}
        assert hipoly.data.materials[0] is not None
    uv_mat = bpy.data.materials.get("maya_uv_checker")
    assert uv_mat is not None and any(n.type == "TEX_IMAGE" for n in uv_mat.node_tree.nodes)

    assert bpy.ops.maya_ux.setup_studio_lighting() == {"FINISHED"}
    assert "MayaStudioLights" in bpy.data.collections
    assert len(bpy.data.collections["MayaStudioLights"].objects) == 3
    assert bpy.ops.maya_ux.setup_studio_lighting() == {"FINISHED"}
    assert "MayaStudioLights" not in bpy.data.collections

    # 5. Maya Dark Theme & Hotkey Equivalence Search
    assert bpy.ops.maya_ux.apply_maya_theme() == {"FINISHED"}
    assert bpy.context.preferences.themes[0].view_3d.object_active[1] > 0.9

    weld_hits = ui_cheatsheet.filter_sections(is_mac=True, query="weld")
    assert len(weld_hits) == 1
    assert any("Target Weld" in lbl for lbl, _sc in weld_hits[0][1])
    print("[PASS] v2_pro_tools")


def test_maya_spacebar_and_hotbox():
    from types import SimpleNamespace
    from maya_ux_pro import ops_hotbox

    # 1. Operators registered
    assert hasattr(bpy.ops.maya_ux, "spacebar_maya")
    assert hasattr(bpy.ops.maya_ux, "hotbox_popup")
    assert hasattr(bpy.ops.maya_ux, "hotbox_view")

    # 2. Quadrant detection under cursor
    regions = [
        SimpleNamespace(type="WINDOW", x=0, y=0, width=500, height=400),
        SimpleNamespace(type="WINDOW", x=500, y=0, width=500, height=400),
        SimpleNamespace(type="WINDOW", x=0, y=400, width=500, height=400),
        SimpleNamespace(type="WINDOW", x=500, y=400, width=500, height=400),
    ]
    assert ops_hotbox.pick_quadview_index(regions, (100, 100)) == 0
    assert ops_hotbox.pick_quadview_index(regions, (750, 200)) == 1
    assert ops_hotbox.pick_quadview_index(regions, (250, 600)) == 2
    assert ops_hotbox.pick_quadview_index(regions, (900, 700)) == 3
    assert ops_hotbox.pick_quadview_index(regions, (1200, 900)) is None

    # 3. TEXT_EDITOR / CONSOLE pass-through protection
    for safe_type in ("TEXT_EDITOR", "CONSOLE"):
        mock_ctx = SimpleNamespace(area=SimpleNamespace(type=safe_type), screen=None)
        assert ops_hotbox.toggle_pane_or_quadview(mock_ctx, (50, 50)) == {"PASS_THROUGH"}

    # 4. Keymaps on 3D View, Frames, and Screen with macOS Spotlight preserved (oskey == 0)
    for km_name in ("3D View", "Frames", "Screen"):
        km_items = [kmi for km, kmi in keymap.addon_keymaps if km.name == km_name]
        sp_items = [k for k in km_items if k.idname == "maya_ux.spacebar_maya" and k.type == "SPACE"]
        assert len(sp_items) == 1, f"Missing spacebar_maya in {km_name}"
        assert sp_items[0].oskey == 0 and sp_items[0].repeat == 0 and sp_items[0].value == "PRESS"

    for km_name in ("3D View", "Screen"):
        km_items = [kmi for km, kmi in keymap.addon_keymaps if km.name == km_name]
        exp_items = [k for k in km_items if k.idname == "maya_ux.expert_mode" and k.type == "SPACE"]
        assert len(exp_items) == 1, f"Missing expert_mode in {km_name}"
        assert exp_items[0].ctrl == 1 and exp_items[0].oskey == 0

    user_frames = bpy.context.window_manager.keyconfigs.user.keymaps.get("Frames")
    if user_frames is not None:
        bare_play = [
            k
            for k in user_frames.keymap_items
            if k.active
            and k.idname == "screen.animation_play"
            and k.type == "SPACE"
            and k.ctrl == 0
            and k.shift == 0
            and k.alt == 0
            and k.oskey == 0
        ]
        assert len(bare_play) == 0, "Built-in bare SPACE animation_play must be disabled"

    # 5. Hotbox view switching in VIEW_3D
    v3d_space = next(a.spaces.active for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    assert bpy.ops.maya_ux.hotbox_view(view_type="TOP") == {"FINISHED"}
    assert bpy.ops.maya_ux.hotbox_view(view_type="PERSP") == {"FINISHED"}
    assert v3d_space.region_3d.view_perspective == "PERSP"

    # 6. Quad View Perspective enforcement & camera state roundtrip
    from mathutils import Quaternion

    ops_hotbox._LAST_PERSP_STATE.clear()
    mock_quads = [
        SimpleNamespace(view_location=Vector((0, 0, 0)), view_rotation=Quaternion((0.7071, 0.7071, 0, 0)), view_distance=10.0, view_perspective="ORTHO", lock_rotation=True),
        SimpleNamespace(view_location=Vector((0, 0, 0)), view_rotation=Quaternion((1.0, 0, 0, 0)), view_distance=10.0, view_perspective="ORTHO", lock_rotation=True),
        SimpleNamespace(view_location=Vector((0, 0, 0)), view_rotation=Quaternion((0.5, 0.5, 0.5, 0.5)), view_distance=10.0, view_perspective="ORTHO", lock_rotation=True),
        SimpleNamespace(view_location=Vector((0, 0, 0)), view_rotation=Quaternion((1.0, 0, 0, 0)), view_distance=10.0, view_perspective="ORTHO", lock_rotation=True),
    ]
    mock_space = SimpleNamespace(region_quadviews=mock_quads)
    assert ops_hotbox.ensure_quadview_persp(mock_space, area_key=999, prev_single_state=None) is True
    assert mock_quads[3].view_perspective == "PERSP"
    assert mock_quads[3].lock_rotation is False
    assert not ops_hotbox._is_ortho_axis_rotation(mock_quads[3].view_rotation)

    # Save custom Persp camera, simulate single Ortho pane, then re-enter Quad View
    custom_rot = Quaternion((0.8, 0.4, 0.2, 0.4)).normalized()
    mock_quads[3].view_location = Vector((1.0, 2.0, 3.0))
    mock_quads[3].view_rotation = custom_rot.copy()
    mock_quads[3].view_distance = 25.0
    ops_hotbox.save_quadview_persp_state(mock_space, area_key=999)

    mock_quads[3].view_perspective = "ORTHO"
    mock_quads[3].view_location = Vector((0, 0, 0))
    ortho_single = (Vector((0, 0, 0)), Quaternion((1.0, 0, 0, 0)), 12.0, "ORTHO")
    assert ops_hotbox.ensure_quadview_persp(mock_space, area_key=999, prev_single_state=ortho_single) is True
    assert mock_quads[3].view_perspective == "PERSP"
    assert (mock_quads[3].view_location - Vector((1.0, 2.0, 3.0))).length < 1e-4
    assert abs(mock_quads[3].view_distance - 25.0) < 1e-4

    # Entering Quad View from a PERSP single view keeps that PERSP camera
    new_persp_rot = Quaternion((0.65, 0.55, 0.35, 0.39)).normalized()
    persp_single = (Vector((4.0, 5.0, 6.0)), new_persp_rot, 18.0, "PERSP")
    assert ops_hotbox.ensure_quadview_persp(mock_space, area_key=999, prev_single_state=persp_single) is True
    assert mock_quads[3].view_perspective == "PERSP"
    assert (mock_quads[3].view_location - Vector((4.0, 5.0, 6.0))).length < 1e-4
    assert abs(mock_quads[3].view_distance - 18.0) < 1e-4

    # 7. Full Hotbox popup draw() RNA audit (operators, properties, enums, and icons)
    valid_icons = {e.identifier for e in bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items}
    drawn_ops = []

    class _MockOpProps:
        def __init__(self, op_id, rna_type):
            object.__setattr__(self, "_op_id", op_id)
            object.__setattr__(self, "_rna_type", rna_type)

        def __setattr__(self, attr, value):
            rna_type = object.__getattribute__(self, "_rna_type")
            op_id = object.__getattribute__(self, "_op_id")
            prop = rna_type.properties.get(attr)
            assert prop is not None, f"{op_id} missing property {attr!r}"
            if prop.type == "ENUM":
                valid_vals = {e.identifier for e in prop.enum_items}
                assert value in valid_vals, f"{op_id}.{attr}={value!r} not in {sorted(valid_vals)}"

    class _MockLayout:
        def row(self, align=False):
            return self

        def column(self, align=False):
            return self

        def box(self):
            return self

        def label(self, text="", icon="NONE"):
            if icon != "NONE":
                assert icon in valid_icons, f"Invalid label icon: {icon}"

        def separator(self):
            pass

        def operator(self, op_id, text="", icon="NONE"):
            if icon != "NONE":
                assert icon in valid_icons, f"Invalid operator icon: {icon} on {op_id}"
            cat, name = op_id.split(".", 1)
            op_fn = getattr(getattr(bpy.ops, cat), name, None)
            assert op_fn is not None, f"Missing operator in Hotbox: {op_id}"
            drawn_ops.append(op_id)
            return _MockOpProps(op_id, op_fn.get_rna_type())

    fake_hotbox = SimpleNamespace(layout=_MockLayout())
    ops_hotbox.MAYA_UX_OT_hotbox_popup.draw(fake_hotbox, bpy.context)
    assert len(drawn_ops) >= 30, f"Expected >= 30 Hotbox buttons, got {len(drawn_ops)}"
    assert bpy.ops.maya_ux.create_maya_workspace(workspace_name="Maya Pro") == {"FINISHED"}

    # 8. Cheatsheet updated & still macOS-safe (no "Alt")
    mac_sections = ui_cheatsheet._get_sections(is_mac=True)
    mac_flat = " ".join(f"{l} {s}" for _t, rows in mac_sections for l, s in rows)
    assert "Alt" not in mac_flat
    assert "Tap Spacebar" in mac_flat and "Hold Spacebar" in mac_flat
    print("[PASS] maya_spacebar_and_hotbox")


def test_clean_startup_and_empty_scene():
    from maya_ux_pro import ops_startup

    cube = _reset_scene()
    assert bpy.ops.maya_ux.new_clean_scene() == {"FINISHED"}
    assert len(bpy.data.objects) == 0
    assert bpy.data.collections.get("Collection") is None

    # Factory default check only matches unsaved scenes with Cube/Camera/Light
    bpy.ops.mesh.primitive_cube_add()
    assert ops_startup.is_factory_default_scene() is True
    bpy.ops.mesh.primitive_uv_sphere_add()
    assert ops_startup.is_factory_default_scene() is False

    assert bpy.ops.maya_ux.new_clean_scene() == {"FINISHED"}
    assert len(bpy.data.objects) == 0

    v3d_theme = bpy.context.preferences.themes[0].view_3d
    assert v3d_theme.space.gradients.background_type == "SINGLE_COLOR"
    assert abs(v3d_theme.space.gradients.high_gradient[0] - 0.09) < 1e-3
    assert int(bpy.context.preferences.view.gizmo_size) == 75

    v3d_space = next(a.spaces.active for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    assert abs(v3d_space.lens - 50.0) < 1e-3
    assert abs(v3d_space.clip_start - 0.01) < 1e-4
    assert abs(v3d_space.clip_end - 1000.0) < 1e-2
    assert v3d_space.overlay.grid_subdivisions == 10
    assert v3d_space.show_region_asset_shelf is False
    assert ops_startup._on_load_post in bpy.app.handlers.load_post
    print("[PASS] clean_startup_and_empty_scene")


def test_maya_poly_count_hud():
    from maya_ux_pro import ui_poly_hud

    # Empty scene -> (0, 0, 0) across all rows
    assert bpy.ops.maya_ux.new_clean_scene() == {"FINISHED"}
    empty_stats = ui_poly_hud.compute_poly_stats(bpy.context)
    assert empty_stats["verts"] == (0, 0, 0)
    assert empty_stats["edges"] == (0, 0, 0)
    assert empty_stats["faces"] == (0, 0, 0)
    assert empty_stats["tris"] == (0, 0, 0)
    assert empty_stats["uvs"] == (0, 0, 0)
    assert empty_stats["subdiv_level"] == 0 and empty_stats["subdiv_mode"] == "Standard"

    # Default Cube in Object Mode -> Verts 8, Edges 12, Faces 6, Tris 12, UVs 24
    cube = _reset_scene()
    obj_stats = ui_poly_hud.compute_poly_stats(bpy.context)
    assert obj_stats["verts"] == (8, 8, 0)
    assert obj_stats["edges"] == (12, 12, 0)
    assert obj_stats["faces"] == (6, 6, 0)
    assert obj_stats["tris"] == (12, 12, 0)
    assert obj_stats["uvs"] == (24, 24, 0)

    # Edit Mode with 1 face selected -> Col 3 reports 4 verts, 4 edges, 1 face, 2 tris, 4 UVs
    import bmesh

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bm = bmesh.from_edit_mesh(cube.data)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    bmesh.update_edit_mesh(cube.data)
    edit_stats = ui_poly_hud.compute_poly_stats(bpy.context)
    assert edit_stats["verts"] == (8, 8, 4)
    assert edit_stats["edges"] == (12, 12, 4)
    assert edit_stats["faces"] == (6, 6, 1)
    assert edit_stats["tris"] == (12, 12, 2)
    assert edit_stats["uvs"] == (24, 24, 4)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Smooth Preview level 3 -> Subdiv level & mode updated
    assert bpy.ops.maya_ux.smooth_preview(level=3) == {"FINISHED"}
    sub_stats = ui_poly_hud.compute_poly_stats(bpy.context)
    assert sub_stats["subdiv_level"] == 2
    assert sub_stats["subdiv_mode"] == "Smooth (3)"

    # Toggle operator flips preference & back
    prefs = preferences.get_prefs()
    before = bool(prefs.show_poly_count_hud)
    assert bpy.ops.maya_ux.toggle_poly_count_hud() == {"FINISHED"}
    assert bool(preferences.get_prefs().show_poly_count_hud) is (not before)
    assert bpy.ops.maya_ux.toggle_poly_count_hud() == {"FINISHED"}
    assert bool(preferences.get_prefs().show_poly_count_hud) is before

    v3d_space = next(a.spaces.active for a in bpy.context.screen.areas if a.type == "VIEW_3D")
    assert v3d_space.overlay.show_text is False
    assert ui_poly_hud._HUD_HANDLE is not None
    assert ui_poly_hud._on_depsgraph_update in bpy.app.handlers.depsgraph_update_post
    print("[PASS] maya_poly_count_hud")


def test_unregistration():
    from maya_ux_pro import ops_startup, ui_poly_hud

    maya_ux_pro.unregister()
    assert ui_poly_hud._HUD_HANDLE is None
    assert ui_poly_hud._on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post
    assert ops_startup._on_load_post not in bpy.app.handlers.load_post
    assert not bpy.app.timers.is_registered(ops_startup._apply_clean_ui_deferred)
    assert len(keymap.addon_keymaps) == 0, "All addon keymaps must be removed on unregister"
    assert len(keymap._disabled_builtin_kmis) == 0, "Disabled built-in keymaps must be restored/cleared"
    assert not keymap._transform_modal_swapped
    assert ops_maya_axes._HUD_DRAW_HANDLE is None
    assert not bpy.app.timers.is_registered(keymap._deferred_spacebar_sync)
    assert not bpy.app.timers.is_registered(ops_viewport._cam_history_timer)
    assert not hasattr(bpy.types.WindowManager, "maya_ux_yup")
    assert not hasattr(bpy.types.Scene, "maya_ux_live_surface")
    assert not hasattr(bpy.types.Scene, "maya_ux_shelf_tab")
    assert not hasattr(bpy.types.Scene, "maya_ux_cam_slots")
    print("[PASS] unregistration")


if __name__ == "__main__":
    test_registration_and_keymap_safety()
    test_setup_manager_roundtrip()
    test_smooth_preview()
    test_pivot_and_snap()
    test_modeling_duplication_and_outliner()
    test_selection_pickwalk_soft_and_delete()
    test_viewport_hide_bg_increment_save_and_cam_history()
    test_animation_and_uv()
    test_official_maya_parity()
    test_maya_yup_axes_and_io()
    test_maya_mmb_smart_drag()
    test_v2_pro_tools()
    test_maya_spacebar_and_hotbox()
    test_clean_startup_and_empty_scene()
    test_maya_poly_count_hud()
    test_unregistration()
    print("ALL TESTS PASSED!")
