# tests/

The offline half of the build — golden parser tests plus run-loop
tests over a fake driver, runnable with `python -m pytest tests`
from the project root.

## Files

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

### `test_runner.py` — Run-Loop Tests
Drives `run_sheet` with a duck-typed fake driver and a temp out
folder — no browser: the per-site rule suffix on every submitted
prompt (Gemini's three laws, ChatGPT without them), the direct
`<out>/<drop-path>` layout, the report txt (header, per-image
lines with resolution and postprocess actions, averages, totals,
stop reason), resume by FILE EXISTENCE (a second unattended run
drives nothing; a ticked `only` REGENERATES an already-saved file),
the graceful stop flag, the `post_save` hook (a failure
is loud, counted, and never kills the run), the per-item
`extra_suffix` map (the AI re-send's fix note — appended after the
site suffix for exactly the mapped item, and riding the safer
retry), and `TerminalState`
propagation — the runner logs the parsed quota reset time, stamps
it into the report and re-raises the exception unchanged.

### `test_ai.py` — Gemini Client + AI Flows
NO live API anywhere: the HTTP layer is the monkeypatched
`painter.ai._urlopen`. Covers the client's request building (url +
model, `x-goog-api-key` header, contents/systemInstruction payload,
base64 `inlineData` for images), the tolerant candidates/parts
response parsing, the loud failure taxonomy (`AiError` on HTTP
errors with the API's own message, prompt blocks, non-STOP finishes,
malformed shapes; `NoKey` on a missing/blank key BEFORE any network
traffic), the free-tier pacing sleep, the sheet-generator flow with
a mocked `gen` (questions parsing + cap, skipped answers, the
whole-file fence unwrap, real-parser validation, exactly ONE repair
round, the still-broken path that must NOT load, slugged
collision-free saves), the checker's strict OK/DEFECTS format, and
the flag memory (round-trip, merge, clear, the mtime-based prune of
regenerated/missing files, relative-vs-absolute keys, the
`dest_for` reverse mapping and the full `plan_resend` grouping —
per site / per sheet, each item its own fix note, loud unmatched
reasons).

### `test_quota_reset.py` — Quota Reset Parsing
`parse_quota_reset` against the LIVE-captured ChatGPT quota
messages (minutes and hours), short units, Serbian phrasings, and
the no-time Gemini message (None, never a guess); plus the
`TerminalState.retry_after_s` field itself.

### `test_postprocess.py` — Split Postprocess Steps
Synthetic images through the two composable steps:
`remove_background` (white plate cleared without cropping, already
transparent → nothing, ambiguous → unclear and untouched, broken
file → loud) and `crop_transparent` (content box + safety margin,
second pass already tight, opaque/fully-transparent → nothing,
margin clamped at the edge).

### `test_upscale.py` — Upscale Gating
The locked gate (aspect 0.9–1.1 AND a dimension under 800) against
a MOCKED binary: non-square and big-enough images never touch the
exe, small squares upscale native-4x and LANCZOS-land exactly on
the target, tiny sources stay honestly below. The last test drives
the REAL downloaded binary (skipped when `tools/realesrgan/` is
absent).

### `test_jobtemp.py` — Job Temp / Restore + Measure
Synthetic PNGs through [Job Temp](../painter/jobtemp.md): a
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
mutually consistent.

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
[Shared Filter Framework](../painter/filters.md)'s `matches()` on
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
- [Sheet Parser](../painter/sheet_parser.md),
  [Run Loop](../painter/runner.md), [Shared Filter
  Framework](../painter/filters.md) and [GUI](../gui.md) — the units
  under test
- DOMY Watch `research/prompts/archetype/` — the golden input

### Used by
- Nobody at runtime; the offline safety net for every change.
