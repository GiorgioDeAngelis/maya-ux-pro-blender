from __future__ import annotations

from . import (
    keymap,
    menus,
    ops_animation,
    ops_camtools,
    ops_extrude,
    ops_hotbox,
    ops_materials,
    ops_maya_axes,
    ops_maya_io,
    ops_modeling,
    ops_modeling_pro,
    ops_outliner,
    ops_pivot_snap,
    ops_retopo,
    ops_selection,
    ops_smooth,
    ops_startup,
    ops_uv,
    ops_viewport,
    ops_workspace,
    preferences,
    setup_manager,
    ui_channel_box,
    ui_cheatsheet,
    ui_poly_hud,
    ui_shelf,
)

_MODULES = (
    preferences,
    setup_manager,
    ops_viewport,
    ops_hotbox,
    ops_pivot_snap,
    ops_smooth,
    ops_maya_axes,
    ops_maya_io,
    ops_selection,
    ops_modeling,
    ops_modeling_pro,
    ops_extrude,
    ops_retopo,
    ops_outliner,
    ops_animation,
    ops_uv,
    ops_camtools,
    ops_materials,
    ops_workspace,
    ops_startup,
    menus,
    ui_channel_box,
    ui_shelf,
    ui_poly_hud,
    ui_cheatsheet,
    keymap,
)


def register():
    for mod in _MODULES:
        mod.register()


def unregister():
    for mod in reversed(_MODULES):
        mod.unregister()
