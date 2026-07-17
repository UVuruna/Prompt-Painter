# painter/

The engine package: the sheet parser, the CDP driver, the run loop,
the Chrome launcher and the background-fix bridge, with every
tunable in one config module. The parser is pure and offline; only
the driver touches a browser.

## Files

### `config.py` — Configuration
Every tunable value: CDP endpoint, Chrome launch settings and the
dedicated profile folder, output layout, sheet-contract constants,
background-tool settings, all timing/pacing knobs, and the per-site
DOM config blocks (selector fallbacks, background prompt suffixes,
refusal markers). See [Config](config.md).

### `sheet_parser.py` — Sheet Parser
Parses one prompt-sheet `.md` into items to generate, entries the
sheet marks as skipped, and loudly reported contract problems.
Stdlib only. See [Sheet Parser](sheet_parser.md).

### `driver.py` — CDP Driver
Attaches over CDP to the open, logged-in tab and drives the DOM:
paste, send, watch the done edge, read the generated image's bytes
straight from the DOM. See [CDP Driver](driver.md).

### `runner.py` — Run Loop
The paced, resumable per-item loop: background suffix, save under
`<out>/<site>/<drop-path>`, background fix, `.progress.json`
sidecar, graceful stop. See [Run Loop](runner.md).

### `chrome.py` — Chrome Launcher
Probes CDP and, when nothing answers, launches the automation
Chrome with the dedicated `chrome-profile/` and one tab per site.
See [Chrome Launcher](chrome.md).

### `postprocess.py` — Background Fix
Runs DOMY Watch's `bg_remove.py` over each saved image
(subprocess); loud on failure, never fatal. See
[Postprocess](postprocess.md).

## Connections

### Uses
- The prompt sheets of consumer projects (first: DOMY Watch
  `research/prompts/`) — READ-ONLY input
- DOMY Watch `tools/bg_remove.py` — the background tool

### Used by
- [Main (CLI)](../main.md) and [GUI](../gui.md) — the two entry
  points wiring the modules together
- [Tests (folder)](../tests/___tests.md) — golden parser tests and
  offline runner tests

## Design Decisions

- **The drop path IS the output path, per site.** Images save to
  `<out>/<site>/<drop-path>` exactly as the arrow line names it
  (`out/gemini/life/tree/Unborn.png`) — the Life sheet's two
  registers share stems and flattening would collide; the per-site
  split keeps parallel runs collision-free and mirrors DOMY's
  per-source asset trees.
- **Skip markers work at three levels** (all case-insensitive, and
  only inside `**bold**` spans, so prose mentions never trigger):
  a marker in a span after an entry's title skips that entry; a
  standalone marked note skips everything until the next heading
  (the temperaments tetramorph case); a marked section heading
  skips its whole section (the weekday SUPERSEDED sections).
- **Loud failure taxonomy** in the driver: `SelectorRot` (no
  fallback matched — the site reskinned), `TerminalState`
  (quota/refusal — stop, never blind-retry), `GenerationTimeout`
  (no done edge inside the hard cap). No state is ever guessed.
- **The background fix is a subprocess, not an import** — DOMY's
  tool stays DOMY's; the bridge only builds the command line and
  reads the action back. Its failures are loud but never kill a
  run (the raw image is already saved; the tool is rerun-safe).
- **Write-scope guarantee:** the loop writes only under `out_root`;
  sheets and their folders are READ ONLY by construction, and both
  entry points refuse an output folder that contains the sheet.
- **The parser imports no browser code** and both entry points
  import the driver lazily, so `--dry-run` / "Check sheet" need
  nothing beyond the standard library.
