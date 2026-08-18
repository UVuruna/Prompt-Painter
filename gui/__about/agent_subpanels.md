# Agent Sub-Panels

**Script:** [Agent Sub-Panels (script)](../agent_subpanels.py)

## Purpose
`AgentSubPanelsMixin` — the fine-tune sub-panel behind each of an
[`AgentPanel`](agent_panel.md) switch's expanders (owner's UI-SKETCH,
2026-07-29).

Five builders, one per `ExpandableSwitch.sub` box:

| Builder | Fills the box with |
|---------|--------------------|
| `_build_bg_sub` | BG removal's mode / colour swatch / tolerance / reach — the SAME knobs the standalone BG tool exposes, fed straight to `remove_background` |
| `_build_aspect_sub` | Force Aspect Ratio: the W/H entries two-way synced with an [`AspectRatioCanvas`](aspect_canvas.md) |
| `_build_upscale_sub` | The upscale gate: the min-side spinner + the [`FilterEditor`](filter_editor.md) stack deciding WHICH images qualify |
| `_build_checker_sub` | The parallel Checker AI's prompt-match toggle + the Fixer AI (auto-fix + api/website mode) |
| `_build_pacing_sub` | Run pacing: the Polite-pace switch and the F2 on-degrade choice |

Every one builds EAGERLY, because state like the `FilterEditor` stack
and the aspect canvas binding must outlive the expander's visibility.

Beside them live the callbacks those widgets alone use: `_pick_bg_color`
and `_render_bg_swatch` (the colour chooser and the luma-contrasted
swatch label), and `_on_force_aspect_canvas_drag` /
`_on_force_aspect_wh_typed` (the canvas ↔ entries two-way sync).

**Why it split, and why a mixin.** `gui/agent_panel.py` stood over the
structure wall at 1,051 lines with a RATCHET entry that offered two
outcomes by name — move the sub-panel builders out, or document the file
as irreducible. The owner chose SPLIT (audit
`docs/AUDIT-OOP-2026-08-18.md` → R6, 2026-08-18), and the ratchet entry
is gone: `agent_panel.py` is 841 lines.

A MIXIN rather than a plain helper module because every builder reads
and writes the panel's own tk vars and widget registry (`self._flows`,
`self.bg_mode_var`, `self.upscale_filter`, `self._force_aspect_canvas`
…) — the same composition `gui/app.py` already uses for `PainterGui`'s six
responsibility slices (see [GUI (folder)](../___gui.md)). The boundary is what the
switches OPEN INTO versus the panel ITSELF: the bands, the vars,
Start/Pause/Stop, the settings round-trip and the public readers
(`force_aspect_ratio`, `upscale_params`, `pace_floats`) all stayed in
`agent_panel.py`.

`AgentPanel` is the only user. [`ApiImageGenPanel`](api_panel.md) has
its own, differently-composed aspect and upscale sub-panels by design —
a documented divergence, not a missed reuse.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`BG_COLOR_DEFAULT`, `BG_MODE_COLOR`, `BG_MODE_LABEL`,
  `BG_REACH_LABEL`, `DEGRADE_CHOICES`, `FIXER_MODE_CHOICES`,
  `PACE_FAST_S`, `PACE_POLITE_S`, `SITES`, `UPSCALE_MINDIM_STEP`)
- [Aspect Ratio Canvas](aspect_canvas.md) — `AspectRatioCanvas`,
  `apply_typed_wh`
- [Filter Editor](filter_editor.md) — `FilterEditor` (the upscale gate)
- [Tool Panels (subfolder)](../tool_panels/___tool_panels.md) —
  `ASPECT_DIALOG_ENTRY_W`, `DENSE_COL_WRAP_PX` (read from that leaf
  module rather than `gui/__init__.py`, same circular-import reason
  `agent_panel.py` documents)
- [Themed Widget Toolkit](widgets.md) — `FlowRow`, `Spinner`,
  `rounded_combo`/`rounded_entry`/`rounded_switch`, `tk_font`

### Used by
- [Agent Panel](agent_panel.md) — `AgentPanel(AgentSubPanelsMixin,
  ttk.Labelframe)`

## Classes

### AgentSubPanelsMixin
Never instantiated alone. See the table above; each method takes the
`ExpandableSwitch.sub` box (`_build_pacing_sub` takes its band's
`FlowRow` instead — pacing has no fine-tune box of its own, its cells
go straight onto the band).
