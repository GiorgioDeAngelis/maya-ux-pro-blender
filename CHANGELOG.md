# Changelog

All notable changes to **Maya UX Pro** are documented in this file.

## [2.8.2] - 2026-11-27
### Fixed
- **Maya Extrude 3D Show Manipulator rebuilt on Blender native C++ gizmos (`ops_extrude.py`)**:
  - Replaced custom arrow/ring gizmos with native `GIZMO_GT_arrow_3d` (`NORMAL` arrows + `BOX` axis scale handles) and `GIZMO_GT_dial_3d` (`TWIST` ring) bound via `target_set_handler("offset", get=..., set=...)` for thick C++ hover hitboxes and reliable 3D cursor tracking across Perspective, Ortho, Quad View, and 1080p/Retina viewports.
  - Eliminated severe handle overlap where the center scale cube (`select_bias=12`) and `SCALE_Z` cube stole clicks along the Blue Extrude Arrow and Twist ring intercepted Red/Green arrow shafts.
  - Fixed `SCALE_Z` being a silent no-op on planar faces (`rel.z == 0`), froze `matrix_basis` updates during active drags to prevent feedback runaway, preserved the session header after drag exit, and guarded delayed `bpy.msgbus` `mesh_select_mode` callbacks so they never terminate a newly started Extrude session.
  - Fixed `ReferenceError: BMVert has been removed` when extruding multi-face grids containing interior vertices (`_map_extruded_verts`).

## [2.8.1] - 2026-11-27
### Fixed
- **Maya Extrude Show Manipulator handles were dead (`ops_extrude.py`)**: dragging the Blue/Red/Green arrows, the Cyan center cube, the axis scale cubes or the Twist ring had no effect in Blender 5.x because the handles delegated to a separate modal operator through `target_set_operator`, whose mouse-move events were swallowed by the gizmo tweak loop.
  - Every handle now drags **natively** through `Gizmo.invoke / modal / exit` (Blender's official custom-gizmo pattern): live per-frame deformation, `⇧` precise, `⌃` snap (0.1 units / 15°), `RMB`/`Esc` cancel restores the geometry, release pushes one undo step.
  - Screen-space mapping rewritten: arrows follow the cursor along their projected axis (1:1 world units), the center cube scales radially from the pivot, axis cubes scale by projected distance ratio, the ring twists by the real angle around the pivot. Live value shown in the viewport header.
  - The `Local ↔ World` button is now a dedicated click gizmo (`VIEW3D_GT_maya_extrude_button`).

## [2.8.0] - 2026-11-27
### Added
- **Native 3D Maya Extrude Show Manipulator & Video Workflow Parity (`ops_extrude.py`, `ops_selection.py`, `keymap.py`, `ui_channel_box.py`)**:
  - **Dedicated 3D Extrude Manipulator (`VIEW3D_GGT_maya_extrude`)**: active exclusively during an Extrude session (no overlap with `builtin.transform`), featuring a **Blue Normal Arrow** (`AUTO_Z`) that pushes every selected face/island symmetrically along its own normal even on opposite faces or 4-face rings, **Cyan Center Cube** (`UNIFORM_SCALE`) for uniform per-island scaling/inset, **Red/Green Arrows**, **Axis Scale Cubes**, **Rotation Twist Ring**, and a clickable **`Local ↔ World`** space toggle directly on the manipulator.
  - **Chained Extrude on `G` (`maya_ux.repeat_last`)**: pressing **`G`** in Edit Mesh while an Extrude session is active immediately chains another Extrude instead of repeating a transform drag.
  - **Face Loop & Vertex Loop on `Shift + Double-Click`** (`LMB Double-Click` selects Edge Loop or Face/Vertex Shell; `⇧ + Double-Click` on an adjacent face or vertex selects the full **Face Loop** or **Vertex Loop** across Perspective and Ortho views).
  - **`Mesh > Maya Extrude` Top Menu & `Fix Double Extrude` (`maya_ux.cleanup_extrude`)**: added Maya Extrude menu entries to `VIEW3D_MT_edit_mesh` and a 1-click zero-thickness double-extrude cleanup (`Merge by Distance` + `Recalc Normals`) in `N → Maya`.

## [2.7.3] - 2026-11-27
### Added
- **Double-Click Edge Loop Selection (`ops_selection.py`, `keymap.py`)**:
  - Double-clicking **Left Mouse (`LMB Double-Click`)** on any edge in Edge Mode or Multi-Component Mode selects the entire **Edge Loop** (`⇧ + Double-Click` adds/deselects loops without losing selection, `⌃ + Double-Click` removes the loop).
  - Works seamlessly in both **Perspective** (`mesh.loop_select`) and **Orthographic Select-Through** (`collect_edge_loop_indices` + `pick_stacked_indices_2d`), while keeping `⌥+Click` macOS Orbit untouched.

## [2.7.2] - 2026-11-27
### Added
- **Maya Center Global Scale Manipulator (`ops_viewport.py`)**:
  - Added a dedicated interactive center cube gizmo (`VIEW3D_GGT_maya_center_scale` / `VIEW3D_GT_maya_center_scale_cube`) in **Scale Mode (`R` / `builtin.scale`)** across Object Mode and Edit Mode.
  - Dragging the cyan center cube performs uniform **Global Scale** (`transform.resize`, all axes locked proportionally together) around the active pivot (`Median`, `Bounding Box`, `Active Element`, or `3D Cursor`).

## [2.7.1] - 2026-11-27
### Fixed
- **All-in-One Transform Gizmo (`Translate + Rotate + Scale`) Restricted Strictly to Extrude Mode (`ops_extrude.py`, `ops_viewport.py`, `ops_startup.py`, `ops_pivot_snap.py`, `ops_selection.py`)**:
  - Cleared persistent `show_gizmo_object_translate / rotate / scale` viewport overlay flags across `W/E/R/Q`, Startup, Pivot Snap, and mode switches so only the active single tool gizmo displays outside Extrude.
  - Added an explicit Extrude manipulator session (`start_extrude_session` / `end_extrude_session` + `bpy.msgbus` observers): running `maya_ux.maya_extrude` activates `builtin.transform` (`Translate + Rotate + Scale` in `Normal`/`Global` space), while switching tools (`Q/W/E/R`), switching modes (`Object` / `Vert` / `Edge` / `Face`), or making a new component selection automatically exits `builtin.transform` and restores your prior tool & orientation. Blocked activating `builtin.transform` outside active Extrude mode.

## [2.7.0] - 2026-11-27
### Added
- **Authentic Maya Extrude (`Edit Mesh > Extrude`, `maya_ux_pro/ops_extrude.py`)**:
  - Replaced Blender's basic extrude on **`⌘+E` / `Ctrl+E`**, **`Shift+RMB`** Modeling Pie, **Top Shelf (`Poly`)**, **Floating Hotbox**, and **N-Panel (`Pivot & Modeling`)** with **`maya_ux.maya_extrude`** supporting **Faces** (`polyExtrudeFace`), **Edges** (`polyExtrudeEdge`), **Vertices** (`polyExtrudeVertex`), and **Curve Paths** (`Extrude Along Curve`).
  - Implemented Maya's full attribute & manipulator set: **`Thickness`** (uniform normal depth), **`Local / World Translate (X/Y/Z)`** with live **Local ↔ World** coordinate space toggle (`maya_ux.toggle_extrude_space`), **`Offset`** (`+` inset / `-` outset), **`Divisions`**, **`Keep Faces Together`** (`ON` unified shell / `OFF` discrete components, toggled via **`⌘+⇧+E` / `Ctrl+Shift+E`** via `maya_ux.toggle_keep_faces_together`), **`Taper`**, **`Twist`**, **`Scale`**, **`Rotate`**, Vertex **`Length`** & **`Width`**, **`Extrude Along Curve`** (`maya_ux.extrude_along_curve`), and automatic **Show Manipulator** (`builtin.transform`) gizmo activation (`extrude_activate_gizmo` preference).

## [2.6.3] - 2026-11-27
### Added
- **Enlarged Selected Vertices Overlay (`ops_selection.py`, `preferences.py`)**:
  - Added a GPU `POST_VIEW` viewport overlay (`POINT_UNIFORM_COLOR`) that renders **only selected vertices** larger (`6.0` logical px default, configurable `3.0–16.0` px via **Selected Vertex Size (px)** and toggleable via **Enlarge Selected Vertices** in Preferences), keeping unselected vertices at your compact theme size.
  - Draws the active vertex slightly larger (`+1 px`) in crisp active highlight color (`editmesh_active` RGB) and automatically respects perspective surface depth occlusion while drawing front and hidden back selected vertices clearly in Orthographic, Wireframe, and X-Ray views.

## [2.6.2] - 2026-11-27
### Added
- **Maya Isolated Component Selection Display (`ops_selection.py`, `preferences.py`, `ops_viewport.py`)**:
  - Added automatic per-mode selection highlight isolation (`isolate_component_display`, default ON): in **Vertex Mode** only selected vertices are highlighted (implied edges/faces stay hidden), in **Edge Mode** only selected edges are highlighted (implied faces stay hidden), and in **Face Mode** only selected faces are highlighted (`Multi-Component` and `Object Mode` automatically restore full user theme highlights).

## [2.6.1] - 2026-11-27
### Fixed
- **Orthographic Select-Through with `Move (W)` / `Rotate (E)` / `Scale (R)` / `Transform (T)` Active**: bound `maya_ux.ortho_select_box` to `3D View Tool: Select Box (fallback)` in addition to `3D View Tool: Select Box`, so dragging a box selection in Ortho views works with Select-Through regardless of whether `Select Box (Q)` or a transform gizmo tool (`W/E/R/T`) is active, and hardened Quad View marquee start coordinates.

## [2.6.0] - 2026-11-27
### Added
- **Orthographic Select-Through in Shaded Mode (`ops_selection.py`, `preferences.py`, `keymap.py`)**:
  - In any Orthographic view (`Top`, `Front`, `Side`, `Back`, `Left`, `Bottom`, `User Ortho`, and Quad View ortho panes), marquee box selection (`LMB Drag` / `⇧+Drag` / `⌃+Drag`) and click selection (`LMB Click` / `⇧+Click` / `⌃+Click`) now select **both front and hidden back components** across **Vertex**, **Edge**, **Face**, and **Multi-Component** modes even when shading is Solid / Material / Rendered (matching Wireframe and Maya behavior).
  - Perspective (`Persp`) views keep standard front-facing occlusion. Toggleable in Preferences (`Orthographic Select-Through (Shaded)`).

## [2.5.11] - 2026-11-27
### Improved
- **Ordered LIFO Decrement for `Shift + ↓` / `Shift + ↑` (`ops_selection.py`)**: extending Edge Loops with `Shift + ↑` and then pressing `Shift + ↓` now cleanly pops the added edge loops back in reverse order down to the starting anchor loop before extending in the opposite direction (symmetric in both directions).

## [2.5.10] - 2026-11-27
### Improved
- **`LEFT_ARROW` (`←`) Edge Loop Pick Walk (`ops_selection.py`)**: pressing `←` on an Edge Loop that was expanded from a single edge via `→` returns cleanly to that original single edge; pressing `←` on any other Edge Loop (after `↓`/`↑` stepping or direct loop selection) deselects the entire Edge Loop.

## [2.5.9] - 2026-11-27
### Added & Fixed
- **Maya Edge Loop Pick Walk (`↑ / ↓ / ← / →` and `⇧ + ↑ / ↓` in Mesh Edge Mode)**:
  - Pressing `→` (or `←`) with an edge selected selects the full Edge Loop (`mesh.select_edge_loop_multi` / `loop_multi_select`).
  - Pressing `↓` or `↑` jumps step-by-step to the next parallel Edge Loop in opposite directions, deselecting the previous loop.
  - Pressing `⇧ + ↓` or `⇧ + ↑` steps to the next parallel Edge Loop while keeping previously selected loops selected.
- **Blender 5.3 Fix**: updated `VIEW3D_MT_maya_component_pie` to call `mesh.select_edge_loop_multi` (preserving Blender 4.2–5.2 `loop_multi_select` fallback).

## [2.5.8] - 2026-11-26
### Fixed
- **Shrink (`<`) at 100% Mesh Selection (`ops_selection.py`)**: fixed Blender's no-op `mesh.select_less()` when all vertices, edges, or faces of a closed mesh or island are selected — `maya_ux.grow_shrink_selection` now steps back cleanly via the tracked Grow stack (`_GROW_HISTORY`) and peels open-mesh boundaries when starting from `Select All`.

## [2.5.7] - 2026-11-26
### Fixed & Improved
- **Strict 1-Step Component Grow (`>`) / Shrink (`<`)**: in Edit Mode, each press now steps strictly 1 increment in the active component (`use_face_step=False` for **Vertex** and **Edge** modes so vertices grow `1→5→13` and edges grow `1→7→23`; `use_face_step=True` for **Face** mode `1→9→25`), with `repeat=False` so holding/tapping never over-steps, plus `BACK_SLASH` ISO fallback.
- **Gizmo Size on `Shift + +` / `Shift + -` (`maya_ux.gizmo_size`)**: added `Shift++` (increase) and `Shift+-` (decrease) across **Italian/EU ISO Mac keyboards** (`PLUS`/`MINUS`, `RIGHT_BRACKET+Shift` `*`, `SLASH+Shift` `_`), **US ANSI keyboards** (`Shift+=` / `Shift+-`), and **Numpad**, while preserving US `?` (Cheatsheet) and `Shift+]` (Soft Select Radius).

## [2.5.6] - 2026-11-26
### Added & Fixed
- **Maya Grow (`>`) / Shrink (`<`) Component Selection (`maya_ux.grow_shrink_selection`)**: works seamlessly in **Vertex**, **Edge**, **Face** (with 3×3 Maya ring step), **Multi-Component**, **Curve**, and **UV Editor** across **Italian/European Mac ISO keyboards** (`ACCENT_GRAVE` `<`/`>` and `GRLESS`), **ISO PC keyboards**, and **US/UK ANSI keyboards** (`⇧+.` / `⇧+,`), while passing through US `` ` `` / `~` untouched.

## [2.5.5] - 2026-11-26
### Added
- **`Shade Auto Smooth` in Object Mode RMB Marking Menu & Hotbox**: added `Shade Auto Smooth` (`object.shade_auto_smooth`) alongside `Shade Smooth` and `Shade Flat` in the Object Mode Right-Click Marking Menu (`VIEW3D_MT_maya_component_pie`) and Spacebar Floating Hotbox (`Modeling & Pivot`).

## [2.5.4] - 2026-11-26
### Added
- **Object Mode `Shade Smooth` & `Shade Flat` in Viewport RMB Marking Menu**: added `Shade Smooth` (`object.shade_smooth`) and `Shade Flat` (`object.shade_flat`) directly inside the Object Mode Right-Click (`RMB`) Marking Menu (`VIEW3D_MT_maya_component_pie`, grouped above `Frame Selected (F)`) and in the Spacebar **Floating Maya Hotbox** (`Modeling & Pivot`).

## [2.5.3] - 2026-11-26
### Changed & Fixed
- **Native Merge Menu (`M`)**: replaced `Merge to Last` in the `Shift+RMB` Modeling Marking Menu with Blender's full Merge menu (`VIEW3D_MT_edit_mesh_merge`) and bound `M` (plus `⌘+⌥+M` / `Ctrl+Alt+M`) in `Mesh` Edit Mode.
- **Maya `F` Frame Selected across Object & Component Modes**: bound bare `F` (`view3d.view_selected`) across `3D View`, `Object Mode`, `Mesh`, `Pose`, and `Curve` (overriding Blender's `F` Make Edge/Face in Edit Mesh so pressing `F` always focuses the selected object, vertex, edge, or face).

## [2.5.2] - 2026-11-26
### Fixed
- Fixed `TypeError: enum "LAST" not found in ('CENTER', 'CURSOR', 'COLLAPSE')` in `maya_ux.merge_to_last` (`ops_modeling_pro.py`) when merging box-selected/edge/face components without an active vertex in `bm.select_history`, falling back cleanly to `CENTER`.

## [2.5.1] - 2026-11-25
### Fixed
- Fixed `ReferenceError: BMesh data of type BMFace has been removed` in `maya_ux.select_face_center` by passing `(obj, face.index)` and holding live `BMesh` references via `apply_face_center_selection()`.

## [2.5.0] - 2026-11-25
### Added
- **Maya Face Center-Only Selection**: automatically enables `show_face_center = True` (`facedot_size = 5`) in Face Mode and restricts `LMB Click` / `⇧+Click` / `⌃+Click` selection strictly to clicking each polygon's center dot handle (`face_center_hit_radius = 10px`), with occlusion and `X-Ray` pass-through support.

## [2.4.1] - 2026-11-25
### Fixed
- Automatically hides Blender's overlapping top-left Text Info (`User Perspective / Cube`) while Maya Poly Count HUD is enabled (`sync_viewport_text_overlay()`), restoring it cleanly when disabled or unregistered.

## [2.4.0] - 2026-11-25
### Added
- **Maya Poly Count & Subdiv HUD** (`ui_poly_hud.py`): top-left 3-column viewport counter (`Verts`, `Edges`, `Faces`, `Tris`, `UVs` for Scene / Selected Objects / Selected Components) + `Subdiv current level` & `Subdiv mode`, with 1-click `HUD` toggle in Top Shelf, Channel Box, Hotbox, and Preferences.

## [2.3.0] - 2026-11-25
### Added
- **Clean Empty Startup Scene & 3-Pane UI** (`ops_startup.py`): automatic removal of factory `Cube`/`Camera`/`Light` on `File → New` (`_on_load_post`), clean charcoal 3-pane layout preset (`apply_clean_maya_ui`), `maya_ux.new_clean_scene`, and 1-click `Save Clean Empty Startup File`.

## [2.2.1] - 2026-11-25
### Changed
- Restored native Blender Z-Up coherence across viewport colors, Navigation Gizmo, `Transform Modal Map`, and Channel Box by default (keeping optional Y-Up toggles in Preferences and automatic Maya Y-Up conversion in FBX/OBJ/USD I/O).

## [2.2.0] - 2026-11-25
### Added
- GPU/BLF Maya Y-Up Axis Tripod HUD (`project_maya_yup_axes`) and optional `Transform Modal Map` Y/Z swap.

## [2.1.0 – 2.1.4] - 2026-11-25
### Added & Fixed
- **Maya Spacebar & 5-Zone Floating Hotbox** (`ops_hotbox.py`): Tap Spacebar to toggle Quad View (always unlocking top-right quadrant as **Persp** and preserving Persp camera across ortho pane zooms) or maximize hovered editor pane; Hold Spacebar (`≥0.20s` or drag) to open `MAYA HOTBOX`; `Ctrl+Space` Expert Mode across all editors.
- Fixed bare-Spacebar timeline playback conflict (`Frames` keymap disabled safely; playback on `⌥+V`).
- Fixed `create_maya_workspace` `workspace_name` property in Hotbox footer.
- Extended **Smart MMB Drag** to Edit Mode components (Vertices, Edges, Faces), multi-object edit, Curves, and Armatures with automatic Object→Edit tool inheritance.

## [2.0.0] - 2026-11-25
### Added
- **Maya Config Pro Suite**: Top Shelf 4 Menu Sets (`Display`, `Poly`, `Retopo`, `LookDev`), GPU interactive **`Target Weld`**, **`Make Live` + `Quad Draw`**, **CamTools Pro** (focal presets, clipping, guides, 4 bookmarks), **Maya Materials & 3-Point Studio Lights**, Maya Dark Theme + `Maya Pro` workspace, and live-searchable Hotkey Reference (`?` / `F1`).

## [1.0.0 – 1.7.0] - 2026-11-25
### Added
- Reversible 1-Click Maya Setup Manager (`maya_ux_pro_backup.json`).
- macOS / MacBook Pro safe keymap profile (`⌥`, `⌘`, `⌃`, `⇧`, `⌫ Delete`) + Trackpad gestures + Spotlight protection.
- Official Maya hotkey parity, Maya-inverted Dolly zoom, Smart MMB virtual transform, Hold-`D` Edit Pivot (`D+V/C/X`), Hold `X/C/V/J` Snap, Smooth Mesh Preview (`1/2/3`), Pick Walk (`↑↓←→`), Maya Groups (`⌘+G`), Animation/Graph/UV tools, and FBX/OBJ/USD Maya Y-Up I/O.
