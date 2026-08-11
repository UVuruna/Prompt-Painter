# painter/

The engine package: the sheet parser, the CDP driver, the run loop,
the Chrome launcher and the background-fix bridge, with every
tunable in one config module. The parser is pure and offline; only
the driver touches a browser.

## Files

| File | Tier | One line |
|------|------|----------|
| `__init__.py` | Trivial | empty package marker — no logic |
| `settings.py` | Standard | GUI's remembered-choices JSON, load/save — [about](__about/settings.md) |
| `chrome.py` | Algorithmic | probe/launch/poll attach-point protocol for the automation Chrome — [about](__about/chrome.md) · [flow](__flow/chrome.md) |
| `driver.py` | Algorithmic | CDP driver — the F1 turn-based per-item protocol (submit, await, extract, recovery) — [about](__about/driver.md) · [flow](__flow/driver.md) |
| `runner.py` | Algorithmic | the paced, resumable run loop over a sheet's pending items — [about](__about/runner.md) · [flow](__flow/runner.md) |
| `run_report.py` | Standard | the per-sheet report txt writer (split out of runner.py, faza 2) — [about](__about/run_report.md) |
| `recovery.py` | Algorithmic | the image-failure recovery ladder (split out of runner.py, 2026-08-11) — [about](__about/recovery.md) · [flow](__flow/recovery.md) |
| `transcript.py` | Standard | the per-site AI response transcript (`_state/<site>/transcript.jsonl`) — [about](__about/transcript.md) |
| `sheet_parser.py` | Algorithmic | parses one prompt-sheet `.md` into the run queue — [about](__about/sheet_parser.md) · [flow](__flow/sheet_parser.md) |
| `bg_remove.py` | Algorithmic | the color-keyed background-removal engine — [about](__about/bg_remove.md) · [flow](__flow/bg_remove.md) |
| `postprocess.py` | Algorithmic | composed post-save hook: background removal + transparent crop — [about](__about/postprocess.md) · [flow](__flow/postprocess.md) |
| `upscale.py` | Algorithmic | upscale gating + Real-ESRGAN invocation — [about](__about/upscale.md) · [flow](__flow/upscale.md) |
| `aspect.py` | Algorithmic | batch DEFORM tool — stretch every image in a folder to a target ratio — [about](__about/aspect.md) · [flow](__flow/aspect.md) |
| `imagesession.py` | Standard | decode-once / encode-once buffer between the chained pipeline steps and the disk — [about](__about/imagesession.md) |
| `filters.py` | Algorithmic | shared stackable "what should this tool touch" gate — [about](__about/filters.md) · [flow](__flow/filters.md) |
| `jobtemp.py` | Algorithmic | the four in-place tools' backup/restore safety net — [about](__about/jobtemp.md) · [flow](__flow/jobtemp.md) |
| `config/` | — | every tunable value, split by domain — [Config (subfolder)](config/___config.md) |
| `ai/` | — | the AI features' engine: Gemini client, sheet generator, image checker, flag memory — [AI (subfolder)](ai/___ai.md) |

## Connections

### Uses
- The prompt sheets of consumer projects (first: Watch Academy
  `research/prompts/`) — READ-ONLY input

### Used by
- [Main (Entry Point)](../__about/main.md) and
  [GUI (folder)](../gui/___gui.md) — the two entry points wiring the
  modules together
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
  the per-sheet report txt lives under `_state/<site>/`, and "done"
  is the SAVED FILE itself (owner 2026-07-19: no progress sidecar),
  so every sheet CLOSES as a unit — a quota stop mid-batch never
  costs finished work and the next run resumes past every image
  already on disk.
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
  moved from Watch Academy on the owner's rule) and called directly;
  its heavy imports (numpy/scipy) load lazily, only when a fix
  actually runs. Fix failures are loud but never kill a run (the
  raw image is already saved; the remover is rerun-safe).
- **ONE removal, not one per colour** (owner 2026-07-28, root Rule
  #19). White and black were two hard-wired scalar keys; they are now
  two TARGET COLOURS handed to a single distance-keyed engine, which
  is what made "clear any background colour ± X %" a parameter rather
  than a third algorithm. The unification was proven byte-identical
  against the old code over 17 real plates and 400 randomised ones.
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
