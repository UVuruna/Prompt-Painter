# API Panel

**Script:** [API Panel (script)](../api_panel.py) ·
**Flow:** [diagram](../__flow/api_panel.md)

## Purpose
`ApiImageGenPanel` (the paid Gemini image-API job's own settings
panel, GUI rework Phase 19) and `ApiImageAdapter` (a `SiteDriver`-
shaped stand-in over that API so the "api_image" job reuses
`SiteJobsMixin._drive_site`/`painter.runner.run_sheet` COMPLETELY
UNCHANGED). Split out of `gui/__init__.py` (root Rule #20 god-file
refactor, step 4/8).

`ApiImageGenPanel`'s INPUT is the SAME queued Collections `.md` sheet
list Website Image GEN already drives — never a folder of existing
images, so a Folder/Files picker would be actively wrong here. Faza 3
(owner 2026-08-03, UV tačka 5) put it on THE SHARED SETUP SKELETON:
LEFT = settings (the Model group on top, then the same FULL-WIDTH
BANDS `AgentPanel` stacks — owner 2026-08-03 slika 1, replacing the
2×2 grid: a `FlowRow` per band whose controls WRAP instead of being
cut off, and a full-width host below them for whichever fine-tune is
open (`ExpanderAccordion`: only one at a time). Here Run behavior,
Pacing and Prompt hold one-to-two controls each, so they share ONE
band — "objedini ih u jednu kolonu jer imaju malo elemenata" — while
the settings column takes 2/3 of the width, with the Force-Aspect
target and the Upscale gate
living under their own Pipeline switches — as `ExpandableSwitch`es
since owner 2026-08-03, folded by default and `eager=True` so the
canvas binding and the FilterEditor stack exist regardless: keeping
that fine-tune permanently open stretched this column past the window
and pushed Pacing/Prompt and the whole Start/Pause/Stop row below the
fold. `apply_settings` wraps its restore in `quiet_restore` so a
reopened panel stays folded), RIGHT = a
[Collections Column](collections_column.md) instance (queue + Output
+ Select images + Check + the Prompt+Image toggle/section — the SAME queue,
output var and mode state as the website setup screen; the host
supplies it via the `build_collections` factory, `None` in headless
tests keeps the panel self-contained). Its Start already honours the
Prompt+Image mode (`_start_api_image` passes
`reference_dir`/`require_input_image` like every site Start).
Pipeline switches ALL default ON — unlike `AgentPanel`'s own
BG/Crop/Upscale-ON-but-Aspect-OFF defaults — because the paid image
model cannot render a real transparent background. A pause RANGE
only — no action-delay pair, since that is `SiteDriver._hesitate()`'s
DOM-hesitation concept, meaningless for a pure REST call. The
Background dropdown defaults to "white" (a colour the model CAN
render, for BG removal to key out) since this panel has no
`SiteConfig` to read a site default from. `get_settings()`/
`apply_settings()` use the EXACT SAME `(stored, conditions=...)` shape
`ToolSettingsPanel`'s own round-trip already has, so the generic
`tool_panels` settings-persistence loop needs zero special-casing for
this panel.

**GATING.** The owner's key has ZERO free-tier quota for the paid
model today — a "Check API access" button makes ONE cheap REAL probe
call on a background thread (its own small private queue + a
`self.after(AI_POLL_MS, ...)` poll, mirroring `_AiDialog`'s pattern —
duplicated rather than shared via a mixin since this panel's base
class differs). A gated result sets `panel.access_gated = True`, shows
the gate message (`AI_IMAGE_GATE_MESSAGE`), and disables the Start
button; a clean probe clears the gate and re-enables Start; any OTHER
`ai.AiError` is shown but changes NEITHER state (inconclusive, never
falsely claiming OK or wrongly gating). The Start handler
(`SiteJobsMixin._start_api_image`) ALSO checks `panel.access_gated`
itself before spawning a worker — defense in depth, not the only guard.

**F5 — model discovery; faza 3 — Image ONLY, hinted.** "Refresh
models" makes its own probe (same private queue+poll pattern) and
fills ONE dropdown — the Image-generation model (owner 2026-08-03:
"podešavanja treba da budu samo za modele koje OVAJ job koristi";
the Vision pick moves to AI Check and the Text pick to New Collection
in faza 4 — their settings.json overrides stay untouched meanwhile).
The list holds image-CAPABLE models only (P3=A); a "show all (debug)"
switch widens it to everything discovered. A curated one-line hint
(`config.model_hint` — the MODEL_PURPOSE_HINTS substring registry;
honest `MODEL_HINT_UNKNOWN` for anything uncurated) shows under the
dropdown for the current selection, seeded at build from
`model_for("image")`. The combo preselects via `CTkComboBox.set()` —
which does NOT fire `command` — so only a GENUINE user pick (wired to
`_on_model_pick`) ever writes `settings.json`; a pick is persisted
IMMEDIATELY and refreshes the hint.

`ApiImageAdapter` remaps a free-tier-exhausted 429
(`ai.PaidFeatureRequired`) to `driver.TerminalState` so the EXISTING
quota-stop plumbing handles it with no new code — `retry_after_s` is
always `None` (the free-tier-zero condition is permanent, unlike a
website quota with a known reset time; it just logs "site stopped"
like any other loud non-retryable failure). Any OTHER `ai.AiError`
propagates unmapped into `run_sheet`'s generic catch-all. `new_chat`
is not implemented on the adapter at all (there is no chat to open);
there is no per-item safety-refusal analogue either — `ApiImageGenPanel`
carries no `safer_retry`/`continue_nudge` toggles at all (unlike
`AgentPanel`), so a safety-blocked call simply propagates as an
ordinary run-stopping error — a documented scope boundary, not an
oversight. `submit_with_image` (F5, owner D3) is the API-mode
counterpart of `driver.submit_with_image` — a sheet item carrying a
"← ref" input image attaches it exactly like `submit_prompt` remembers
a plain prompt; the actual call still happens in `extract_image`.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `filters` (the
  upscale gate's `FilterCondition`/`condition_to_dict`), `config`
  (background/style choices, the upscale/aspect defaults, the AI
  gate/probe message + `MODELS_SETTING`); `ai`/`driver.TerminalState`/
  `painter.settings` (imported LOCALLY inside the methods that need
  them — `_probe_access`, `extract_image`, `_refresh_models`,
  `_populate_model_dropdowns`, `_on_model_pick` — mirrors the
  original file's own lazy-import convention)
- [Aspect Ratio Canvas](aspect_canvas.md) — `AspectRatioCanvas` (the
  Force Aspect Ratio target editor)
- [Filter Editor](filter_editor.md) — `FilterEditor` (the upscale
  gate's embedded condition stack)
- [Icons](icons.md) — `icon()` (the job-logo header image)
- [Pure Logic Helpers](logic.md) — `_upscale_params_from_side_and_filter`
  (`upscale_params()`)
- [Theme Engine](theme.md) — `THEME_TOPLEVELS` (the Force-Aspect
  canvas's Day/Night repaint registration)
- [Themed Widget Toolkit](widgets.md) — `Spinner`,
  `rounded_button`/`rounded_combo`/`rounded_entry`/`rounded_switch`,
  `style_action_button`, `tk_font`
- [Layout Constants](../tool_panels/__about/layout.md) —
  `DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W` (the
  two-column-dense layout constants every control-panel family
  shares — imported from the `gui.tool_panels` package leaf, not
  `gui/__init__.py`)
- [Modal Dialogs](dialogs.md) — `AI_POLL_MS`, reached through a
  deferred `import gui` (see Design Decisions)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `ApiImageGenPanel`/`ApiImageAdapter`
- [Build Mixin](app_build.md) — `BuildMixin.__init__` builds the ONE
  `ApiImageGenPanel` (`self._tool_panels["api_image_gen"]`)
- [Site Jobs Mixin](app_jobs.md) — `_start_api_image` drives the
  panel's Start/access-gate check and hands a fresh `ApiImageAdapter()`
  to `_drive_site` in place of a real `SiteDriver` for the "api_image"
  job
- [Settings Mixin](app_settings.md) — the generic `tool_panels`
  settings round-trip drives this panel's `get_settings`/
  `apply_settings` with no special-casing

## Classes

### ApiImageGenPanel
See the Purpose section above — the paid-API job's settings panel,
including the "Check API access" gating probe (`_probe_access`/
`_arm_probe_poll`/`_poll_probe`/`_apply_probe_result`, its own private
queue+poll mirroring `_AiDialog`'s established pattern since this is a
`ttk.Frame`, not a `Toplevel`) and the F5 model-discovery row
(`_refresh_models`/`_arm_models_poll`/`_poll_models`/
`_apply_models_result`/`_populate_model_dropdowns`/`_on_model_pick`).
Both polls reach `AI_POLL_MS` through a deferred `import gui` — that
constant lives in [Modal Dialogs](dialogs.md) (`_AiDialog` owns the
poll loop it paces); see the module docstring and `gui.theme._pkg()`
for the same established late-binding idiom.

### ApiImageAdapter
A `SiteDriver`-shaped stand-in — `attach`/`close`/`await_done` are
no-ops, `submit_prompt`/`submit_with_image` only remember the prompt
text (and, for the latter, the input image path — cleared again by
the next plain `submit_prompt` so it can never leak into a following
item), and `extract_image` makes the real `ai.generate_image` call,
remapping a free-tier-exhausted 429 to `driver.TerminalState`.

## Design Decisions
See [GUI (folder)](../___gui.md)'s own "Design Decisions" section for
why the shared two-column-dense layout constants live in
`gui.tool_panels` rather than here or in `gui/__init__.py`, and why
`AI_POLL_MS` lives in [Modal Dialogs](dialogs.md) with a deferred-
import indirection here instead of a real-path import.
