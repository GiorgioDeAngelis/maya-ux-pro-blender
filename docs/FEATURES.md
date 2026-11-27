# Maya UX Pro — Features & Module Architecture (`v2.8.2`)

Maya UX Pro is organized into **26 cleanly modular Python files** inside `maya_ux_pro/`. Every module can be toggled or configured in **Preferences → Extensions / Add-ons → Maya UX Pro**.

---

## 1. Setup Manager & Reversible Backup ([`setup_manager.py`](../maya_ux_pro/setup_manager.py), [`preferences.py`](../maya_ux_pro/preferences.py))
- **1-Click Apply Maya Base Setup (`maya_ux.apply_maya_setup`)**:
  - Snapshots your existing active keyconfig, zoom preferences (`invert_mouse_zoom`, `view_zoom_method`, `view_zoom_axis`), orbit/zoom behavior (`use_rotate_around_active`, `use_zoom_to_mouse`), snap flags, gizmo size, viewport theme colors, and clean UI state to `maya_ux_pro_backup.json` inside Blender's `CONFIG` folder.
  - Activates Blender's built-in *Industry Compatible* keyconfig as a base layer, sets inverted Maya mouse zoom (`DOLLY` + `VERTICAL`), disables conflicting 3-button mouse emulation on macOS, and applies the clean 3-pane Maya viewport.
- **Restore Previous Setup (`maya_ux.restore_previous_setup`)**:
  - Reverts every backed-up setting and removes the backup file cleanly.

---

## 2. Spacebar & Floating Maya Hotbox ([`ops_hotbox.py`](../maya_ux_pro/ops_hotbox.py))
- **Modal Tap vs Hold (`maya_ux.spacebar_maya`)**:
  - Bound across `3D View`, `Frames`, and `Screen` with Blender's bare-`Space` timeline playback disabled automatically (while keeping `⌥+V` for playback).
  - Automatically passes through in `TEXT_EDITOR`, `CONSOLE`, `EDIT_TEXT`, and temporary popup regions.
  - **Tap (`< hotbox_hold_delay`, default `0.20s`, without `>= 14px` drag)**:
    - In **3D View**: toggles Quad View; when collapsing from 4-View, detects the quadrant under the cursor (`pick_quadview_index`) and restores that view's exact location/rotation/distance/perspective into the single viewport. When entering 4-View, `ensure_quadview_persp()` ensures the top-right user pane (`quads[3]`) is always unlocked **Perspective (`PERSP`)** and restores your last saved Persp camera.
    - In **Outliner, Properties, UV/Image, Graph, Dopesheet, Node Editor, NLA, Sequencer, Spreadsheet, Clip, File/Asset Browser**: maximizes/restores the hovered pane cleanly (`screen_full_area`).
  - **Hold (`>= 0.20s` or drag `>= 14px`)**: opens **`maya_ux.hotbox_popup`** — a 5-zone Floating Maya Hotbox with File/Edit/Display menus, Modes & Retopo, Maya Camera Views (`Persp`, `Top`, `Front`, `Side`, `Back`, `Left`, `Camera`), Modeling & Pivot, Smooth Preview, Materials/Lighting, Channel Box, and Workspace switching.

---

## 3. Smart MMB & Maya Viewport Tools ([`ops_viewport.py`](../maya_ux_pro/ops_viewport.py))
- **`maya_ux.mmb_smart_drag`**:
  - Empty selection or active `Q` (Select Box) → **Pan** (`view3d.move`).
  - Active `W` / `E` / `R` / `T` with selected **Objects**, **Edit Mesh Vertices/Edges/Faces**, **Curve points**, **Armature bones**, or **Pose bones** → transforms globally or constrained to the last gizmo axis (or explicit `MMB` axis lock buttons in `N → Maya`).
  - Inherits Object Mode's transform tool automatically when switching into Edit Mode (`F8..F11`, RMB menu, or `Tab`) until you press `Q`.
  - When Snapping (`V`/`C`/`X`) is held, enables `use_snap_self=True` in Edit Mode so vertices/edges snap cleanly onto the same mesh or background objects.
- **Viewport Controls**: `maya_ux.set_tool` (+ Maya Center Global Scale cube `VIEW3D_GGT_maya_center_scale` active in `R` Scale mode), `maya_ux.gizmo_size` (`=`/`-`), `maya_ux.set_shading` (`4/5/6/7`), `maya_ux.toggle_wireframe_on_shaded` (`⌥+5`), `maya_ux.toggle_xray` (`⌥+X`), `maya_ux.isolate_select`, `maya_ux.smart_hide` (`H` / `⌃+H` / `⇧+H` / `⌥+H` / `⌃+⇧+H`), `maya_ux.camera_view_undo`/`redo` (`[`/`]`), `maya_ux.increment_save`, `maya_ux.screen_nudge` (`⌥+Arrows`).

---

## 4. Pivot Editing & Hold-Snapping ([`ops_pivot_snap.py`](../maya_ux_pro/ops_pivot_snap.py))
- **`Hold D`** (`maya_ux.maya_pivot_hold`): enters Edit Pivot (`use_transform_data_origin = True`) while held and exits on release; pairs directly with **`D+V`** (Vertex), **`D+C`** (Edge), and **`D+X`** (Grid) to snap an object's pivot precisely.
- **`Hold X` / `C` / `V` / `J`** (`maya_ux.maya_snap_hold`): temporarily enables Grid / Edge / Vertex / Discrete increment snap while held and restores your exact previous snap settings on release.
- **`maya_ux.pivot_action`**: 1-click *Center Pivot*, *World Origin*, *Bottom Center*, *Match Active*, and *Bake Pivot*.

---

## 5. Face Center-Only Selection & Modeling Selection ([`ops_selection.py`](../maya_ux_pro/ops_selection.py))
- **`maya_ux.select_face_center` & `sync_face_center_overlay()`**:
  - Enables `overlay.show_face_center = True` and `facedot_size = 5`.
  - In pure Face Select Mode (`(False, False, True)`), `LMB Click` / `⇧+Click` / `⌃+Click` picks faces **strictly** within `face_center_hit_radius` (`10px` default) of the projected face center handle, respecting depth and front-face/raycast occlusion (or selecting through in `X-Ray`/`Wireframe`).
- **`maya_ux.convert_selection`** (`⌃+F9/F10/F11`), **`maya_ux.edge_loop_double_click`** (`LMB Double-Click` / `⇧+Double-Click` / `⌃+Double-Click` in Edge & Multi-Component modes), **`maya_ux.pick_walk`** (`↑↓←→`), **`maya_ux.toggle_soft_select`** (`B` + `⇧+[/]`), **`maya_ux.smart_delete`** (`⌫ Delete` dissolves interior edges keeping vertices; `⌘+⌫ Delete` removes vertices).

---

## 6. Maya Poly Count & Subdiv HUD ([`ui_poly_hud.py`](../maya_ux_pro/ui_poly_hud.py))
- Real-time `blf` viewport overlay showing Maya's 3-column counts (**All Visible \| Selected Objects \| Selected Components**) for `Verts`, `Edges`, `Faces`, `Tris`, `UVs` plus `Subdiv current level` and `Subdiv mode`.
- Automatically hides Blender's overlapping top-left Text Info (`User Perspective / Cube`) and skips duplicate drawing in 4-pane Quad View.
- Throttled + cached via `depsgraph_update_post` so viewport navigation stays silky-smooth.

---

## 7. Top Shelf, Channel Box & Clean Startup ([`ui_shelf.py`](../maya_ux_pro/ui_shelf.py), [`ui_channel_box.py`](../maya_ux_pro/ui_channel_box.py), [`ops_startup.py`](../maya_ux_pro/ops_startup.py))
- **Top Shelf**: 4 Menu Sets (`Display`, `Poly`, `Retopo`, `LookDev`) right in the 3D View header with live `EDIT PIVOT`, `LIVE`, and `HUD` buttons.
- **N-Panel (`N → Maya`)**:
  - *Channel Box* (Translate / Rotate / Scale + per-channel Lock toggles + vertex/edge/face stats)
  - *Pivot & Modeling* (`Freeze Transforms`, `Delete History`, `Combine`, `Separate`, `Group`, `Duplicate`, `MMB Axis Lock`)
  - *Display, Snap & Smooth*
  - *Inputs / Modifiers Stack*
  - *Retopo & Quad Draw*
  - *CamTools Pro*
  - *Maya Materials & Studio Lighting*
  - *Maya Axes & I/O*
- **Clean Empty Startup Scene (`ops_startup.py`)**: removes factory `Cube`/`Camera`/`Light` on `File → New` (`_on_load_post`), applies the dark 3-pane UI, and offers `maya_ux.new_clean_scene` + `maya_ux.save_clean_startup`.

---

## 8. Modeling, Smooth Preview, Retopo, CamTools, Materials & I/O
- **Modeling & Outliner** ([`ops_modeling.py`](../maya_ux_pro/ops_modeling.py), [`ops_modeling_pro.py`](../maya_ux_pro/ops_modeling_pro.py), [`ops_extrude.py`](../maya_ux_pro/ops_extrude.py), [`ops_outliner.py`](../maya_ux_pro/ops_outliner.py)): `Freeze Transforms`, `Delete History`, `Combine` / `Separate`, Maya Null **`Group`** (`⌘+G`), `Duplicate In-Place` / `+Transform` / `Duplicate Special`, interactive GPU **`Target Weld`**, **`Merge to Last`**, and **Maya Extrude Pro** (`maya_ux.maya_extrude` for Faces, Edges, Vertices & Curves with `Thickness`, `Local/World Translate`, `Offset`, `Divisions`, `Keep Faces Together`, `Taper`, `Twist`, Vertex `Length`/`Width`, and Show Manipulator).
- **Smooth Preview** ([`ops_smooth.py`](../maya_ux_pro/ops_smooth.py)): `1` / `2` / `3` non-destructive `MayaSmoothPreview` Subsurf workflow + `PgUp` / `PgDn`.
- **Retopo Pro** ([`ops_retopo.py`](../maya_ux_pro/ops_retopo.py)): **`Make Live`**, **`Quad Draw`** (auto `Shrinkwrap` + `Mirror` + `FACE_PROJECT` snap + Retopo overlay + `Poly Build`), **`Relax`**, **`Finish / Bake`**.
- **CamTools Pro** ([`ops_camtools.py`](../maya_ux_pro/ops_camtools.py)): `Cam from View`, Lock Camera, `24/35/50/85mm` presets, `Fix Clip` (`0.01..10000`), DoF, Passepartout, Composition Guides, 4 per-scene Camera Bookmarks.
- **Materials & Lighting** ([`ops_materials.py`](../maya_ux_pro/ops_materials.py)): 1-click `lambert1`, `blinn1`, `maya_clay`, `maya_chrome`, `maya_uv_checker`, `maya_glass`, plus toggleable `MayaStudioLights` 3-point rig.
- **Animation, UV & Maya Y-Up I/O** ([`ops_animation.py`](../maya_ux_pro/ops_animation.py), [`ops_uv.py`](../maya_ux_pro/ops_uv.py), [`ops_maya_axes.py`](../maya_ux_pro/ops_maya_axes.py), [`ops_maya_io.py`](../maya_ux_pro/ops_maya_io.py)): keyframe channels, Graph Editor tangent presets, UV tools (`Cut`/`Stitch`/`Unfold`/`Layout`), `Convert Up-Axis (±90° X)`, `cm` unit toggle, and automatic Maya Y-Up FBX/OBJ/USD import/export.
