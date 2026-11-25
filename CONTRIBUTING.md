# Contributing to Maya UX Pro

Contributions, bug reports, and pull requests are very welcome!

## Repository Layout

```text
maya-ux-pro-blender/
├── maya_ux_pro/              # Blender Extension package (manifest + 25 Python modules)
│   ├── blender_manifest.toml # Extension metadata (Blender 4.2+, GPL-3.0-or-later)
│   ├── __init__.py           # Module registration order
│   ├── preferences.py        # AddonPreferences & macOS/Win detection
│   ├── keymap.py             # Modular Maya keymaps & macOS safety rules
│   ├── setup_manager.py      # Reversible 1-Click Maya setup + JSON backup
│   ├── ops_*.py              # Feature operators (Hotbox, Smart MMB, Pivot/Snap, Selection, Retopo, CamTools, etc.)
│   └── ui_*.py               # N-Panel Channel Box, Top Shelf, Poly Count HUD, Searchable Cheatsheet
├── tests/
│   └── test_maya_ux_pro.py   # 16 automated headless Blender test suites
├── docs/
│   ├── HOTKEYS.md            # Complete macOS & Win/Linux hotkey tables
│   └── FEATURES.md           # Module-by-module feature guide
└── README.md / README.it.md  # English & Italian documentation
```

## Validation, Packaging & Running Tests

Make sure Blender `4.2+` (tested on `5.3.0`) is installed, then run:

```bash
# 1. Validate the Blender extension manifest and structure
blender --command extension validate ./maya_ux_pro

# 2. Build a distributable .zip into ./dist
blender --command extension build --source-dir ./maya_ux_pro --output-dir ./dist

# 3. Validate the built archive
blender --command extension validate ./dist/maya_ux_pro-2.5.1.zip

# 4. Run all 16 automated headless test suites
blender --background --python-exit-code 1 --python ./tests/test_maya_ux_pro.py
```

On macOS, if `blender` is not in your `PATH`, use `/Applications/Blender.app/Contents/MacOS/Blender`.

## Key Design Constraints
- **macOS Safety**: Never bind bare `oskey=True` (`⌘`) on macOS-reserved shortcuts (`C, V, X, Z, S, O, N, A, Q, W, H, M, TAB, SPACE`), and never display the string `"Alt"` in macOS UI text (use `⌥`, `⌘`, `⌃`, `⇧`, `⌫ Delete`).
- **Blender `KeyMapItem` RNA flags**: modifier flags (`ctrl`, `shift`, `alt`, `oskey`, `repeat`) are integers (`0`/`1`) in Blender Python API.
- **Clean Unregister**: every timer, draw handler, `load_post` / `depsgraph_update_post` handler, keymap item, and `WindowManager` / `Scene` property must unregister cleanly (`test_unregistration` verifies this).
- **Non-Destructive Defaults**: new setups and `load_post` handlers must never touch saved `.blend` user files or non-factory objects.
