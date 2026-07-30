"""The layout constants EVERY settings-panel family shares — the one
leaf both ``gui.agent_panel`` and ``gui.api_panel`` can import without
pulling in (or cycling through) the tool panels themselves.

Split out of the single-file ``gui/tool_panels.py`` with the rest of
the package (root Rule #20, 2026-07-30); the constants themselves are
unchanged.
"""

from __future__ import annotations

# --- Aspect-ratio prompt (the standalone 'Aspect ratio…' tool) -------
ASPECT_DIALOG_ENTRY_W = 64  # px width of each W / H field in the ratio dialog

# The Advanced section's caret label (``ToolSettingsPanel.
# _toggle_advanced``). The wording predates the UI-SKETCH rework that
# retired AgentPanel's own Settings gear (owner 2026-07-29) — these two
# glyphs are the TOOL panels' Advanced header, and nothing else.
SETTINGS_GLYPH_EXPANDED = "▾  Settings"   # label while Advanced shows
SETTINGS_GLYPH_COLLAPSED = "▸  Settings"  # label while Advanced is hidden

# --- Two-column-dense settings-panel layout (owner 2026-07-21 layout
# fix — Rule #16: a settings panel with room to spare fills the width in
# TWO logical columns instead of cramming everything into the left half
# with the right sitting dead). The ToolSettingsPanel family and
# ApiImageGenPanel are ALWAYS full-width single panels, so they use it
# unconditionally. (AgentPanel used to switch into it while it was the
# sole visible site; since the UI-SKETCH rework, owner 2026-07-29, it
# lives in the setup screen's LEFT settings column and always stacks —
# see AgentPanel._stack_groups.)
DENSE_COL_GAP_PX = 16    # gap between the two columns (DESIGN.md 8pt grid,
#                          same 2-unit gap MENU_TILE_GAP_PX already uses)
DENSE_COL_WRAP_PX = 320  # wraplength for a caption/note living in ONE
#                          column instead of the panel's old full width
#                          (narrower than JOB_PANEL_BANNER_WRAP_PX, which
#                          still wraps a full-width dashboard banner)
