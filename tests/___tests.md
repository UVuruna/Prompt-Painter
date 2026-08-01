# tests/

The offline half of the build — golden parser tests plus run-loop
tests over a fake driver, runnable with `python -m pytest tests`
from the project root.

## Files

### Guard Tests — `test_structure_law.py` / `test_config_sections.py` / `test_docs_coverage.py` / `test_doc_links.py` / `run_guards.py`
Project-META tests: they check the STRUCTURE of the codebase itself
(root Rule #20 THE STRUCTURE LAW, rules/CODE.md THE CONFIG SECTION
LAW, rules/DOCS.md THE DOCS LAW), not `painter`/`gui` runtime
behavior. Installed 2026-08-01 (MIGRATE-DOCS session) and wired into
`.claude/settings.json` (PostToolUse `--fast`, Stop full) via
`run_guards.py`.

- **`test_structure_law.py`** (renamed from `test_structure.py`, same
  ratchet content) — no `.py` source file over ~1,000 lines without a
  documented, owner-approved `RATCHET` entry naming why and who owes
  the split. The three TEST god-files the owner pre-approved this
  session (`test_gui_tool_panels.py`, `test_runner.py`, `test_ai.py`)
  were split and their entries removed; five entries remain
  (`gui/app_jobs.py`, `painter/driver.py`, `gui/agent_panel.py`,
  `tests/test_driver.py`, `tests/test_gui_fixer.py` — out of this
  session's scope).
- **`test_config_sections.py`** — every `painter/config/*.py` data file
  (seeded in `CONFIG_FILES`) has no module-level post-definition
  patching (`TABLE["x"] = ...` / `.update(...)` after the table's own
  definition), no duplicate dict keys, and no top-level definition
  sitting before the file's first section banner.
- **`test_docs_coverage.py`** — every source file carries the docs its
  TIER requires (`TRIVIAL_FILES`/`FLOW_REQUIRED_FILES` encode the tier
  assignment; everything else defaults to Standard/`__about`-only), and
  every code folder has its `___folder.md`.
- **`test_doc_links.py`** — every relative `.md` link across the whole
  project resolves to a real file, and every project `.md` (except
  `tests/fixtures/*.md`, sheet-format test DATA, not documentation) is
  reachable from `README.md`.
- **`run_guards.py`** — the fast wrapper both hooks call: `--fast` runs
  structure + config-sections only (right after an Edit/Write); the
  bare call runs all four (the Stop hook — a session cannot end with a
  red guard). Exits 2 on failure.

### `test_sheet_parser.py` — Golden Parser Tests
Runs the parser against the REAL archetype sheets in DOMY Watch
`research/prompts/archetype/` (all eight files). Expected values
were read from the sheets by hand, never copied from parser output:
per-sheet item/skip counts, the full trinity (title, path) tuple
set, two byte-identical prompts, the REUSE seats of the persons
sheet, the unapproved tetramorph section, wrapped-heading
normalization (calendar) and the two Life registers that share
stems. The `fixtures/` sheets cover the loud failures: an unpaired
heading, a missing H1 (`SheetError`), escaping and non-image drop
paths. Skips (with a clear reason) if the DOMY Watch sheets are not
on disk.

### Run-Loop Tests — `test_runner_paths_and_save.py` / `test_runner_images.py` / `test_runner_recovery_ladder.py` / `test_runner_queue_and_control.py`
Drives `run_sheet` with a duck-typed fake driver and a temp out
folder — no browser. Split by concern from the former `test_runner.py`
god-file (root Rule #20, second round, 2026-08-01 — same 47 tests,
same fixtures duplicated per module rather than shared, see each
file's own docstring):

- **`test_runner_paths_and_save.py`** — `dest_for`/`versioned_dest_for`/
  `prompt_suffix` (the output-path contract), and the plain save/report/
  resume path: the per-site rule suffix on every submitted prompt
  (Gemini's three laws, ChatGPT without them), the direct
  `<out>/<drop-path>` layout, the report txt (header, per-image lines
  with resolution and postprocess actions, averages, totals, stop
  reason), safer-retry recovery and the copyright reframing.
- **`test_runner_images.py`** — input-image items (`← ref`, owner
  2026-07-23: `submit_with_image`, the missing-input loud skip, the
  escalation re-attach) and the ChatGPT continue-nudge stall recovery
  (F1: `NoImage` with `had_text=True` is ALWAYS a loud per-item skip,
  never nudged — the market-scene incident).
- **`test_runner_recovery_ladder.py`** — the `ImageGenFailed` recovery
  ladder (BUG 3, owner 2026-07-21 + escalation 2026-07-23): native
  Retry button → paced "retry" resends → escalation rounds (refresh →
  new session → whole prompt), an `ItemRefused` surfacing INSIDE the
  ladder handled like a first-attempt refusal (F1, owner 2026-07-29),
  and the F1 duplicate-bytes guard (one fresh re-submit, then a loud
  skip).
- **`test_runner_queue_and_control.py`** — refusals/advice/resume/redo
  queue semantics (resume by FILE EXISTENCE, a ticked `only` REGENERATES
  as the next `_vN` version, `extra_suffix`'s fix note), and run
  control: the graceful stop flag, the `post_save` hook (a failure is
  loud, counted, never fatal), `TerminalState` propagation (the parsed
  quota reset time), and F2 model degradation — `on_degrade` gets a
  choice on a `ModelDegraded` ("continue" loud-skips the item, anything
  else re-raises as `TerminalState` with the same `retry_after_s`),
  plus a pin on the F2-retimed ladder constants read straight from
  `painter.config` (never `painter.runner`'s copies, which the autouse
  fast-recovery fixture monkeypatches).

### `test_driver.py` — CDP Driver, F1/F2 Protocol
Duck-typed Locator/Page fakes over `SiteDriver` (no browser — see the
module's own docstring for the exact fakes). The F1 turn-based
protocol (owner 2026-07-29): a submit is not "sent" until CONFIRMED
(composer emptied + our text is the newest user turn, via the shared
`_wire_send_flow` test helper), `await_done`/`extract_image` are
scoped to a pre-submit `Baseline` (turn count + last image src) so a
leftover busy button or the PREVIOUS item's image can never be
mistaken for OUR result, a busy signal stuck from the previous item
gets a page refresh BEFORE the next send, and a garbled paste gets
one silent retype. F2 model degradation: Gemini's
`degrade_banner` selector (ChatGPT has none) is checked BEFORE the
image-failed/refusal/quota markers in both `await_done` and
`extract_image`, raising `ModelDegraded` with `retry_after_s` parsed
from the banner's own absolute-moment text — and, with no banner
wired, the ordinary quota classification still fires unchanged.

### Gemini Client + AI Flows — `test_ai_client.py` / `test_ai_sheet_flow.py` / `test_ai_checks.py` / `test_ai_flags.py`
NO live API anywhere: the HTTP layer is the monkeypatched
`painter.ai.client._urlopen`. Split by `painter/ai/` submodule from
the former `test_ai.py` god-file (root Rule #20, second round,
2026-08-01 — same 80 tests, one module per package module):

- **`test_ai_client.py`** — the client's request building (url +
  model, `x-goog-api-key` header, contents/systemInstruction payload,
  base64 `inlineData` for images), the tolerant candidates/parts
  response parsing, the loud failure taxonomy (`AiError` on HTTP
  errors with the API's own message, prompt blocks, non-STOP finishes,
  malformed shapes; `NoKey` on a missing/blank key BEFORE any network
  traffic), the transient-error retry/backoff, the free-tier pacing
  sleep, API image generation + the reference-image path, and model
  discovery/recommendation (`list_models` pagination, `capable_models`,
  `recommend_model`, `model_for`'s settings override).
- **`test_ai_sheet_flow.py`** — the sheet-generator flow with a mocked
  `gen` (questions parsing + cap, skipped answers, the whole-file fence
  unwrap, real-parser validation, exactly ONE repair round, the
  still-broken path that must NOT load, slugged collision-free saves).
- **`test_ai_checks.py`** — the checker's strict OK/DEFECTS format, the
  Fixer AI's `build_fix_prompt` (GUI rework Phase 20 — pure, defects
  become bullets, an empty list still returns a non-blank fallback, raw
  appended verbatim when given and omitted when blank), the per-image
  checker orchestrator (`check_one_image`, pairing over a batch), and
  the re-send reverse mapping (`drop_and_site_for`, `plan_resend` —
  per site / per sheet, each item its own fix note, loud unmatched
  reasons).
- **`test_ai_flags.py`** — the flag memory (round-trip, merge, clear,
  the mtime-based prune of regenerated/missing files, relative-vs-
  absolute keys).

### `test_quota_reset.py` — Quota Reset Parsing
`parse_quota_reset` against the LIVE-captured ChatGPT quota
messages (minutes and hours), short units, Serbian phrasings, and
the no-time Gemini message (None, never a guess); plus the
`TerminalState.retry_after_s` field itself. F2 (owner 2026-07-29)
adds the ABSOLUTE banner phrasing ("... resets on Jul 25 at 2:18
PM"): a positive real offset (the exact seconds are not
reproducible — the moment may roll to next year), a message
carrying BOTH phrasings still uses the RELATIVE sum, and text naming
no month/day/time stays `None`.

### `test_postprocess.py` — Split Postprocess Steps
Synthetic images through the two composable steps:
`remove_background` (white plate cleared without cropping, already
transparent → nothing, ambiguous → unclear and untouched, broken
file → loud) and `crop_transparent` (content box + safety margin,
second pass already tight, opaque/fully-transparent → nothing,
margin clamped at the edge).

Also the BACKGROUND MODE block (owner 2026-07-28): hex parsing and
its loud failures, the owner's own `± X %` worked example
(`#FF0000 ± 6.67 %` = 17 levels), `0 %` keying the colour EXACTLY, a
colour that is neither white nor black cleared once STATED, the
tolerance bounding what counts as background, forced modes overruling
the border sniff, an already-transparent image skipped in EVERY mode,
and the "unclear" report naming the colour it saw.

The REACH choice gets a group built on a synthetic letter "O" (a ring
whose COUNTER is pure `#000000`, exactly like the background): edge
reach keeps that counter opaque while clearing the outer void — the
flood fill cannot walk through the stroke — and `BG_REACH_ALL` clears
it too, leaving an outline. Plus: everywhere always removes at least as
much as edge, the choice really reaches the engine through
`remove_background`, and meeting the SAFETY guard because of it is a
NAMED report, never a silent no-op.

The FOUR-CORNER auto-colour vote gets its own group: auto clearing a
colour the corners agree on (and LOGGING which), the vote ignoring a
subject that runs to an edge (the reason it is corners and not the
border band), refusing when the corners disagree, tolerating corner
noise up to `AUTO_CORNER_AGREE_MAX`, and — the important negative —
never overriding the white/black sniff, so the pointers plates keep
the black recipe and its own guard. Its REGRESSION pin (root
Rule #25) is
`test_pointers_regression_black_guard_bails_custom_colour_succeeds`:
a disc on pure black whose LEGITIMATE background is ~42 % — black's
0.40 guard bails on it (message naming the guard) while the stated
colour goes through. That geometry is the owner's real "pointers"
folder in miniature (17 plates, 41.2–42.2 %).

### `test_upscale.py` — Upscale Gating
The locked gate (aspect 0.9–1.1 AND a dimension under 800) against
a MOCKED binary: non-square and big-enough images never touch the
exe, small squares upscale native-4x and LANCZOS-land exactly on
the target, tiny sources stay honestly below. The last test drives
the REAL downloaded binary (skipped when `tools/realesrgan/` is
absent).

### `test_jobtemp.py` — Job Temp / Restore + Measure
Synthetic PNGs through [Job Temp](../painter/__about/jobtemp.md): a
backup→restore_one byte round-trip, `drop` removing a no-op backup,
`restore_all` reverting every backed-up file, `clear`/`clear_all`
wiping the slot / whole root, a fresh `JobTemp` wiping a stale slot,
and `measure` for all four kinds — bg (% removed pixels), crop (% area
reduction), upscale (% area increase) and aspect (% deformation),
including the LARGER-axis stretch case where a naive "smaller side
only" reading would wrongly report 0.

### `test_settings.py` — Settings Persistence
Missing file → `{}`, atomic roundtrip, corrupt and non-object JSON
→ loud stderr but `{}`, never a crash.

### `test_config.py` — Config Helpers
Pure-data checks with no tkinter import: the per-theme solid-button
shades (day differs from night, the neutral is LIGHT on day), the
`fmt_op_duration` / `fmt_pct` formatters, `selection_base_and_rels`,
`iter_images`, the STYLE clause table, and the dashboard STATUS
BADGE mapping (owner 2026-07-20) — `badge_keys_for` awards a badge
only on a `done` step (never nothing/unclear/FAILED), adds `retry`
from the flag, renders in `BADGES` order, and the badge tables stay
mutually consistent. Also the Main Menu's `MENU_TILES` (GUI rework
Phase 10) — the 8 required ids are present and unique, every tile has
a label/description and an icon stem that resolves to a real file
under `assets/icons/`, only `api_image_gen` is disabled, and
`MENU_TILE_RADIUS` matches DESIGN.md's card-radius bracket (16). Real
`MainMenu`/`_view` Tk wiring gets a screenshot, not a pytest — see
gui.py's own "barely Tk-unit-tested by design" convention below. GUI
rework Phase 11 adds `TILE_JOB_KINDS` coverage — every `MENU_TILES` id
has an entry, every kind it lists is a real `JOB_ORDER` member,
`website_gen` maps to both gen sites, the two AI dialogs map to `()`,
and (the inverse check) every `JOB_ORDER` kind is reachable from some
tile. GUI rework Phase 15 adds `tile_for_kind` (the REVERSE lookup
behind `PainterGui._tool_panel_key`) — the four standalone tools
resolve to themselves, `"aicheck"` resolves to `"image_checker"` (the
one kind whose MENU_TILES id differs from its JOB_ORDER slot), and a
multi-kind tile's own kinds (chatgpt/gemini) or an unknown kind both
return `None`.

### `test_aspect.py` — Change-Aspect Deform
The grow-only stretch rule, already-at-ratio byte-unchanged no-ops,
the optional input filter (off / IF / IF NOT) and loud failures. Plus
(GUI rework Phase 5) the visual editor's pure helpers: `reduced_ratio`
(gcd reduction, e.g. 1920×1080 → (16, 9), an already-coprime pair
unchanged) and `decimal_ratio_label` (standard-rounded decimal, e.g.
1920×1080 → "1.778:1", the configured-decimals default and an
explicit override), both rejecting a non-positive side loudly.

### `test_viewer.py` — Viewer Helpers
The before/after transparency checkerboard (`_checkerboard` /
`_has_alpha` and the composite promise) and the folder-scoped
restore set (`rels_in_folder`). GUI rework Phase 9 added
`_filmstrip_stages` (the per-step restore viewer's pure list-builder,
over a REAL `JobTemp`): the ordered `(label, path)` pairs — every
named pipeline stage that still holds a backup, in `JOBTEMP_STEP_NAMES`
order, followed by exactly one final `(Current, live_path)` entry —
skips a stage with no backup (never gap-fills), collapses to
`[(Current, live_path)]` alone when nothing was ever backed up, and
the documented `stages[:-1]` <-> `steps_for(rel)` one-to-one zip
contract `StepRestoreWindow._render` relies on.

### `test_smooth_transition.py` — Snapshot-Cover Fallbacks
The shared `gui.smooth_transition` helper headless (owner
2026-07-20): the mutate callback runs EXACTLY ONCE with no root, an
unmapped/unviewable root, or a failing cover; the covered path
forces the overlay painted BEFORE the mutate and fades after (theme
timing passes through); a mutate exception propagates loudly while
the overlay still fades — never a stuck cover, never a masked error.

### `test_filters.py` — Shared Filter Framework
[Shared Filter Framework](../painter/__about/filters.md)'s `matches()` on
synthetic `(width, height)` ints, no images: one test per kind (aspect
exact, aspect range, any side, width, height), IF vs IF NOT for each,
several conditions ANDed together (a mixed IF/IF-NOT stack, and one
failing condition vetoing an otherwise-passing stack), the empty-list
"matches everything" default, the exact-aspect `lo == hi` edge (no
hidden epsilon — an off-ratio image by one pixel misses it), the "any
side" both-extremes-at-once semantics (portrait/landscape judged
identically; one outlier axis fails even when the other is in range),
and loud `ValueError` on an unrecognised kind/polarity. GUI rework
Phase 4 added the JSON-safe (de)serializer pair: `condition_to_dict`'s
four flat fields, a REAL `json.dumps`/`loads` round-trip (not just a
dict compare), `condition_from_dict` as the exact inverse across every
kind/polarity combination, int-to-float coercion for a hand-edited
settings.json, and loud `KeyError`/`ValueError` on a missing field or
an unparsable bound.

### `test_gui_filters.py` — FilterEditor + the Aspect-Filter Migration
GUI rework Phase 4. Two halves: the settings migration
(`gui._migrate_legacy_aspect_filter`) is pure and Tk-free — the
owner's REAL saved dict (`{"from": 0.9, "to": 1.1, "mode": "IF NOT"}`)
becomes exactly one `FILTER_KIND_ASPECT_RANGE` condition with the same
numbers/polarity, `off`/a missing mode becomes an empty list, an
unrecognised mode raises loudly, and `gui._parse_condition_dicts`
drops (never crashes on) a malformed condition dict with a log line.
`FilterEditor` itself is a REAL `ttk.Frame`/CTk widget — the suite's
FIRST tests to construct one for real, sharing `conftest.py`'s
session-scoped `tk_root` (see its docstring for why a second,
independently created-and-destroyed root breaks gui.py's process-
lifetime icon cache: `TclError: image "pyimageN" doesn't exist`).
Covers `get_conditions()`/`set_conditions()` round-tripping (empty,
seeded-at-construction, multiple mixed kinds, replace-not-append), a
row-level `ValueError` on an unparsable or inverted bound, the
"Aspect (exact)" tolerance-band round-trip (`lo`/`hi` widen by
`FILTER_ASPECT_EXACT_TOL` on read-out, centred on the original ratio,
and the widened band actually matches a real 1000x1001 near-square),
and the preset Save/Load/Delete cycle — the caller's OWN injected
`presets` dict sees the mutation, the `on_presets_changed` callback
fires exactly once per Save/Delete, and the widget still works with
neither injected (a private in-memory dict).

### `test_gui_upscale.py` — Upscale Gate Simplification
GUI rework Phase 6: the old four-field gate (min W / min H / aspect
FROM / aspect TO) collapses into one min-SIDE spinner plus an embedded
`FilterEditor`. `_upscale_params_from_side_and_filter` (pure) folds a
seeded/stacked condition list's first IF-aspect row into
`upscale_if_small`'s `aspect_min`/`aspect_max`, widening to `(0, inf)`
when there is none to fold (no aspect row, only non-aspect conditions,
or an IF-NOT aspect row that cannot be expressed that way) and taking
the FIRST IF-aspect match when several are stacked — documented
partial behaviour, cross-checked against the real `upscale_if_small`
engine (a mocked binary) so the resolved kwargs actually reproduce the
old default gate's verdicts. `_gate_and_upscale` (the per-image
site-pipeline gate) skips the engine entirely on a failing stacked
condition the simple kwargs cannot express, calls it unconditionally
on an empty filter, and runs it normally when the filter passes.
`_migrate_legacy_upscale_gate` converts both the owner's REAL per-agent
string shape and the standalone tool's shape into the new
`{min_side, conditions}` form (the round-tripped condition reproducing
the exact old gate), the shipped defaults, and raises loudly on an
unparsable value. `AgentPanel`'s new `up_minside_var`/`upscale_filter`/
`upscale_params()`/`upscale_conditions()` get a real (withdrawn) Tk
root — the regression guard that a freshly built panel's resolved
params equal the OLD hardcoded defaults, a `ValueError` from a bad
min-side or an invalid filter row propagating through unmodified (Start
relies on this), and `get_settings`/`apply_settings` round-tripping
both fields (a missing/None `upscale_conditions` keeps the widget's own
seeded default, never crashing).

### `test_gui_pipeline.py` — Pipeline Reorder + Force Aspect + Per-Step Backups
GUI rework Phase 8 (plus a Phase 9 addition — see below): the post-save
order becomes BG → Crop → Aspect(force) → Upscale, and the two gen
SITES gain their own `JobTemp` (new plumbing — previously only the four
standalone tools had one). `gui._run_pipeline_steps` is the pure-ish,
Tk-free per-image engine, tested directly with fake `path -> status`
step functions: dedup of the FIRST enabled step's pre-state into
`step="original"` (never both), `"original"` surviving even when that
first step is a no-op, a LATER step's own named backup dropped on a
no-op result, the disk-cap fallback (new per-step backups stop, one
`on_cap()` per SKIPPED backup, `"original"` still always taken) and the
"keep every step" toggle producing the identical original-only outcome
SILENTLY (never `on_cap`). `PainterGui._compose_post_save` itself runs
through a small duck-typed `FakeGui` (`.agents`/`._job_temps`/`._q` —
the only attributes it touches) carrying a REAL `AgentPanel`: the
ordered action string with all four steps on, the correct subset with
some off, and the CRITICAL byte-identical-output regression guard (with
Force Aspect off, and separately with a JobTemp newly attached) — proving
the new backup plumbing is purely additive. One REAL end-to-end test
drives the actual engine functions (bg_remove/crop/aspect/a MOCKED
upscale binary) through the full pipeline and cross-checks the result
against calling the four engine functions directly in the same order,
plus the exact backup set under `__steps__` and `restore_to` round-trips
for the pristine baseline AND a middle stage. `AgentPanel`'s
`force_aspect_var`/`force_aspect_w_var`/`force_aspect_h_var`/
`keep_all_steps_var` (defaults, a bad-value `ValueError`, the embedded
`AspectRatioCanvas` drag/typed two-way sync, `apply_theme`/
`THEME_TOPLEVELS` registration, settings round-trip) and `DashPanel`'s
new loud, PERSISTENT "over_cap" banner (survives further progress
events, unlike the muted `state_var`; only `reset()` hides it again)
round out the GUI-facing half. GUI rework Phase 9 adds `DashPanel`'s
`jobtemp`/`out_base` wiring and its "Steps…" button
(`_show_steps`/`refresh_image_row`): the three info-dialog guards (no
row selected, no JobTemp yet, no kept stages for this rel) via a
monkeypatched `messagebox.showinfo` — never a real blocking dialog —
and the happy path via a monkeypatched `gui.StepRestoreWindow`
capturing its call args (rel resolved through `dest_for`, the panel's
own live JobTemp/live path, and an `on_restored` callback that is
`refresh_image_row` itself, proven by calling it and checking the row's
`res` column updates); `refresh_image_row` re-reads a row's resolution/
size straight off disk and is a no-op for an unknown drop path.

### `test_gui_running_view.py` — Running View (Icon Bar + Start/Pause/Stop)
GUI rework Phase 11. Two halves: `gui._next_view(current, active_count,
menu_requested=False)` is the pure, Tk-free view-transition decision —
tested directly (no GUI at all) for every rule the binding design doc
states: any active job forces `"running"` from `"menu"`/`"main"`; it
STAYS `"running"` through every active count including a drop to zero
(Stop of the last job never auto-navigates by itself); a Menu click is
honoured ONLY once `active_count == 0`, refused otherwise; idle
`"menu"`/`"main"` are left alone. The `PainterGui` methods that consume
it (`_active_kinds` / `_active_tile_ids` / `_sync_running_state` /
`_apply_running_layout` / `_request_menu` / `_click_icon_bar_tile` /
`_tile_handler` / `_toggle_pause_job`'s new reveal) run for REAL
through a small duck-typed `FakeGui` (the SAME convention
test_gui_pipeline.py's own `FakeGui` uses for `_compose_post_save` —
never a full `PainterGui`, whose `__init__` is too heavy for a unit
test) — the running-view methods this needs (`_active_kinds` etc.) are
ALIASED onto `FakeGui` as class attributes rather than reimplemented,
so `self._active_kinds()` calls inside an unbound `PainterGui` method
resolve correctly even though `self` is the fake. Covers: entering
`"running"` on the first job, never leaving it on its own when a job
finishes, the IconBar recolouring on both, `_apply_running_layout`'s
controls-box-only-while-website_gen-inline packing (and never showing
a stale collapsed strip), `_request_menu`'s refuse-while-active status
hint, `_click_icon_bar_tile`'s branches (already-active → focus
Dashboard, website_gen → toggle the real inline `_controls_box`, every
standalone-job tile → `_tile_handler`'s `_open_tool_panel` fallthrough,
`ai_sheet_gen` → its dialog handler — shared with `_select_tile`, one
mapping, not two), and `_toggle_pause_job`'s Phase 11 addition (pausing
a SITE reveals the website_gen panel; pausing outside `"running"` is a
no-op; Resume never hides it again). `IconBar` itself gets real-widget
checks: one button per `MENU_TILES` id, only `api_image_gen` starts
disabled, a click calls `on_select` with the tile id, the Menu button
calls `on_menu`, and `set_active` fills/outlines buttons via their
`border_width` (0 filled / 1 outline) — never touching the disabled
placeholder.

GUI rework Phase 13 adds `_tool_panels`/`_open_tool_panel` coverage
(BG/Crop's own persistent panel, a real `_RecordingToolPanel` stand-in
per slot so pack/pack_forget is exercised for real) — `_select_tile`'s
own bg/crop shortcut straight to `"running"` (skipping the `"main"`
hop every other tile takes) and `_toggle_pause_job`'s matching reveal;
Phase 14 widens the SAME dict/tests to upscale/aspect, no new branch
in any caller; Phase 15 widens it a FIFTH time to the AI checker
(keyed `"image_checker"`, its MENU_TILES id, NOT its `"aicheck"`
JOB_ORDER slot) and adds `_tool_panel_key`'s own alias onto `FakeGui`
— `_select_tile("image_checker")`/`_click_icon_bar_tile("image_checker")`
now open its panel the identical bg/upscale way, and pausing
`"aicheck"` reveals `_tool_panels["image_checker"]`, proving the
tile-id/slot bridge for real (the pre-Phase-15 stub that called a fake
`_start_ai_check()` directly on a tile click is deleted along with the
production behaviour it stood in for).

### `test_gui_agent_visibility.py` — Per-Site Show/Hide + the Fine-Tune Expanders
GUI rework Phase 12 + the UI-SKETCH rework (owner 2026-07-29).
`gui._visible_agent_slots(order, visible)` is the pure, Tk-free slot
resolver behind `PainterGui._relayout_agents`: both visible keep their
order, hiding either one leaves the survivor compacted into slot 0
(never stranded in slot 1 with a dead gap beside it), both hidden is a
legal empty result, and a missing key defaults visible (matches
everything). A slot is a ROW since the sketch's left-settings/
right-input split. `AgentPanel`'s new
`visible_var`/`build_visibility_toggle`/`set_run_state` get a real
(withdrawn) Tk root (the SAME `make_panel` convention
test_gui_upscale.py/test_gui_pipeline.py already established): the var
defaults True, is in `_PERSIST`/`_vars()`, and round-trips through
`get_settings`/`apply_settings` (a missing key on an old settings.json
keeps the default, like every other field); `set_run_state` tolerates
no toggle built yet (the real `__init__` order — PainterGui calls
`build_visibility_toggle` only AFTER construction), greys the toggle
out while `running` OR `pending_restart` (the same window Stop already
uses), and — the one genuinely stateful behaviour — forces a HIDDEN
panel's `visible_var` back to True and calls `on_log` exactly once on
the False→True transition (never on an already-visible run, never
without `on_log` passed — defaults to a harmless no-op, so every OTHER
test file's own headless `make_panel` stays unaffected). The
retired Settings gear is proven GONE (no `settings_collapsed_var`, no
`_toggle_settings`, no `_finetune_box`, no `settings_collapsed` in
`_PERSIST` — Rule #6 leaves no stump), and the WIRING of the
per-switch expanders is pinned here (the primitive's own mechanics
live in test_gui_widgets.py): BG removal / Force aspect ratio /
Upscale / AI checker each own their sub-panel and the switch-less
Pacing section exists, all start collapsed, an eager sub-panel's state
(`upscale_params()`, `force_aspect_ratio()`) works before the first
expand, an OFF→ON click auto-expands, OFF hides, and `apply_settings`
never auto-expands a restored-ON switch (the live-window defect:
without `quiet_restore` the app opened with every ON switch unfolded).
`on_layout_change` fires once per toggle AFTER the pack/forget, for
both the switch and the Pacing section, and defaults to a harmless
no-op. `PainterGui._relayout_agents` itself runs unbound against a
small duck-typed `FakeGui` carrying REAL `AgentPanel`/`ttk.Frame`
widgets in the SAME two-container shape production uses (a
grid-managed `_agents_frame` and a pack-managed compact strip — Tk
refuses to mix managers on one parent): both visible grids/packs both,
hiding either removes ONLY that one (panel AND its collapsed-strip
cluster) and leaves the survivor's row untouched or compacted to 0 as
appropriate, and re-showing both re-enters the F4c shared editor.

### `test_gui_widgets.py` — ExpandableSwitch / ExpandableSection / quiet_restore
The UI-SKETCH primitives in `gui/widgets.py` (owner 2026-07-29) — the
only widgets in that file with behaviour of their own (the rest are
colour/geometry factories, screenshot-verified). `ExpandableSwitch`:
an OFF switch has no sub-panel and no caret; an already-ON one starts
COLLAPSED (a restored setting must open compact); a live OFF→ON
auto-expands ONCE; the caret folds/unfolds without touching the
switch; OFF hides the sub-panel and the caret; expanding while OFF is
refused; a redundant expand is a no-op (no second `on_layout_change`),
as is turning an already-collapsed switch off; `build_sub=None` is a
plain switch; the sub-panel builds LAZILY on the first expand, or at
construction with `eager=True` and is never rebuilt.
`ExpandableSection` (the switch-less Pacing row) toggles both ways,
swaps its ▸/▾ head text and reports each change. `quiet_restore` keeps
a restored-ON switch folded, still hides a sub-panel whose switch is
restored OFF, releases after the block — and releases even when the
block raises.

### Standalone-Tool Settings Panels + Stop — `test_tool_panels_base.py` / `test_tool_panels_bg.py` / `test_tool_panels_geometry.py` / `test_tool_panels_image_checker.py`
GUI rework Phase 13 (`BgSettingsPanel`/`CropSettingsPanel`) through
Phase 15 (`ImageCheckerSettingsPanel`), over the shared
`ToolSettingsPanel` base. Split by `gui/tool_panels/` module from the
former `test_gui_tool_panels.py` god-file (root Rule #20, second
round, 2026-08-01 — same 98 tests):

- **`test_tool_panels_base.py`** — the BASE contract, exercised through
  concrete panels purely as instantiation vehicles: module-level
  `gui._filter_files` (the shared pre-filter, real tiny PNGs on disk),
  the Advanced-override field parsers (`_parse_fraction`/
  `_parse_nonneg_int`/`_parse_int_range`), `resolve_input()`/
  `get_conditions()`, run-state/pause/Advanced-collapsible reflection,
  the generic settings-round-trip fallback, and
  `PainterGui._start_tool_from_panel`/`_stop_tool`/`_run_tool_job` — the
  pre-filter path end to end through a duck-typed `FakeGuiForPanel`
  (`_run_tool_job` a RECORDING stand-in) plus its own `should_stop`
  halting the loop BETWEEN images (mirrors
  `test_runner_queue_and_control.py`'s own
  `test_stop_flag_stops_between_items`).
- **`test_tool_panels_bg.py`** — `BgSettingsPanel`'s own fields: the
  Advanced safety-fraction overrides reaching `remove_background`, the
  mode block (owner 2026-07-28 — chosen mode/colour/tolerance reaching
  the engine call, a mistyped colour raising at Start and being
  HARMLESS in a mode that ignores it, the colour fields packed only in
  Custom mode, the guards typed as PERCENT still reaching the engine as
  FRACTIONS, the REACH dropdown, the swatch click opening a
  monkeypatched color chooser), the settings round-trip (MODE/REACH
  KEYS, an unknown stored value falling back), and the UNIT MIGRATION
  pin (a fraction-build settings file's `"0.40"` must fall back to the
  40% default, never misread as a 0.4% guard).
- **`test_tool_panels_geometry.py`** — `CropSettingsPanel`/
  `UpscaleSettingsPanel`/`AspectSettingsPanel` (all three live in
  `gui/tool_panels/geometry.py`): Crop's margin/ink-alpha overrides
  reaching `crop_transparent`, Upscale's min-side reaching
  `upscale_if_small` (cross-checked against
  `test_gui_upscale.py`'s own resolution table), Aspect's target-ratio
  W/H entries + canvas two-way sync reaching `change_aspect`, and each
  panel's own settings round-trip.
- **`test_tool_panels_image_checker.py`** — `ImageCheckerSettingsPanel`:
  no Advanced section, the read-only `_picker_title_suffix` (never
  claims "runs IN PLACE"), the OPTIONAL `sheets_path()` second input
  (F6, REWORK.md, owner E2), `gui.app_tools._sheet_prompt_map` (the
  pure drop_path→prompt builder over a sheet file or folder),
  `PainterGui._start_ai_check`'s OWN pre-filter path through a
  SEPARATE `FakeGuiForAiCheck` (a different fake from
  `_start_tool_from_panel` because the AI checker's Start does not
  share `_launch_tool_worker`), **Stop** reusing `_stop_tool` VERBATIM
  keyed `"aicheck"`, `_run_ai_check_job`'s own `should_stop` halting
  BETWEEN checks with `painter.ai.check_one_image` monkeypatched (no
  network, no API quota spent), and the F6 two-input flow (a
  `sheets_path` narrows the check to only images whose reversed drop
  path matches a sheet entry, WITH that entry's prompt; no
  `sheets_path` keeps every image quality-only).

### `test_gui_checker.py` — Checker AI, Parallel Per-Item Check
GUI rework Phase 16. Four halves: `AgentPanel`'s new `checker_var`
(default OFF — a real Tk root, the SAME `make_panel`/`root` convention
as every other GUI-phase file — in `_PERSIST`/`_vars()`, round-trips
through `get_settings`/`apply_settings`, a missing key on an old
settings.json keeps the default); the SHARED module-level report
helpers `ai_check_tag` (pure — flagged is the CHANGED tag, ok/error
both SKIP) and `ai_check_image_file` (promoted from `AiCheckPanel`'s
own private `_file_for`, relative-joins/absolute-passthrough), plus a
Rule #5 proof that `AiCheckPanel`'s double-click viewer and
`DashPanel`'s new 'Check…' viewer render the IDENTICAL report (both
monkeypatched `DocWindow` calls compared byte-for-byte) for the
identical checked image; `DashPanel`'s new check-status column
(`item_checking`→"checking…", `item_checked`→"OK"/"flagged N"/"error"
+ the shared tag, an unknown/late row a silent no-op like `item_done`
already tolerates) and `_check_results`' lifetime (survives a
`sheet_start` new-collection reset, unlike `_child_ids` — cleared only
by `reset()`, mirroring `_node_info`) plus `_show_check`'s three states
(no row selected / no result yet / the happy path opening a real
DocWindow, monkeypatched — same convention test_gui_pipeline.py's own
`_show_steps` tests use); and `PainterGui._maybe_spawn_checker`/
`_run_checker_one` run for REAL through a small duck-typed
`_FakeGuiForChecker` (`.agents`/`.panels`/a real `queue.Queue` —
`_run_checker_one`/`_maybe_spawn_checker` themselves ALIASED onto the
class, the SAME test_gui_running_view.py convention, so `self.
_run_checker_one(...)` inside the unbound `_maybe_spawn_checker`
resolves) carrying a REAL `DashPanel`: checker OFF is a deterministic
no-op (returns before touching the queue or starting any thread, so no
sleep is needed to prove it); checker ON marks "checking…"
SYNCHRONOUSLY then a mocked `painter.ai.check_one_image` (no network,
no API quota spent) posts `item_checked` back onto the queue, awaited
with a bounded `Queue.get(timeout=...)` — never a sleep loop — for the
ok/flagged/error(NoKey-shaped) cases alike; a non-site key and a panel
with no `out_base` yet are both no-ops; `_run_checker_one`'s OWN outer
safety net is proven by mocking `check_one_image` to RAISE directly (an
`OSError`, simulating a file vanishing mid-race) — the posted event is
still a graceful 'error', never an unhandled thread exception; and
`PainterGui._dispatch` itself is proven to route `item_progress` (and
ONLY that event type — NOT `item_done`, NOT a tool panel's own events)
through the spawn.

### `test_gui_fixer.py` — Fixer AI Wiring
GUI rework Phase 20. Mirrors test_gui_checker.py's own structure. Six
halves: `AgentPanel`'s new `fixer_var`/`fixer_mode_var` (defaults,
`_PERSIST`/settings round-trip, visibility tied to `checker_var` via
`winfo_manager()` — the withdrawn shared root makes `winfo_ismapped()`
unusable); `gui._fixer_decision`'s pure branch table (fixer off; not
flagged; empty defects; api mode; website mode) against a bare
duck-typed switches stand-in, no Tk; `PainterGui._maybe_spawn_fixer`/
`_run_fixer_api`/`_queue_website_fix` run for REAL through a
`_FakeGuiForFixer` (mocked `ai.edit_image`, a REAL `JobTemp` proving
the `step="fixer"` backup, a bounded `_wait_for_event` wait for the
background thread's `item_fixed` past any log lines that precede it,
and — the core physical-constraint proof — website mode monkeypatches
BOTH `ai.edit_image` and `driver.SiteDriver` to raise if EVER touched,
plus proving the queued item lands in `AiCheckPanel._flagged` and
`DashGrid.add("aicheck")` fires); `_dispatch` routing `item_checked`
(and ONLY that type) into the fixer; `PainterGui._build_fix_workers`'s
site resolution (an explicit `jobtemp_slot` vs the
`ai.drop_and_site_for` fallback, `"api_image"` correctly getting no
website worker) and `_run_image_fix`/`_run_website_fix`'s gate/success
paths (a duck-typed fake `SiteDriver` proving the attach ->
submit_with_image -> await_done -> extract_image -> close call SEQUENCE
and that it is ALWAYS closed, even on `AttachNotConfigured`; "site
currently running"
refuses WITHOUT ever constructing a driver); and `gui._fix_result_ui`'s
pure result-to-UI mapping behind `DocWindow._apply_fix_result`
(Tk-free — no test in this suite constructs a real `tk.Toplevel`) plus
`DashPanel._show_check`/`AiCheckPanel._on_activate` passing fix workers
into `DocWindow` only when the report actually carries defects.

### `test_gui_degrade.py` — F2 Model-Degradation Choice
`AgentPanel`'s new `degrade_var` (ask/continue/wait, persisted key
"degrade") — a real (withdrawn) Tk root, the same `make_panel`
convention every other GUI-phase file uses: defaults to "ask", is in
`_PERSIST`/`_vars()`, round-trips through `get_settings`/
`apply_settings`, a missing key on an old settings.json keeps the
default; plus `cooldown_var` (the info-only reset-time label beside
the site name, never gating Start) defaulting to empty. The deeper
F2 plumbing — `PainterGui`'s "site_cooldowns" persistence, the 30s
`_refresh_cooldown_labels` poll, the `"__ask_degrade__"` queue
message — needs a full `PainterGui`/real timers and stays outside
this offline suite, same as the rest of the "barely Tk-unit-tested
by design" surface.

### `conftest.py` — Import Path + Shared Tk Root
Makes the `painter` package importable from any pytest invocation.
Also the session-scoped `tk_root` fixture (GUI rework Phase 4) — ONE
real, withdrawn, never-mainloop'd `tb.Window` every Tk-constructing
test in the suite shares (see its docstring for why a second
independent root breaks gui.py's icon cache).

### `fixtures/` — Contract-Violation Sheets
`unpaired.md`, `no_h1.md`, `bad_paths.md` — tiny synthetic sheets,
one violation each.

## Connections

### Uses
- [Sheet Parser](../painter/__about/sheet_parser.md),
  [Run Loop](../painter/__about/runner.md), [Shared Filter
  Framework](../painter/__about/filters.md) and [GUI](../gui/___gui.md) — the units
  under test
- DOMY Watch `research/prompts/archetype/` — the golden input

### Used by
- Nobody at runtime; the offline safety net for every change.
