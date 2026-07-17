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
folder — no browser: the background suffix on every submitted
prompt (plus the `auto`/`transparent`/`white`/`none` mode
resolution), the `<out>/<drop-path>` layout, resume via the
progress sidecar (a second run drives nothing), the graceful stop
flag, and the background-fix hook (action logged; a failure is
loud, counted, and never kills the run).

### `test_review.py` — Staging & Approval Tests
Phase two offline: `staged_images` lists per site (progress
sidecars never listed), `approve` moves an image to its final
`<out>/<site>/<drop-path>` and keeps it marked done, `reject`
deletes it and clears the progress mark so a rerun regenerates.

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
