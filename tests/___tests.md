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
the optional input filter (off / IF / IF NOT) and loud failures.

### `test_viewer.py` — Viewer Helpers
The before/after transparency checkerboard (`_checkerboard` /
`_has_alpha` and the composite promise) and the folder-scoped
restore set (`rels_in_folder`).

### `test_smooth_transition.py` — Snapshot-Cover Fallbacks
The shared `gui.smooth_transition` helper headless (owner
2026-07-20): the mutate callback runs EXACTLY ONCE with no root, an
unmapped/unviewable root, or a failing cover; the covered path
forces the overlay painted BEFORE the mutate and fades after (theme
timing passes through); a mutate exception propagates loudly while
the overlay still fades — never a stuck cover, never a masked error.

### `conftest.py` — Import Path
Makes the `painter` package importable from any pytest invocation.

### `fixtures/` — Contract-Violation Sheets
`unpaired.md`, `no_h1.md`, `bad_paths.md` — tiny synthetic sheets,
one violation each.

## Connections

### Uses
- [Sheet Parser](../painter/sheet_parser.md) and
  [Run Loop](../painter/runner.md) — the units under test
- DOMY Watch `research/prompts/archetype/` — the golden input

### Used by
- Nobody at runtime; the offline safety net for every change.
