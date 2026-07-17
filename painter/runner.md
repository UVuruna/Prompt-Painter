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
  `REPORT_SUFFIX`, `SAFER_PREAMBLE`, `fmt_duration`, `fmt_size`

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
Per image: completion timestamp, **generate** seconds (SEND →
image), **process** seconds (image → saved+fixed), original →
final resolution (PNG header parse, stdlib only), final file size,
extra actions (`REMOVE BG: <action>`). Summary: image count,
average generation AND average processing per image, total
generate + process, wall clock incl. pauses, run start/finish
timestamps and why the run ended.

## The two timings (owner 2026-07-17)

- **generate** `gen_s = t_image − t_send` — pure AI time from the
  SEND click to the image appearing (excludes the input
  hesitation, which is timed inside `submit_prompt`).
- **process** `proc_s = t_saved − t_image` — our side: writing the
  file plus the background fix. (The paced pause between prompts is
  a separate, configured value, not folded into this average.)

## Functions

- `run_sheet(sheet, driver, out_root, timing, log, should_stop,
  post_save, prompt_suffix, report, only, on_event, safer_retry)
  -> int` — `on_event` receives structured progress dicts:
  `sheet_start` (sheet, pending, total), `item_start` (title, idx,
  of), `item_retry`, `item_done` (title, drop_path, gen_s, proc_s,
  orig_res, final_res, size), `item_refused`, `sheet_done`
  (generated) — the GUI dashboard is built from these. Logs the
  sheet's skipped entries, filters the queue through `Progress`,
  drives every pending item, appends `prompt_suffix` (the caller
  resolves the per-site rules), runs the `post_save` background fix
  (failures loud, counted, never fatal), paces between prompts,
  honors `should_stop`, and feeds `RunReport` when `report` is on.
  `only` narrows the queue to the owner's ticked drop paths. A
  SAFETY refusal (`ItemRefused`) skips just that item and the run
  continues; when `safer_retry` is on the item is re-sent ONCE with
  `SAFER_PREAMBLE` first, and only a second refusal counts as
  REFUSED. Terminal/driver errors propagate to the caller —
  progress and report stay saved.
