<div align="center">

# Maya UX Pro for Blender

**Authentic Autodesk Maya workflow inside Blender 4.2 – 5.3+ — Spacebar Floating Hotbox, Smart Middle-Mouse Transform, Face Center-Only Selection, Poly Count HUD, Hold-`D` Pivot & Snap, Retopo & CamTools Pro.**

[![Blender](https://img.shields.io/badge/Blender-4.2%20--%205.3%2B-orange?logo=blender)](https://www.blender.org/)
[![Version](https://img.shields.io/badge/Release-v2.8.0-blue)](https://github.com/GiorgioDeAngelis/maya-ux-pro-blender/releases/latest)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-green.svg)](./LICENSE)
[![Platforms](https://img.shields.io/badge/OS-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#platform-profiles-macos--windowslinux)
[![Tests](https://img.shields.io/badge/Headless%20Tests-17%2F17%20Passing-brightgreen)](./CONTRIBUTING.md)

**English** | [Italiano (README.it.md)](./README.it.md) · [All Hotkeys](./docs/HOTKEYS.md) · [Full Features Guide](./docs/FEATURES.md) · [Changelog](./CHANGELOG.md)

</div>

---

## Why Maya UX Pro?

Switching from Autodesk Maya to Blender is slowed down by more than a few keybindings. Blender's built-in *Industry Compatible* keymap only covers basics—it does not reproduce Maya's **Spacebar Hotbox & Quad View**, **Smart Middle-Mouse transform drag**, **Hold-`D` Edit Pivot + vertex/edge snap**, **Face Center-Only click selection**, **Poly Count HUD**, **Smooth Mesh Preview (`1`/`2`/`3`)**, or **macOS Trackpad / Spotlight-safe shortcuts**.

**Maya UX Pro** packages the complete Maya UX muscle memory into a single, non-destructive, **100% reversible** Blender Extension (`4.2 – 5.3+`).

---

## Quick Installation (30 Seconds)

### Option A — Drag & Drop (Easiest, Blender 4.2+)
1. Download **`maya_ux_pro-2.8.0.zip`** from the [**Latest GitHub Release**](https://github.com/GiorgioDeAngelis/maya-ux-pro-blender/releases/latest/download/maya_ux_pro-2.8.0.zip).
2. Open Blender and **drag & drop** the `.zip` file directly into the Blender window.
3. Click **OK** in the install dialog — the extension enables automatically.

### Option B — Install from Disk
1. Download `maya_ux_pro-2.8.0.zip` from [Releases](https://github.com/GiorgioDeAngelis/maya-ux-pro-blender/releases/latest).
2. In Blender open **Edit → Preferences → Get Extensions** (top-right `⌄` menu) → **Install from Disk...**.
3. Select the downloaded `.zip` and ensure **Maya UX Pro** is checked.

### Recommended First-Run Setup (1-Click & Reversible)
1. In **Preferences → Extensions / Add-ons → Maya UX Pro**, click **Apply Maya Base Setup**:
   - Saves a complete JSON backup (`maya_ux_pro_backup.json` in Blender's config folder) of your original keyconfig, navigation, zoom, snapping, gizmos, and theme.
   - Enables *Industry Compatible* base keymap + Maya navigation, inverted Maya zoom (`Pull Back = Zoom In`), Rotate Around Selection, Zoom to Mouse, and clean dark 3-pane Maya viewport.
   - You can revert to your exact original Blender configuration at any time with **Restore Previous Setup**.
2. *(Optional)* Click **Save Clean Empty Startup File** to save a blank `startup.blend` (empty scene + 3-pane dark UI without the bottom timeline).

---

## Key Features at a Glance

| Feature | Maya Behavior Implemented in Blender |
|---|---|
| **Spacebar & Floating Hotbox** | **Tap `Space`**: toggle 4-pane Quad View (top-right always **Persp**) or maximize hovered editor (`Outliner`, `Properties`, `UV`, `Graph`, `Nodes`). **Hold `Space`** (`≥0.20s` or drag): open 5-zone **Floating Maya Hotbox**. **`⌃+Space` / `Ctrl+Space`**: Expert Mode fullscreen (`⌘+Space` Spotlight preserved on macOS). |
| **Smart Middle Mouse (MMB)** | Empty selection or `Q` (Select): **MMB drags to Pan**. With `W` / `E` / `R` / `T` active on **Objects OR Edit Mode Vertices / Edges / Faces**: **MMB drags globally (or along last gizmo axis)** — plus **`V+MMB`** / **`C+MMB`** direct vertex/edge snap! |
| **Maya Zoom & Mac Trackpad** | Maya-inverted mouse dolly (`Pull back = Zoom In`), **`⌥+Click`** Orbit, **`⌥+⇧+Click`** / **`MMB`** Pan, **`⌥+RMB`** / **`⌥+⌃+Click`** Zoom, plus native 2-finger Trackpad & Pinch gestures, and **`[` / `]`** Camera Undo/Redo. |
| **Hold-`D` Edit Pivot & Snap** | Hold **`D`** to edit object origin directly (`D+V` snap pivot to vertex, `D+C` to edge, `D+X` to grid). Hold **`X` / `C` / `V` / `J`** for temporary Grid / Edge / Vertex / Discrete snap. **`⌥+D`** opens Pivot Marking Menu. |
| **Face Center-Only Selection** | Displays crisp Maya-style center dot handles on polygons (`show_face_center = True`, size `5`). In Face Mode, faces are selected **only when clicking their center handle** (`Click`, `⇧+Click` toggle, `⌃+Click` deselect). Also isolates active component highlights (`Vert`/`Edge`/`Face`) and draws **selected vertices larger** (`6 px` default) while keeping unselected vertices subtle. |
| **Maya Poly Count & Subdiv HUD** | Live top-left 3-column viewport counter (**Scene \| Selected Objects \| Selected Components**) for `Verts`, `Edges`, `Faces`, `Tris`, `UVs`, plus `Subdiv current level` & `Subdiv mode`. Auto-hides Blender's overlapping Text Info overlay. |
| **Top Shelf (4 Menu Sets)** | Compact viewport header bar with **`Display` \| `Poly` \| `Retopo` \| `LookDev`** tabs, live **`EDIT PIVOT`** & **`LIVE`** status badges, and 1-click **`HUD`** toggle. |
| **Maya Extrude Pro (`⌘+E` / `Ctrl+E`)** | Authentic `Edit Mesh > Extrude` for **Faces**, **Edges**, **Vertices** (`Length` / `Width` / `Divisions`), and **Curve Paths** with **`Thickness`**, **`Local / World Translate`**, **`Offset`**, **`Divisions`**, **`Keep Faces Together`** (`⌘+⇧+E` / `Ctrl+Shift+E`), **`Taper`**, **`Twist`**, and **Show Manipulator**. |
| **Retopology & Target Weld Pro** | **`Target Weld`** interactive modal tool with GPU highlight overlay; **`Make Live`** + **`Quad Draw`** (Shrinkwrap + Mirror + X-Ray Retopo + Poly Build) + **`Relax`** + **`Bake`**. |
| **Smooth Mesh Preview (`1`/`2`/`3`)** | **`1`** Rough cage, **`2`** Subdiv + cage, **`3`** Smooth preview (`PgUp`/`PgDn` adjusts subdivisions). |
| **CamTools Pro & Maya LookDev** | **`Cam from View`**, Lock Camera, `24/35/50/85mm` presets, `Fix Clip`, DoF, Passepartout, Composition Guides, 4 Camera Bookmarks; **`lambert1`**, **`blinn1`**, **`maya_clay`**, **`maya_chrome`**, **`maya_uv_checker`**, **`maya_glass`** + **`3-Point Studio Lights`**. |
| **Empty New Scene & Clean UI** | Automatically removes factory `Cube`, `Camera`, and `Light` on `File → New` and applies a clean 3-pane dark layout (`View3D`, `Outliner`, `Properties`). |
| **Maya Y-Up I/O + Native Z-Up** | Keeps Blender's Z-Up kernel 100% consistent across Transform panels, Graph Editor, and Modifiers while automatically converting to **Maya Y-Up** on **FBX / OBJ / USD** Import & Export. |

---

## Core Workflows Explained

### 1. Spacebar & Floating Maya Hotbox
- **Tap `Space`** (`< 0.20s` without dragging):
  - In **Single 3D Viewport**: switches to **4-View (Quad View)** where the top-right user quadrant is always unlocked **Perspective (`PERSP`)** — never accidentally stuck in `ORTHO`.
  - In **Quad View**: detects the exact quadrant under your cursor (`Top`, `Front`, `Side`, or `Persp`), saves your `Persp` camera, and maximizes that quadrant cleanly.
  - Over **any other visual editor** (`Outliner`, `Properties`, `UV/Image`, `Graph`, `Dopesheet`, `Shader/Node`, `NLA`, `Sequencer`): maximizes/restores that pane under the cursor.
  - Safely passes through inside `Text Editor`, `Console`, text-edit mode, and popup fields so typing spaces always works normally.
- **Hold `Space`** (`≥ 0.20s` or drag `≥ 14px`): opens the **Floating Maya Hotbox** (`660px` wide) organized into 5 Maya zones (`File / Edit / Display`, `Modes & Retopo`, `Maya Views & Panes`, `Modeling & Pivot`, `Channel Box & Workspaces`).
- **`⌃ + Space` (`Ctrl + Space`)**: toggles **Expert Mode** (full-screen without panels) across all editors — keeping `⌘ + Space` free for **macOS Spotlight**.

### 2. Smart Middle Mouse (`MMB`) + Component Support
- **Nothing selected** or **`Q` (Select tool)**: dragging **MMB** pans the viewport cleanly (`⌥+MMB` also forces Pan anytime).
- **Object selected OR Vertices/Edges/Faces selected in Edit Mode** with **`W` / `E` / `R` / `T`**:
  - Dragging **MMB anywhere in the viewport** performs a virtual Move / Rotate / Scale globally — or locked to the last gizmo axis you dragged!
  - Switching into Component Mode via Marking Menu, Hotbox, `F8`/`F9`/`F10`/`F11`, or `Tab` automatically inherits your active Object transform tool (`W/E/R/T`) until you explicitly switch to `Q` (Select).
  - Holding **`V` + MMB** snaps to vertices (including vertices on the same mesh in Edit Mode); holding **`C` + MMB** snaps to edges.

### 3. Face Center-Only Selection
In Maya, polygons are selected by clicking their small center square rather than anywhere inside the face interior:
- Entering **Face Mode** displays center dots (`facedot_size = 5`) on all visible polygon faces.
- Clicking within `Face Center Hit Radius` (`10px` default, configurable in Preferences) of a face center dot selects it (`Click` replace, `⇧+Click` toggle, `⌃+Click` deselect).
- Clicking away from center handles will never accidentally select large background polygons (`X-Ray` / `Wireframe` mode lets you pick through to back faces).

### 4. Built-in Searchable Hotkey Reference (`?` or `F1`)
Press **`?`** (or **`F1`**) at any time in the 3D Viewport to open the **Maya UX Pro Hotkey Reference & Equivalence** popup with live instant search across both Maya and Blender command names.

→ See the full categorized tables in **[docs/HOTKEYS.md](./docs/HOTKEYS.md)** and the complete module reference in **[docs/FEATURES.md](./docs/FEATURES.md)**.

---

## Quick-Start Hotkey Cheat Sheet

| Action | macOS (`⌥ ⌘ ⌃ ⇧`) | Windows / Linux |
|---|---|---|
| Tumble (Orbit) | `⌥ Option + Click` or `2-Finger Drag` | `Alt + LMB` |
| Track (Pan) | `MMB` (Empty/`Q`) · `⌥+MMB` · `⌥+⇧+Click` | `MMB` (Empty/`Q`) · `Alt+MMB` |
| Dolly (Zoom, Maya inverted) | `⌥+RMB` · `⌥+⌃+Click` · `Pinch` | `Alt+RMB` |
| Smart MMB Virtual Transform | `MMB Drag` (with `W/E/R/T`) | `MMB Drag` (with `W/E/R/T`) |
| Select / Move / Rotate / Scale / Universal | `Q` / `W` / `E` / `R` / `T` | `Q` / `W` / `E` / `R` / `T` |
| Quad / Pane Maximize vs Hotbox | `Space` (Tap / Hold) · `⇧+Space` Pie | `Space` (Tap / Hold) · `Shift+Space` Pie |
| Expert Mode (Fullscreen Panels) | `⌃ + Space` | `Ctrl + Space` |
| Component / Modeling Menu | `RMB` / `⇧ + RMB` | `RMB` / `Shift + RMB` |
| Object / Vert / Edge / Face | `F8` Toggle · `⌥+1 / 2 / 3 / 4` | `F8` Toggle · `F9 / F10 / F11` |
| Edit Pivot / Pivot Snap / Pivot Pie | `Hold D` (`D+V/C/X`) · `⌥+D` | `Hold D` (`D+V/C/X`) · `Alt+D` |
| Snap Grid / Edge / Vertex / Step | `Hold X / C / V / J` (`⇧+J` Rel) | `Hold X / C / V / J` (`Shift+J` Rel) |
| Frame Selected / All | `F` / `A` (`⇧+F/A` all views) | `F` / `A` (`Shift+F/A` all views) |
| Smooth Preview (Rough/Cage/Smooth) | `1` / `2` / `3` (`PgUp/PgDn`) | `1` / `2` / `3` (`PgUp/PgDn`) |
| Wire / Shaded / Tex / Light / X-Ray | `4 / 5 / 6 / 7` · `⌥+5` W/S · `⌥+X` | `4 / 5 / 6 / 7` · `Alt+5` W/S · `Alt+X` |
| Isolate Select / Channel Box | `⌘+1` or `⇧+I` · `⌃+A` | `Ctrl+1` or `Shift+I` · `Ctrl+A` |
| Play Timeline / AutoKey | `⌥+V` · `⌥+K` | `Alt+V` · `Alt+K` |
| Duplicate / Dup+Trans / Special | `⌘+D` / `⇧+D` / `⌘+⇧+D` | `Ctrl+D` / `Shift+D` / `Ctrl+Shift+D` |
| Group / Delete History | `⌘+G` · `⌥+⇧+D` | `Ctrl+G` · `Alt+Shift+D` |
| Smart Delete / Dissolve Edge | `⌫ Delete` · `⌘+⌫ Delete` | `Backspace` · `Ctrl+Backspace` |
| Undo / Redo / Repeat Last | `Z` / `⇧+Z` / `G` or `Y` | `Z` / `Shift+Z` / `G` or `Y` |

<a id="platform-profiles-macos--windowslinux"></a>

---

## Platform Profiles (`macOS` & `Windows/Linux`)

Maya UX Pro auto-detects macOS vs Windows/Linux (`AUTO`), or lets you override it in Preferences:
- **macOS Profile**: uses Apple symbols (`⌥ Option`, `⌘ Cmd`, `⌃ Ctrl`, `⇧ Shift`, `⌫ Delete`), never hijacks macOS system shortcuts (`⌘+Space`, `⌘+Q`, `⌘+W`, `⌘+H`, `⌘+Tab`, `⌘+M`), maps `Ctrl+Space` for Expert Mode, `Ctrl+A` for Channel Box, `Ctrl+H` for Hide, `⌥+1..4` for Fn-free component switching on MacBook Pro keyboards, and adds Trackpad gestures + no-MMB modifiers (`⌥+⇧+Click` Pan, `⌥+⌃+Click` Zoom).
- **Windows / Linux Profile**: standard Maya `Alt` / `Ctrl` / `Shift` bindings.

---

## FAQ & Troubleshooting

<details>
<summary><strong>1. Why does Blender still show Z as vertical in Item → Transform?</strong></summary>

Blender's C++ kernel is strictly **Z-Up** internally (`obj.location.z` is vertical height across transforms, Graph Editor, Physics, and Modifiers). Like *Maya Config Pro* and *Industry Compatible*, Maya UX Pro keeps Blender **Z-Up** internally by default so gizmos, keybindings, and numerical panels stay 100% consistent—while automatically converting to **Maya Y-Up** during **FBX / OBJ / USD** import & export. *(If you still prefer Maya Y-Up colors/tripod/Channel Box UI, optional toggles exist in Preferences → Maya UX Pro.)*
</details>

<details>
<summary><strong>2. Pressing Spacebar plays the timeline instead of opening the Hotbox</strong></summary>

Maya UX Pro automatically disables Blender's bare-`Space` playback binding in `Frames` and maps Timeline Playback to Maya's **`⌥+V` (`Alt+V`)**. Make sure **Maya Marking Menus** is enabled and **Spacebar Mode** is set to **Hybrid** in Preferences.
</details>

<details>
<summary><strong>3. How do I uninstall or revert back to stock Blender?</strong></summary>

Open **Preferences → Extensions → Maya UX Pro** and click **Restore Previous Setup** (this restores your saved pre-Maya keymap, zoom, snap, and theme backup), then disable or uninstall the extension.
</details>

---

## Development, Build & Tests

Validate, package, and run all **17 headless test suites** locally with Blender CLI:

```bash
blender --command extension validate ./maya_ux_pro
blender --command extension build --source-dir ./maya_ux_pro --output-dir ./dist
blender --background --python-exit-code 1 --python ./tests/test_maya_ux_pro.py
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for architecture details and contribution guidelines.

---

## License

Released under the **[GNU General Public License v3.0 (GPL-3.0-or-later)](./LICENSE)**.
