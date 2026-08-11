# Run Report

**Script:** [Run Report (script)](../run_report.py)

## Purpose
`RunReport` — the per-sheet report txt writer
(`<out>/_state/<site>/<sheet-stem>_report.txt`, on by default). Split
out of `painter/runner.py` (THE STRUCTURE LAW, faza 2 2026-08-03 —
report writing is its own responsibility; the run loop had outgrown
the god-file line guard). Appends INCREMENTALLY — header, then a line
per image, then the summary — so an interrupted run keeps every
finished line. The content is the owner's 2026-07-18 decree ("sve se
računa"): run start/finish timestamps, per-image GENERATE time (AI:
SEND → image) and OUR time (save + bgfix + pause), original → final
resolution, file size, extra actions (REMOVE BG …), refused items
with reasons, the per-image averages and the collection total.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — `fmt_duration`/
  `fmt_size` (the report's human-readable numbers)

### Used by
- [Run Loop](runner.md) — `run_sheet` builds ONE `RunReport` per run
  (only when `report=True`) and calls `start`/`item`/`refused`/
  `finish` at the matching loop points

## Classes

### RunReport
See Purpose above. `start(pending, total, skipped)` writes the header
+ the sheet-skip lines; `item(...)` one finished-image line;
`refused(drop_path, reason)` one refusal line (reason capped at 120
chars); `finish(generated, wall_s, stopped_why)` the averages/total
footer. `_now()` (module-private) stamps every line.

## Design Decisions
- **Moved whole, byte-identical behavior.** The split changed the
  class's HOME, not its output — every report written after the split
  is line-for-line what the pre-split runner wrote.

## 2026-08-11 — the diagnosis line

`diagnosis(drop_path, text)` appends the site's OWN answer to the
refusal diagnostic question (`WHY (site's answer) — ...`, capped at
400 chars) right under the matching REFUSED line, so the sheet rework
sees WHY without opening the transcript.
