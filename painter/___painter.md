# painter/

The engine package: the sheet parser, the CDP driver and the run
loop, with every tunable in one config module. The parser is pure and
offline; only the driver touches a browser.

## Files

### `config.py` — Configuration
Every tunable value: the CDP URL, output root, sheet-contract
constants (image extensions, skip markers), all timing/pacing knobs,
and the per-site DOM config blocks (selector fallbacks + refusal
markers) for ChatGPT and Gemini. See [Config](config.md).

### `sheet_parser.py` — Sheet Parser
Parses one prompt-sheet `.md` into items to generate, entries the
sheet marks as skipped, and loudly reported contract problems.
Stdlib only. See [Sheet Parser](sheet_parser.md).

### `driver.py` — CDP Driver
Attaches over CDP to the owner's already-open, logged-in tab and
drives the DOM: paste, send, watch the done edge, read the generated
image's bytes straight from the DOM. See [CDP Driver](driver.md).

### `runner.py` — Run Loop
The paced, resumable per-item loop with the `.progress.json` sidecar
state. See [Run Loop](runner.md).

## Connections

### Uses
- The prompt sheets of consumer projects (first: DOMY Watch
  `research/prompts/`) — read-only input

### Used by
- [Main (CLI)](../main.md) — the entry point wiring all four together
- [Tests (folder)](../tests/___tests.md) — golden tests over the parser

## Design Decisions

- **The drop path IS the output path.** Images save to
  `out/<drop-path>` exactly as the arrow line names it
  (`out/life/tree/Unborn.png`), not to a flattened
  `out/<theme>/<stem>.png` — the Life sheet's two registers share
  stems (`tree/Unborn.png` vs `animals/Unborn.png`) and flattening
  would collide; the sheet's own path already carries the theme
  folder.
- **Skip markers work at three levels** (all case-insensitive, and
  only inside `**bold**` spans, so prose mentions never trigger):
  a marker in a span after an entry's title skips that entry; a
  standalone marked note skips everything until the next heading
  (the temperaments tetramorph case); a marked section heading skips
  its whole section (the weekday SUPERSEDED sections).
- **Loud failure taxonomy** in the driver: `SelectorRot` (no
  fallback matched — the site reskinned), `TerminalState`
  (quota/refusal — stop, never blind-retry), `GenerationTimeout`
  (no done edge inside the hard cap). No state is ever guessed.
- **The parser imports no browser code** and the CLI imports the
  driver lazily, so `--dry-run` sheet validation needs nothing
  beyond the standard library.
