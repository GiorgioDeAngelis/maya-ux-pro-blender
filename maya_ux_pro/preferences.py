from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty


def _on_pref_update(self, context):
    from . import keymap

    keymap.rebuild_keymaps()


def _on_zoom_pref_update(self, context):
    ctx = context or bpy.context
    prefs_root = getattr(ctx, "preferences", None)
    if prefs_root is not None:
        prefs_root.inputs.invert_mouse_zoom = bool(self.maya_invert_mouse_zoom)


def _on_axis_color_update(self, context):
    from . import keymap, ops_maya_axes

    ops_maya_axes.apply_maya_axis_colors(bool(self.swap_axis_colors_yup), context)
    keymap.rebuild_keymaps()


def _on_yup_hud_update(self, context):
    from . import keymap, ops_maya_axes

    ops_maya_axes.sync_viewport_yup_gizmo(bool(self.show_maya_yup_hud), context)
    keymap.rebuild_keymaps()


def _on_hud_redraw(self, context):
    from . import ui_poly_hud

    ui_poly_hud.sync_viewport_text_overlay(bool(self.show_poly_count_hud), context)


def _on_face_center_update(self, context):
    from . import keymap, ops_selection

    ops_selection.sync_face_center_overlay(bool(self.maya_face_center_select), context)
    keymap.rebuild_keymaps()


def is_macos_layout(context=None) -> bool:
    """Return True when macOS / MacBook Pro keyboard & Trackpad layout is active."""
    prefs = get_prefs(context)
    layout = getattr(prefs, "keyboard_layout", "AUTO")
    if layout == "MACOS":
        return True
    if layout == "WIN_LINUX":
        return False
    return sys.platform == "darwin"


def mod_label(context=None) -> dict[str, str]:
    """Return platform-appropriate modifier key labels (never 'Alt' on macOS)."""
    if is_macos_layout(context):
        return {
            "alt": "⌥ Option",
            "alt_short": "⌥",
            "cmd": "⌘ Cmd",
            "cmd_short": "⌘",
            "ctrl": "⌃ Ctrl",
            "ctrl_short": "⌃",
            "shift": "⇧ Shift",
            "shift_short": "⇧",
            "del": "⌫ Delete",
        }
    return {
        "alt": "Alt",
        "alt_short": "Alt",
        "cmd": "Ctrl",
        "cmd_short": "Ctrl",
        "ctrl": "Ctrl",
        "ctrl_short": "Ctrl",
        "shift": "Shift",
        "shift_short": "Shift",
        "del": "Backspace",
    }


class MayaUXPreferences(bpy.types.AddonPreferences):
    """Preferences for Maya UX Pro modular keymaps and workflow behavior."""

    bl_idname = __package__

    keyboard_layout: EnumProperty(
        name="Keyboard & Platform Profile",
        description="Choose macOS / MacBook Pro (⌥ Option, ⌘ Cmd, Trackpad) or Windows/Linux labels and bindings",
        items=[
            ("AUTO", "Auto-Detect (macOS / Win)", "Automatically use macOS / MacBook Pro layout on Mac"),
            ("MACOS", "macOS / MacBook Pro (⌥ Option, ⌘ Cmd)", "Use Apple ⌥ Option, ⌘ Cmd, ⌃ Ctrl, and MacBook Trackpad navigation"),
            ("WIN_LINUX", "Windows / Linux (Alt, Ctrl)", "Use Windows/Linux Alt and Ctrl conventions"),
        ],
        default="AUTO",
        update=_on_pref_update,
    )
    enable_mac_trackpad_nav: BoolProperty(
        name="MacBook Trackpad & No-MMB Maya Nav",
        description="Enable ⌥+Click Orbit, ⌥+⇧+Click Pan, ⌥+⌃+Click Zoom, and native Trackpad gestures",
        default=True,
        update=_on_pref_update,
    )
    enable_maya_mmb_drag: BoolProperty(
        name="Maya Smart MMB (Pan / Transform Drag)",
        description="Bare MMB pans when nothing selected or in Select tool, and moves/rotates/scales globally or along last active gizmo axis when transforming",
        default=True,
        update=_on_pref_update,
    )
    maya_invert_mouse_zoom: BoolProperty(
        name="Invert Mouse Zoom (Pull Back = Zoom In)",
        description="Match Maya zoom direction: dragging mouse backward/down zooms closer",
        default=True,
        update=_on_zoom_pref_update,
    )
    channel_box_yup: BoolProperty(
        name="Channel Box Y-Up (Maya Coordinates)",
        description="Display and edit Channel Box Translate/Rotate/Scale with Y as vertical Up axis (optional UI mode)",
        default=False,
        update=_on_pref_update,
    )
    swap_axis_colors_yup: BoolProperty(
        name="Maya Y-Up Axis Colors (Green Up / Blue Depth)",
        description="Optional: swap Viewport Y/Z axis colors and Y/Z transform modal keys (Y = Up, Z = Depth)",
        default=False,
        update=_on_axis_color_update,
    )
    show_maya_yup_hud: BoolProperty(
        name="Maya Y-Up Axis Tripod (Hide Z-Up Gizmo)",
        description="Optional: draw Maya Y-Up (X Red, Y Green Up, Z Blue Forward) viewport tripod and hide Blender's Z-Up navigation gizmo",
        default=False,
        update=_on_yup_hud_update,
    )
    clean_empty_new_scene: BoolProperty(
        name="Empty New Scene (No Cube/Camera/Light)",
        description="Automatically clear factory Cube, Camera, and Light when opening File -> New",
        default=True,
    )
    clean_maya_startup_layout: BoolProperty(
        name="Clean 3-Pane Dark Viewport UI",
        description="Apply the clean charcoal 3-pane Maya viewport layout (no bottom timeline) on new scenes and setup",
        default=True,
    )

    # Modular feature toggles
    enable_viewport_keys: BoolProperty(
        name="Core UX & Viewport Keys",
        description="Enable Q/W/E/R smart gizmo, +/- gizmo size, 4/5/6/7 shading, Isolate, Hide, F8-F11 / ⌥+1-4, ? / F1 cheatsheet",
        default=True,
        update=_on_pref_update,
    )
    enable_marking_menus: BoolProperty(
        name="Maya Marking Menus",
        description="Enable RMB Component Pie, Shift+RMB Modeling Pie, and Spacebar Quad/View Pie",
        default=True,
        update=_on_pref_update,
    )
    enable_pivot_snap: BoolProperty(
        name="Pivot & Snapping",
        description="Enable D (Edit Pivot), ⌥+D / Alt+D (Pivot Pie), and X/C/V (Grid/Edge/Vertex Snap)",
        default=True,
        update=_on_pref_update,
    )
    enable_smooth_preview: BoolProperty(
        name="Smooth Mesh Preview (1 / 2 / 3)",
        description="Map 1, 2, 3 to Maya Smooth Mesh Preview; disable to keep 1/2/3 as Component Mode switches",
        default=True,
        update=_on_pref_update,
    )
    enable_outliner_ops: BoolProperty(
        name="Modeling & Outliner Workflow",
        description="Enable Group (⌘+G / Ctrl+G), P / Shift+P Parent/Unparent, and G Repeat Last",
        default=True,
        update=_on_pref_update,
    )
    enable_selection_keys: BoolProperty(
        name="Selection, Pick Walk & Soft Select",
        description="Enable >/< Grow/Shrink, Convert Selection, B Soft Select, Smart Delete, Arrow Pick Walk",
        default=True,
        update=_on_pref_update,
    )
    enable_modeling_keys: BoolProperty(
        name="Maya Modeling & Duplication",
        description="Enable Duplicate In-Place, Dup+Transform, Dup Special, J Discrete, Extrude/Bevel/Multi-Cut",
        default=True,
        update=_on_pref_update,
    )
    enable_animation_keys: BoolProperty(
        name="Animation, Timeline & Graph Editor",
        description="Enable S/Shift+W/E/R Keyframes, Play, ,/. Keys, Frame step, Graph Tangents 1-4 & T",
        default=True,
        update=_on_pref_update,
    )
    enable_uv_keys: BoolProperty(
        name="UV Editor (Maya Style)",
        description="Enable RMB UV Marking Menu, QWER UV tools, Cut Seams, Stitch, Unfold, Layout",
        default=True,
        update=_on_pref_update,
    )
    enable_maya_z_undo: BoolProperty(
        name="Z / Shift+Z Undo & Redo",
        description="Bind Z to Undo and Shift+Z to Redo in 3D Viewport (⌘+Z always remains active)",
        default=True,
        update=_on_pref_update,
    )
    enable_pick_walk_arrows: BoolProperty(
        name="Arrow Keys = Pick Walk",
        description="Use Up/Down/Left/Right arrows for hierarchy Pick Walk instead of frame stepping",
        default=True,
        update=_on_pref_update,
    )
    show_top_shelf: BoolProperty(
        name="Show Top Viewport Shelf",
        description="Display compact Maya quick-action shelf in the 3D Viewport header",
        default=True,
    )
    show_poly_count_hud: BoolProperty(
        name="Maya Poly Count HUD",
        description="Display Maya-style Poly Count & Subdiv HUD in the top-left of the 3D Viewport",
        default=True,
        update=_on_hud_redraw,
    )

    # Behavioral options
    group_mode: EnumProperty(
        name="Group Mode (Ctrl+G)",
        description="How Ctrl+G groups selected objects",
        items=[
            ("EMPTY", "Maya Null Group (Empty)", "Parent selection under a new Empty object"),
            ("COLLECTION", "Blender Collection", "Move selection into a new Collection"),
        ],
        default="EMPTY",
    )
    group_pivot: EnumProperty(
        name="Group Pivot",
        description="Pivot placement for new Null Groups",
        items=[
            ("CENTER", "Selection Center", "Place group Empty at selection bounding center"),
            ("ORIGIN", "World Origin (0, 0, 0)", "Place group Empty at world origin"),
        ],
        default="CENTER",
    )
    rmb_trigger: EnumProperty(
        name="RMB Marking Menu Trigger",
        description="How Right Mouse Button triggers the Component Marking Menu",
        items=[
            ("PRESS", "Instant Press (Maya Style)", "Open Marking Menu immediately on RMB press"),
            ("CLICK_DRAG", "Click-Drag (Keep Blender Click Menu)", "Open Marking Menu on RMB drag, keep native context menu on click"),
        ],
        default="PRESS",
        update=_on_pref_update,
    )
    spacebar_mode: EnumProperty(
        name="Spacebar Mode",
        description="Behavior of Spacebar across editors and 3D Viewport",
        items=[
            ("HYBRID", "Hybrid (Tap=Pane/Quad, Hold=Hotbox)", "Tap Space to maximize/quad pane under cursor, hold Space for Maya Hotbox"),
            ("QUAD_ONLY", "Pane / Quad View Only", "Tap Space toggles 4-way Quad View or maximizes pane under cursor"),
            ("VIEW_PIE_ONLY", "View Pie Only", "Space opens orthographic/camera View Pie"),
            ("DISABLED", "Blender Default", "Do not override Spacebar"),
        ],
        default="HYBRID",
        update=_on_pref_update,
    )
    hotbox_hold_delay: FloatProperty(
        name="Hotbox Hold Delay (s)",
        description="Seconds to hold Spacebar before opening the Floating Maya Hotbox",
        default=0.20,
        min=0.08,
        max=0.60,
        step=2,
    )
    smooth_preview_levels: IntProperty(
        name="Smooth Preview Subdivisions",
        description="Target viewport subdivision levels for Smooth Preview level 3",
        default=2,
        min=1,
        max=4,
    )
    snap_hold_mode: EnumProperty(
        name="Snap Key Behavior (X / C / V / J)",
        description="Whether X/C/V/J snap keys act while held (Maya) or toggle on tap",
        items=[
            ("HOLD", "Hold Key (Maya Native)", "Hold X/C/V/J to snap, release to restore previous snap state"),
            ("TOGGLE", "Tap Toggle", "Tap X/C/V/J to toggle snap on/off"),
        ],
        default="HOLD",
        update=_on_pref_update,
    )
    pivot_hold_mode: EnumProperty(
        name="Edit Pivot Key Behavior (D)",
        description="Whether D enters Edit Pivot while held (Maya D+V/C/X) or toggles on tap",
        items=[
            ("HOLD", "Hold Key (Maya Native)", "Hold D to edit pivot (works with D+V/C/X), release to exit"),
            ("TOGGLE", "Tap Toggle", "Tap D to toggle Edit Pivot on/off"),
        ],
        default="HOLD",
        update=_on_pref_update,
    )
    maya_face_center_select: BoolProperty(
        name="Maya Face Center-Only Selection",
        description="Display center handles on faces and select faces only by clicking their center dot",
        default=True,
        update=_on_face_center_update,
    )
    face_center_hit_radius: FloatProperty(
        name="Face Center Hit Radius (px)",
        description="Click radius in pixels around a face's center handle",
        default=10.0,
        min=4.0,
        max=28.0,
        step=50,
    )
    ortho_select_through: BoolProperty(
        name="Orthographic Select-Through (Shaded)",
        description="Select front and hidden back components (Verts/Edges/Faces) in Orthographic views even in Solid/Shaded mode, like Wireframe and Maya",
        default=True,
        update=_on_pref_update,
    )

    def draw(self, context):
        layout = self.layout
        setup_manager = importlib.import_module(f"{__package__}.setup_manager")

        # 1-Click Base Setup box
        box = layout.box()
        box.label(text="1-Click Maya Base Setup (Reversible)", icon="PREFERENCES")
        wm = context.window_manager
        active_kc = wm.keyconfigs.active.name if wm and wm.keyconfigs.active else "Unknown"
        has_bk = setup_manager.has_backup()

        info_row = box.row()
        info_row.label(text=f"Active Keyconfig: {active_kc}")
        info_row.label(text=f"Backup Saved: {'Yes' if has_bk else 'No'}")

        btn_row = box.row(align=True)
        btn_row.scale_y = 1.3
        btn_row.operator("maya_ux.apply_maya_setup", text="Apply Maya Base Setup", icon="CHECKMARK")
        sub = btn_row.row(align=True)
        sub.enabled = has_bk
        sub.operator("maya_ux.restore_previous_setup", text="Restore Previous Setup", icon="LOOP_BACK")
        box.operator("maya_ux.save_clean_startup", text="Save Clean Empty Startup File", icon="FILE_NEW")

        # Platform Profile
        plat_box = layout.box()
        active_profile = "macOS / MacBook Pro (⌥ Option, ⌘ Cmd, Trackpad)" if is_macos_layout(context) else "Windows / Linux (Alt, Ctrl)"
        plat_box.label(text=f"Keyboard Profile: {active_profile}", icon="DESKTOP")
        plat_box.prop(self, "keyboard_layout")
        if is_macos_layout(context):
            plat_box.prop(self, "enable_mac_trackpad_nav")
        plat_box.prop(self, "enable_maya_mmb_drag")
        plat_box.prop(self, "maya_invert_mouse_zoom")
        plat_box.prop(self, "channel_box_yup")
        plat_box.prop(self, "swap_axis_colors_yup")
        plat_box.prop(self, "show_maya_yup_hud")
        plat_box.operator("maya_ux.apply_maya_grid_theme", text="Apply Maya Grid & Viewport Theme", icon="GRID")

        # Modules
        mod_box = layout.box()
        mod_box.label(text="Active Modules", icon="MODIFIER")
        col = mod_box.column(align=True)
        col.prop(self, "enable_viewport_keys")
        col.prop(self, "enable_marking_menus")
        col.prop(self, "enable_pivot_snap")
        col.prop(self, "enable_smooth_preview")
        col.prop(self, "enable_outliner_ops")
        col.prop(self, "enable_selection_keys")
        col.prop(self, "enable_modeling_keys")
        col.prop(self, "enable_animation_keys")
        col.prop(self, "enable_uv_keys")
        col.separator()
        col.prop(self, "enable_maya_z_undo")
        col.prop(self, "enable_pick_walk_arrows")
        col.prop(self, "show_top_shelf")
        col.prop(self, "show_poly_count_hud")

        # Behavioral options
        beh_box = layout.box()
        beh_box.label(text="Workflow Options", icon="TOOL_SETTINGS")
        beh_box.prop(self, "group_mode")
        if self.group_mode == "EMPTY":
            beh_box.prop(self, "group_pivot")
        beh_box.prop(self, "rmb_trigger")
        beh_box.prop(self, "spacebar_mode")
        if self.spacebar_mode == "HYBRID":
            beh_box.prop(self, "hotbox_hold_delay")
        beh_box.prop(self, "smooth_preview_levels")
        beh_box.prop(self, "snap_hold_mode")
        beh_box.prop(self, "pivot_hold_mode")
        beh_box.prop(self, "maya_face_center_select")
        if self.maya_face_center_select:
            beh_box.prop(self, "face_center_hit_radius")
        beh_box.prop(self, "ortho_select_through")
        beh_box.prop(self, "clean_empty_new_scene")
        beh_box.prop(self, "clean_maya_startup_layout")

        # Cheatsheet
        hk_lbl = "Open Maya UX Pro Hotkey Reference (? or F1)" if is_macos_layout(context) else "Open Maya UX Pro Hotkey Reference (F1)"
        layout.operator("maya_ux.cheatsheet", text=hk_lbl, icon="HELP")


_DEFAULT_PREFS = SimpleNamespace(
    keyboard_layout="AUTO",
    enable_mac_trackpad_nav=True,
    enable_maya_mmb_drag=True,
    maya_invert_mouse_zoom=True,
    channel_box_yup=False,
    swap_axis_colors_yup=False,
    show_maya_yup_hud=False,
    clean_empty_new_scene=True,
    clean_maya_startup_layout=True,
    enable_viewport_keys=True,
    enable_marking_menus=True,
    enable_pivot_snap=True,
    enable_smooth_preview=True,
    enable_outliner_ops=True,
    enable_selection_keys=True,
    enable_modeling_keys=True,
    enable_animation_keys=True,
    enable_uv_keys=True,
    enable_maya_z_undo=True,
    enable_pick_walk_arrows=True,
    show_top_shelf=True,
    show_poly_count_hud=True,
    group_mode="EMPTY",
    group_pivot="CENTER",
    rmb_trigger="PRESS",
    spacebar_mode="HYBRID",
    hotbox_hold_delay=0.20,
    smooth_preview_levels=2,
    snap_hold_mode="HOLD",
    pivot_hold_mode="HOLD",
    maya_face_center_select=True,
    face_center_hit_radius=10.0,
    ortho_select_through=True,
)


def get_prefs(context=None):
    """Return addon preferences instance or safe default proxy when running standalone."""
    ctx = context or bpy.context
    prefs_root = getattr(ctx, "preferences", None)
    if prefs_root is not None:
        addon = prefs_root.addons.get(__package__)
        if addon is not None and addon.preferences is not None:
            return addon.preferences
    return _DEFAULT_PREFS


CLASSES = (MayaUXPreferences,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
