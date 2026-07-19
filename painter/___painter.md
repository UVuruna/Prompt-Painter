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

### `postprocess.py` — Background Removal + Crop
The two split, composable per-save steps (owner's #7):
`remove_background` (auto-detected, in place) and
`crop_transparent` (content box + safety margin) — callers compose
them by flags; loud on failure, never fatal. See
[Postprocess](postprocess.md).

### `bg_remove.py` — Background Remover
The remover itself (moved in from DOMY Watch tools — no part of
this program lives in another project): per-file auto-detection,
white/black clearing, autocrop; also runnable standalone. See
[Background Remover](bg_remove.md).

### `upscale.py` — Real-ESRGAN Upscaler
Upscales small near-square (badge-class) images with the
`realesrgan-ncnn-vulkan` binary (downloaded on first use into
`tools/`, gitignored) so no dimension stays below the configured
minimum; loud but catchable on a machine without Vulkan. See
[Upscale](upscale.md).

### `aspect.py` — Change Aspect Ratio
The standalone batch DEFORM tool (owner 2026-07-19): stretches every
image in a folder to a target ratio `X:Y` in place — a grow-only,
non-proportional LANCZOS stretch that never shrinks either axis and
leaves an already-at-ratio image byte-unchanged. Loud but catchable.
See [Change Aspect Ratio](aspect.md).

### `jobtemp.py` — Job Temp / Restore
The four in-place tools' safety net (owner 2026-07-19): back up the
ORIGINAL of every file before the op, so the dashboard's before/after
viewer can RESTORE one image or the whole job, plus `measure` — the
before→after % each tool panel shows (removed / reduction / increase /
deformation), derived OUTSIDE the engine functions. Cleared on panel
CLOSE, on app exit and swept at startup. See [Job Temp](jobtemp.md).

### `settings.py` — Settings Persistence
Loads/saves the GUI's remembered choices as `settings.json` at the
project root (gitignored); a corrupt file is loud but never crashes
the app. See [Settings](settings.md).

## Connections

### Uses
- The prompt sheets of consumer projects (first: DOMY Watch
  `research/prompts/`) — READ-ONLY input

### Used by
- [Main (CLI)](../main.md) and [GUI](../gui.md) — the two entry
  points wiring the modules together
- [Tests (folder)](../tests/___tests.md) — golden parser tests and
  offline runner tests

## Design Decisions

- **The drop path IS the output path, per site.** Images land at
  `<out>/<site>/<drop-path>` exactly as the arrow line names it
  (`out/gemini/life/tree/Unborn.png`) — the Life sheet's two
  registers share stems and flattening would collide; the per-site
  split keeps parallel runs collision-free and mirrors DOMY's
  per-source asset trees.
- **Direct save, closed folders.** Images land straight in
  `<out>/<site>/<drop-path>` (owner 2026-07-17: no approval step);
  the per-sheet progress sidecar and report txt live beside them,
  so every sheet CLOSES as a unit — a quota stop mid-batch never
  costs finished work and the next run resumes the rest.
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
- **The background remover is in-house** (`painter/bg_remove.py`,
  moved from DOMY Watch on the owner's rule) and called directly;
  its heavy imports (numpy/scipy) load lazily, only when a fix
  actually runs. Fix failures are loud but never kill a run (the
  raw image is already saved; the remover is rerun-safe).
- **Postprocess steps are split and composable** (owner's #7):
  background removal, transparent crop and the Real-ESRGAN upscale
  are three separate functions; the entry points compose them into
  ONE `post_save` hook by flags, and the hook's returned string is
  the report's per-image action description.
- **Write-scope guarantee:** the loop writes only under `out_root`;
  sheets and their folders are READ ONLY by construction, and both
  entry points refuse an output folder that contains the sheet.
- **The parser imports no browser code** and both entry points
  import the driver lazily, so `--dry-run` / "Check sheet" need
  nothing beyond the standard library.
