# Run Loop

**Script:** [Run Loop (script)](runner.py)

## Purpose
The paced, resumable loop over a clean sheet's pending items:
paste (prompt + the site's rule suffix) → submit → await the done
edge → extract bytes → save at `out_base / dest_for(drop, site)`
(the assets-mirroring layout) → the `post_save` hook (the caller's
composed postprocess: bg removal / crop / upscale) → report line →
mark done in the sidecar state (under `_state/<site>/`) → pause →
next. A crash or a quota stop costs nothing — the next run resumes
past every marked item and the report keeps every finished line.
The loop writes ONLY under `out_base`; sheets are READ ONLY by
construction.

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
Per image: completion timestamp, **gen** seconds (AI: SEND →
image), **ours** seconds (save + bgfix + pause), original → final
resolution (PNG header parse, stdlib only), final file size, extra
actions — the `post_save` hook's own description (e.g.
`REMOVE BG: done, CROP: done, UPSCALE: nothing`;
`POSTPROCESS: FAILED` on a loud failure). Summary: image count,
average generation (AI) AND average our-time per image, their
total, wall clock, run start/finish timestamps and why the run
ended — a quota stop includes the parsed reset time when the site
named one (`quota / rate limit — stopped (reset in ~27m 00s)`).

## The two timings (owner 2026-07-17 — "sve se računa")

Every image's wall time splits cleanly into two, and they sum:

- **AI generate** `gen_s = t_image − t_send` — from the SEND click
  to the image appearing.
- **our time** `over_s` — everything WE do until the next SEND:
  writing the file, the background fix, AND the paced pause. Timed
  as `now − t_image` after the pause (the last image has no pause).

The image is counted the instant it is saved (an `item_progress`
event) so the dashboard never stalls; the `item_done` event with
`over_s` follows once the pause has elapsed.

## Functions

- `run_sheet(sheet, driver, out_root, timing, log, should_stop,
  post_save, prompt_suffix, report, only, on_event, safer_retry)
  -> int` — `on_event` receives structured progress dicts:
  `sheet_start` (sheet, pending, total), `item_start` (title, idx,
  of), `item_retry`, `item_progress` (idx, of, gen_s — the live
  count), `item_done` (title, drop_path, gen_s, over_s, orig_res,
  final_res, size), `item_refused`, `sheet_done` (generated) — the
  GUI dashboard is built from these. Logs the
  sheet's skipped entries, filters the queue through `Progress`,
  drives every pending item, appends `prompt_suffix` (the caller
  resolves the per-site rules), runs the `post_save` hook — the
  caller composes the postprocess steps by flags and returns the
  full action description; failures are loud, counted, never fatal
  — paces between prompts,
  honors `should_stop`, and feeds `RunReport` when `report` is on.
  `only` narrows the queue to the owner's ticked drop paths. A
  SAFETY refusal (`ItemRefused`) skips just that item and the run
  continues; when `safer_retry` is on the item is re-sent ONCE with
  `SAFER_PREAMBLE` first, and only a second refusal counts as
  REFUSED. Terminal/driver errors propagate to the caller —
  progress and report stay saved. A `TerminalState` is re-raised
  UNCHANGED, so callers read its `retry_after_s` (the quota reset
  time the site named, parsed by the driver); the runner logs it
  first (`quota — reset in ~N min`) and stamps it into the report's
  stop reason.
