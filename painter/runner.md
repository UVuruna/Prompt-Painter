# Run Loop

**Script:** [Run Loop (script)](runner.py)

## Purpose
The paced, resumable loop over a clean sheet's pending items:
paste → submit → await the done edge → extract bytes → save
`out/<drop-path>` → mark done in the sidecar state → pause → next.
A crash or a quota stop costs nothing — the next run resumes past
every marked item.

## Connections

### Uses
- [Sheet Parser](sheet_parser.md) — consumes `Sheet`
- [CDP Driver](driver.md) — the per-item protocol, `sniff_format`
- [Config](config.md) — `Timing`, `PROGRESS_SUFFIX`

### Used by
- [Main (CLI)](../main.md)

## Classes

### Progress
The sidecar state file `out/<sheet-stem>.progress.json`: a map of
done drop paths to saved file + UTC timestamp. Writes are atomic
(temp file + replace). A corrupt file raises loudly — never
silently restarts a run.

## Functions

- `run_sheet(sheet, driver, out_root, timing, log) -> int` — logs
  the sheet's skipped entries, filters the queue through
  `Progress`, drives every pending item with per-item progress
  lines (elapsed, n/total, saved bytes), warns when the saved bytes
  are not PNG, and paces between prompts. Returns how many images
  this run generated. Terminal/driver errors propagate to the CLI —
  progress stays saved.
