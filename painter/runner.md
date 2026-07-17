# Run Loop

**Script:** [Run Loop (script)](runner.py)

## Purpose
The paced, resumable loop over a clean sheet's pending items:
paste (prompt + the site's rule suffix) → submit → await the done
edge → extract bytes → save DIRECTLY at `<out_root>/<drop-path>` →
background fix → report line → mark done in the sidecar state →
pause → next. A crash or a quota stop costs nothing — the next run
resumes past every marked item and the report keeps every finished
line. The loop writes ONLY under `out_root`; sheets are READ ONLY
by construction.

## Connections

### Uses
- [Sheet Parser](sheet_parser.md) — consumes `Sheet`
- [CDP Driver](driver.md) — the per-item protocol, `sniff_format`
- [Config](config.md) — `Timing`, `PROGRESS_SUFFIX`,
  `REPORT_SUFFIX`

### Used by
- [Main (Entry Point)](../main.md) and [GUI](../gui.md)

## Classes

### Progress
The sidecar state file `<out_root>/<sheet-stem>.progress.json`: a
map of done drop paths to saved file + UTC timestamp. Writes are
atomic (temp file + replace). A corrupt file raises loudly — never
silently restarts a run.

### RunReport
The per-sheet report `<out_root>/<sheet-stem>_report.txt`,
APPENDED per run and written INCREMENTALLY (header → a line per
image → summary), so an interrupted run keeps every finished line.
Per image: completion timestamp, generation seconds, original →
final resolution (PNG header parse, stdlib only), extra actions
(`REMOVE BG: <action>`). Summary: image count, average generation
per image, total generation + processing, wall clock incl. pauses,
run start/finish timestamps and why the run ended.

## Functions

- `run_sheet(sheet, driver, out_root, timing, log, should_stop,
  post_save, prompt_suffix, report) -> int` — logs the sheet's
  skipped entries, filters the queue through `Progress`, drives
  every pending item with per-item progress lines, appends
  `prompt_suffix` (the caller resolves the per-site rules) to each
  prompt, runs the `post_save` background fix (failures loud,
  counted, never fatal), warns when saved bytes are not PNG, paces
  between prompts, honors `should_stop` between items and during
  the pause, and feeds `RunReport` when `report` is on. Returns
  how many images this run generated. Terminal/driver errors
  propagate to the caller — progress and report stay saved.
