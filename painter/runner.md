# Run Loop

**Script:** [Run Loop (script)](runner.py)

## Purpose
The paced, resumable loop over a clean sheet's pending items:
paste (prompt + the site's background suffix) → submit → await the
done edge → extract bytes → save `<out_root>/<drop-path>` →
background fix → mark done in the sidecar state → pause → next.
A crash or a quota stop costs nothing — the next run resumes past
every marked item. The loop writes ONLY under `out_root`; sheets
are READ ONLY by construction.

## Connections

### Uses
- [Sheet Parser](sheet_parser.md) — consumes `Sheet`
- [CDP Driver](driver.md) — the per-item protocol, `sniff_format`,
  the site's `prompt_suffix`
- [Config](config.md) — `Timing`, `PROGRESS_SUFFIX`

### Used by
- [Main (CLI)](../main.md) and [GUI](../gui.md)

## Classes

### Progress
The sidecar state file `<out_root>/<sheet-stem>.progress.json`: a
map of done drop paths to saved file + UTC timestamp. Writes are
atomic (temp file + replace). A corrupt file raises loudly — never
silently restarts a run.

## Functions

- `run_sheet(sheet, driver, out_root, timing, log, should_stop,
  post_save) -> int` — logs the sheet's skipped entries, filters
  the queue through `Progress`, drives every pending item with
  per-item progress lines (elapsed, n/total, saved bytes), appends
  the site's background suffix to each prompt, runs the
  `post_save` background fix (failures loud, counted, never
  fatal), warns when saved bytes are not PNG, paces between
  prompts, and honors `should_stop` between items and during the
  pause (a graceful stop — the current item always completes).
  Returns how many images this run generated. Terminal/driver
  errors propagate to the caller — progress stays saved.
