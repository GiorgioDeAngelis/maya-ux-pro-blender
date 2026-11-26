from __future__ import annotations

import bpy
from bpy.props import StringProperty

from .preferences import is_macos_layout, mod_label


def _get_sections(is_mac: bool):
    if is_mac:
        o = "⌥"
        c = "⌘"
        ct = "⌃"
        s = "⇧"
        dl = "⌫ Delete"
        nav = (
            ("Tumble (Orbit)", f"{o} Option + Click  |  2-Finger Drag"),
            ("Track (Pan)", f"MMB (Empty/Q) | {o}+MMB | {o}+{s}+Click"),
            ("Virtual Transform (Global/Last Axis)", "MMB Drag (Selected + W / E / R / T)"),
            ("Dolly (Zoom)", f"{o}+RMB  |  {o}+{ct}+Click  |  Pinch"),
            ("Select / Move / Rotate / Scale", "Q / W / E / R"),
            ("Universal Manipulator / Size +/-", "T  |  = / -"),
            ("Frame Selected / Frame All", "F / A  (⇧+F / ⇧+A all views)"),
            ("Shading: Wire / Solid / Tex / Light", "4 / 5 / 6 / 7  (0 = Default)"),
            ("Wireframe on Shaded / X-Ray", f"{o}+5 / {o}+X"),
            ("Isolate Select", f"{c}+1  |  {s}+I  (or {ct}+1)"),
            ("Expert Mode (Fullscreen)", f"{ct}+Space (All Editors, keeps {c}+Space)"),
            ("Toggle Channel Box / Cycle BG", f"{ct}+A / {o}+B"),
            ("Camera Undo / Redo", "[ / ]"),
        )
        vis = (
            ("Smart Hide / Hide / Unhide", f"H / {ct}+H / {s}+H  (keeps {c}+H macOS)"),
            ("Hide Unselected / Show Last", f"{o}+H / {ct}+{s}+H"),
            ("Component Marking Menu", "RMB"),
            ("Modeling Marking Menu", f"{s}+RMB"),
            ("Tap Spacebar (Pane / Quad)", "Maximize/Quad Pane under cursor"),
            ("Hold Spacebar (Hotbox)", f"Floating Maya Hotbox  |  {s}+Space View Pie"),
            ("Object / Vertex / Edge / Face", f"F8 Toggle | {o}+1/2/3/4"),
            ("Undo / Redo (Maya + macOS)", f"Z / {s}+Z / {c}+Y  (and {c}+Z)"),
            ("Repeat Last / Increment Save", f"G or Y / {c}+{o}+S"),
            ("Hotkey Reference", "?  (or Fn+F1)"),
        )
        sel = (
            ("Grow / Shrink Selection", "> / <  (ISO <> or ⇧+. / ⇧+,)"),
            ("Invert Selection", f"{c}+{s}+I"),
            ("Convert to Vert / Edge / Face", f"{ct}+F9 / F10 / F11"),
            ("Pick Walk (Parent/Child/Siblings)", "↑ / ↓ / ← / →"),
            ("Nudge Screen-Space", f"{o}+↑ / ↓ / ← / →"),
            ("Soft Select / Radius -/+", f"B / {s}+[ / {s}+]"),
            ("Smart Delete Edge (Keep/Del Verts)", f"{dl} / {c}+{dl}"),
        )
        mod = (
            ("Edit Pivot / Pivot Pie", f"Hold D (D+V/C/X Snap) / {o}+D"),
            ("Snap: Grid / Edge / Vert / Step", "Hold X / C / V / J  (⇧+J Relative)"),
            ("Smooth Preview (Rough/Cage/Smooth)", "1 / 2 / 3  (PgUp/PgDn +/-)"),
            ("Dup In-Place / +Transform / Special", f"{c}+D / {s}+D / {c}+{s}+D"),
            ("Delete History", f"{o}+{s}+D"),
            ("Group / Parent / Unparent", f"{c}+G / P / {s}+P"),
            ("Extrude / Bevel / Multi-Cut", f"{c}+E / {c}+B / {c}+{s}+X"),
            ("Bridge / Merge Menu / Reverse Normals", f"{c}+{s}+B / M ({c}+{o}+M) / {o}+N"),
            ("Target Weld / Quad Draw / Make Live", "Shift+RMB / Maya Panel / Top Shelf"),
        )
        anim = (
            ("Set Keyframe (All / Loc / Rot / Scale)", f"S / {s}+W / {s}+E / {s}+R"),
            ("Play / Go to Min Frame / AutoKey", f"{o}+V / {o}+{s}+V / {o}+K"),
            ("Prev/Next Keyframe | Frame", f", / .  |  {o}+, / {o}+."),
            ("Graph: Lin / Auto / Step / Spline / Pie", f"1 / 2 / 3 / 4 / T  ({o}+I Key)"),
        )
        uv = (
            ("UV Marking Menu / Tools", "RMB / Q, W, E, R"),
            ("Select Shell / Grow / Shrink", f"{c}+F12 / > / <"),
            ("Cut Seams / Stitch / Unfold / Layout", f"{s}+X / {s}+S / {c}+U / {c}+L"),
        )
    else:
        nav = (
            ("Tumble / Track / Dolly", "Alt + LMB / MMB / RMB"),
            ("Smart MMB (Pan or Virtual Drag)", "MMB (Empty/Q = Pan, W/E/R = Transform)"),
            ("Select / Move / Rotate / Scale", "Q / W / E / R"),
            ("Universal Manipulator / Size +/-", "T  |  = / -"),
            ("Frame Selected / Frame All", "F / A  (Shift+F / A all views)"),
            ("Shading: Wire / Solid / Tex / Light", "4 / 5 / 6 / 7  (0 = Default)"),
            ("Wireframe on Shaded / X-Ray", "Alt+5 / Alt+X"),
            ("Isolate Select", "Ctrl+1  |  Shift+I"),
            ("Expert Mode (Fullscreen)", "Ctrl + Space (All Editors)"),
            ("Toggle Channel Box / Cycle BG", "Ctrl+A / Alt+B"),
            ("Camera Undo / Redo", "[ / ]"),
        )
        vis = (
            ("Smart Hide / Hide / Unhide", "H / Ctrl+H / Shift+H"),
            ("Hide Unselected / Show Last", "Alt+H / Ctrl+Shift+H"),
            ("Component Marking Menu", "RMB"),
            ("Modeling Marking Menu", "Shift + RMB"),
            ("Tap Spacebar (Pane / Quad)", "Maximize/Quad Pane under cursor"),
            ("Hold Spacebar (Hotbox)", "Floating Maya Hotbox  |  Shift+Space View Pie"),
            ("Object / Vertex / Edge / Face", "F8 Toggle | F9 / F10 / F11"),
            ("Undo / Redo", "Z / Shift+Z / Ctrl+Y  (Ctrl+Z)"),
            ("Repeat Last / Increment Save", "G or Y / Ctrl+Alt+S"),
            ("Hotkey Reference", "?  or  F1"),
        )
        sel = (
            ("Grow / Shrink Selection", "> / <  (ISO <> or Shift+. / Shift+,)"),
            ("Invert Selection", "Ctrl + Shift + I"),
            ("Convert to Vert / Edge / Face", "Ctrl+F9 / F10 / F11"),
            ("Pick Walk (Parent/Child/Siblings)", "Up / Down / Left / Right"),
            ("Nudge Screen-Space", "Alt + Up / Down / Left / Right"),
            ("Soft Select / Radius -/+", "B / Shift+[ / Shift+]"),
            ("Smart Delete Edge (Keep/Del Verts)", "Backspace / Ctrl+Backspace"),
        )
        mod = (
            ("Edit Pivot / Pivot Pie", "Hold D (D+V/C/X Snap) / Alt+D"),
            ("Snap: Grid / Edge / Vert / Step", "Hold X / C / V / J  (Shift+J Rel)"),
            ("Smooth Preview (Rough/Cage/Smooth)", "1 / 2 / 3  (PgUp/PgDn +/-)"),
            ("Dup In-Place / +Transform / Special", "Ctrl+D / Shift+D / Ctrl+Shift+D"),
            ("Delete History", "Alt + Shift + D"),
            ("Group / Parent / Unparent", "Ctrl+G / P / Shift+P"),
            ("Extrude / Bevel / Multi-Cut", "Ctrl+E / Ctrl+B / Ctrl+Shift+X"),
            ("Bridge / Merge Menu / Reverse Normals", "Ctrl+Shift+B / M (Ctrl+Alt+M) / Alt+N"),
            ("Target Weld / Quad Draw / Make Live", "Shift+RMB / Maya Panel / Top Shelf"),
        )
        anim = (
            ("Set Keyframe (All / Loc / Rot / Scale)", "S / Shift+W / E / R"),
            ("Play / Go to Min Frame / AutoKey", "Alt+V / Alt+Shift+V / Alt+K"),
            ("Prev/Next Keyframe | Frame", ", / .  |  Alt+, / Alt+."),
            ("Graph: Lin / Auto / Step / Spline / Pie", "1 / 2 / 3 / 4 / T  (Alt+I Key)"),
        )
        uv = (
            ("UV Marking Menu / Tools", "RMB / Q, W, E, R"),
            ("Select Shell / Grow / Shrink", "Ctrl+F12 / > / <"),
            ("Cut Seams / Stitch / Unfold / Layout", "Shift+X / Shift+S / Ctrl+U / Ctrl+L"),
        )

    return (
        ("Navigation & Viewport", nav),
        ("Visibility & Marking Menus", vis),
        ("Selection, Pick Walk & Soft Select", sel),
        ("Pivot, Snap, Smooth & Modeling", mod),
        ("Animation & Graph Editor", anim),
        ("UV Editor (Maya Style)", uv),
    )


def filter_sections(is_mac: bool, query: str = ""):
    """Filter Maya->Blender hotkey sections by search query (Hotkey Equivalence)."""
    sections = _get_sections(is_mac)
    q = (query or "").strip().lower()
    if not q:
        return sections

    filtered = []
    for title, items in sections:
        if q in title.lower():
            filtered.append((title, items))
            continue
        matched = tuple((lbl, sc) for lbl, sc in items if q in lbl.lower() or q in sc.lower())
        if matched:
            filtered.append((title, matched))
    return tuple(filtered)


class MAYA_UX_OT_cheatsheet(bpy.types.Operator):
    """Display the searchable Maya UX Pro Hotkey Reference & Equivalence popup (? / F1)."""

    bl_idname = "maya_ux.cheatsheet"
    bl_label = "Maya UX Pro — Hotkey Reference & Equivalence"

    search: StringProperty(
        name="Search",
        description="Filter Maya or Blender commands",
        default="",
        options={"TEXTEDIT_UPDATE"},
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=800)

    def draw(self, context):
        layout = self.layout
        is_mac = is_macos_layout(context)
        if is_mac:
            header = layout.box()
            header.label(
                text="macOS / MacBook Pro Active — ⌥ Option = Maya Alt  |  ⌘ Cmd / ⌃ Ctrl Safe Layout",
                icon="DESKTOP",
            )

        search_row = layout.row(align=True)
        search_row.prop(self, "search", text="", icon="VIEWZOOM")

        sections = filter_sections(is_mac, self.search)
        if not sections:
            layout.label(text=f"No shortcuts matching '{self.search}'", icon="INFO")
            return

        cols = layout.row()
        left_col = cols.column()
        right_col = cols.column()

        half = (len(sections) + 1) // 2
        for idx, (title, items) in enumerate(sections):
            target_col = left_col if idx < half else right_col
            box = target_col.box()
            box.label(text=title, icon="KEYINGSET")
            for action_label, shortcut in items:
                row = box.row()
                split = row.split(factor=0.56)
                split.label(text=action_label)
                split.label(text=shortcut)

    def execute(self, context):
        return {"FINISHED"}


CLASSES = (MAYA_UX_OT_cheatsheet,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
