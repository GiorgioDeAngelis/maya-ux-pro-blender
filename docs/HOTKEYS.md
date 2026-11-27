# Maya UX Pro — Complete Hotkey Reference (`v2.6.0`)

> Press **`?`** (or **`F1`**) inside Blender's 3D Viewport at any time to open the live searchable **Hotkey Reference & Equivalence** dialog.

---

## macOS / MacBook Pro Profile (`⌥ Option`, `⌘ Cmd`, `⌃ Ctrl`, `⇧ Shift`, `⌫ Delete`)

> macOS system shortcuts (`⌘+Space` Spotlight, `⌘+Q`, `⌘+W`, `⌘+H`, `⌘+M`, `⌘+Tab`) are never hijacked.

### Navigation, Viewport & Spacebar
| Command | Shortcut |
|---|---|
| Tumble (Orbit) | `⌥ Option + Click` or `2-Finger Drag` |
| Track (Pan) | `MMB` (Empty / `Q`) · `⌥ + MMB` · `⌥ + ⇧ + Click` |
| Dolly (Zoom, Maya inverted) | `⌥ + RMB` · `⌥ + ⌃ + Click` · `Trackpad Pinch` |
| Virtual Transform (Global / Last Axis) | `MMB Drag` (Selected Object or Vert/Edge/Face + `W / E / R / T`) |
| Select / Move / Rotate / Scale / Universal | `Q` / `W` / `E` / `R` / `T` |
| Gizmo Size + / - | `⇧ + +` / `⇧ + -` (or `=` / `-` / `Numpad +` / `Numpad -`) |
| Frame Selected / Frame All | `F` / `A` (`⇧+F` / `⇧+A` all 4 views) |
| Tap Spacebar (Pane / Quad View) | `Space` tap (`< 0.20s` — maximizes hovered pane or Quad View with `Persp`) |
| Hold Spacebar (Floating Maya Hotbox) | `Space` hold (`≥ 0.20s` or drag) · `⇧ + Space` View Pie |
| Expert Mode (Fullscreen Panels) | `⌃ + Space` (All Editors, preserves `⌘ + Space` Spotlight) |
| Shading: Wire / Solid / Tex / Light / Default | `4` / `5` / `6` / `7` / `0` |
| Wireframe on Shaded / X-Ray | `⌥ + 5` / `⌥ + X` |
| Isolate Select | `⌘ + 1` or `⇧ + I` (or `⌃ + 1`) |
| Toggle Channel Box (`N` Panel) / Cycle BG | `⌃ + A` / `⌥ + B` |
| Camera Undo / Redo | `[` / `]` |
| Hotkey Reference (Searchable) | `?` (`⇧ + /`) or `Fn + F1` |
| Increment & Save | `⌘ + ⌥ + S` |

### Visibility & Marking Menus
| Command | Shortcut |
|---|---|
| Smart Hide / Hide / Unhide | `H` / `⌃ + H` / `⇧ + H` (`⌘+H` macOS safe) |
| Hide Unselected / Show Last Hidden | `⌥ + H` / `⌃ + ⇧ + H` |
| Component Marking Menu | `RMB` |
| Modeling Marking Menu | `⇧ + RMB` |
| Object / Vertex / Edge / Face | `F8` Toggle · `⌥ + 1 / 2 / 3 / 4` (or `F9 / F10 / F11`) |
| Undo / Redo (Maya + macOS) | `Z` / `⇧ + Z` / `⌘ + Y` (`⌘ + Z` also active) |
| Repeat Last | `G` or `Y` |

### Selection, Pick Walk & Soft Select
| Command | Shortcut |
|---|---|
| Face Center-Only Selection | `LMB Click` on center dot (`⇧+Click` toggle, `⌃+Click` deselect) |
| Orthographic Select-Through (Shaded) | `LMB Drag` / `LMB Click` in Ortho views (selects front & hidden back Verts/Edges/Faces even in Shaded mode) |
| Grow / Shrink Selection (1 step per press) | `>` / `<` (Italian/EU ISO `<>` or `⇧ + .` / `⇧ + ,`) |
| Invert Selection | `⌘ + ⇧ + I` |
| Convert to Vert / Edge / Face | `⌃ + F9` / `⌃ + F10` / `⌃ + F11` |
| Pick Walk (Hierarchy / Edge Loops) | `↑` / `↓` / `←` / `→` (`→` Edge Loop · `←` back to seed edge or deselect loop · `↑`/`↓` step loop · `⇧+↑/↓` extend & LIFO decrement) |
| Screen-Space Nudge | `⌥ + ↑ / ↓ / ← / →` |
| Soft Select / Radius - / + | `B` / `⇧ + [` / `⇧ + ]` |
| Smart Delete / Dissolve Edge | `⌫ Delete` (keep verts) / `⌘ + ⌫ Delete` (remove verts) |

### Pivot, Snap, Smooth & Modeling
| Command | Shortcut |
|---|---|
| Edit Pivot (Hold or Tap) / Pivot Pie | `Hold D` (`D+V/C/X` snap pivot) / `⌥ + D` |
| Snap: Grid / Edge / Vertex / Discrete | `Hold X` / `Hold C` / `Hold V` / `Hold J` (`⇧+J` Relative) |
| Smooth Preview (Rough / Cage / Smooth) | `1` / `2` / `3` (`PgUp` / `PgDn` step +/-) |
| Duplicate In-Place / +Transform / Special | `⌘ + D` / `⇧ + D` / `⌘ + ⇧ + D` |
| Delete History | `⌥ + ⇧ + D` |
| Group / Parent / Unparent | `⌘ + G` / `P` / `⇧ + P` |
| Extrude / Bevel / Multi-Cut | `⌘ + E` / `⌘ + B` / `⌘ + ⇧ + X` |
| Bridge / Merge Menu / Reverse Normals | `⌘ + ⇧ + B` / `M` (`⌘ + ⌥ + M`) / `⌥ + N` |
| Target Weld / Quad Draw / Make Live | `⇧ + RMB` / `N → Maya → Retopo` / Top Shelf |

### Animation, Timeline & Graph Editor
| Command | Shortcut |
|---|---|
| Set Keyframe (All / Loc / Rot / Scale) | `S` / `⇧ + W` / `⇧ + E` / `⇧ + R` |
| Play Timeline / Go to Min Frame / AutoKey | `⌥ + V` / `⌥ + ⇧ + V` / `⌥ + K` |
| Prev / Next Keyframe \| Prev / Next Frame | `,` / `.` \| `⌥ + ,` / `⌥ + .` |
| Graph Tangents: Linear / Auto / Stepped / Spline / Pie | `1` / `2` / `3` / `4` / `T` (`⌥ + I` Insert Key) |

### UV Editor
| Command | Shortcut |
|---|---|
| UV Marking Menu / QWER Tools | `RMB` / `Q`, `W`, `E`, `R` |
| Frame Selected / Frame All | `F` / `A` |
| Select UV Shell / Grow / Shrink | `⌘ + F12` / `>` / `<` |
| Cut Seams / Stitch / Unfold / Layout | `⇧ + X` / `⇧ + S` / `⌘ + U` / `⌘ + L` |

---

## Windows / Linux Profile (`Alt`, `Ctrl`, `Shift`)

### Navigation, Viewport & Spacebar
| Command | Shortcut |
|---|---|
| Tumble / Track / Dolly | `Alt + LMB` / `MMB` (or `Alt + MMB`) / `Alt + RMB` |
| Smart MMB Virtual Transform | `MMB Drag` (Selected Object or Vert/Edge/Face + `W / E / R / T`) |
| Select / Move / Rotate / Scale / Universal | `Q` / `W` / `E` / `R` / `T` |
| Frame Selected / Frame All | `F` / `A` (`Shift + F` / `Shift + A` all views) |
| Tap Spacebar / Hold Spacebar | `Space` (Tap = Pane/Quad View, Hold = Hotbox) · `Shift + Space` Pie |
| Expert Mode (Fullscreen Panels) | `Ctrl + Space` |
| Shading: Wire / Solid / Tex / Light / Default | `4` / `5` / `6` / `7` / `0` |
| Wireframe on Shaded / X-Ray / Isolate | `Alt + 5` / `Alt + X` / `Ctrl + 1` or `Shift + I` |
| Channel Box / Cycle Viewport BG | `Ctrl + A` / `Alt + B` |
| Camera Undo / Redo | `[` / `]` |
| Hotkey Reference / Increment Save | `?` or `F1` / `Ctrl + Alt + S` |

### Selection, Modeling, Pivot, Animation & UV
| Category | Key Shortcuts |
|---|---|
| **Modes & Visibility** | `F8` Toggle · `F9/F10/F11` Vert/Edge/Face · `RMB` Component Pie · `Shift+RMB` Modeling Pie · `H / Ctrl+H / Shift+H / Alt+H / Ctrl+Shift+H` Hide |
| **Selection** | `LMB Click` Face Center Handle (`Shift` toggle, `Ctrl` deselect) · `> / <` Grow/Shrink · `Ctrl+Shift+I` Invert · `Ctrl+F9/F10/F11` Convert · `Arrows` Pick Walk · `Alt+Arrows` Nudge · `B` (`Shift+[/]`) Soft Select · `Backspace` / `Ctrl+Backspace` Smart Delete |
| **Pivot & Snap** | `Hold D` Edit Pivot (`D+V/C/X`) · `Alt+D` Pivot Pie · `Hold X/C/V/J` Snap (`Shift+J` Rel) · `1/2/3` (`PgUp/PgDn`) Smooth Preview |
| **Modeling** | `Ctrl+D` / `Shift+D` / `Ctrl+Shift+D` Dup · `Alt+Shift+D` Delete History · `Ctrl+G` Group · `P / Shift+P` Parent/Unparent · `Ctrl+E` Extrude · `Ctrl+B` Bevel · `Ctrl+Shift+X` Multi-Cut · `Ctrl+Shift+B` Bridge · `M` (`Ctrl+Alt+M`) Merge Menu · `Alt+N` Flip Normals |
| **Animation & Graph** | `S` / `Shift+W/E/R` Keyframe · `Alt+V` Play · `Alt+Shift+V` Min Frame · `Alt+K` AutoKey · `,/.` Prev/Next Key · `Alt+,/.` Step Frame · Graph: `1/2/3/4/T`, `Alt+I` |
| **UV Editor** | `RMB` UV Pie · `Q/W/E/R` Tools · `Ctrl+F12` Shell · `Shift+X` Cut · `Shift+S` Stitch · `Ctrl+U` Unfold · `Ctrl+L` Layout |
