# Run Loop

**Script:** [Run Loop (script)](runner.py)

## Purpose
The paced, resumable loop over a clean sheet's pending items:
paste (prompt + the site's rule suffix) → submit → await the done
edge → extract bytes → save at `out_base / dest_for(drop, site)`
(the assets-mirroring layout) → the `post_save` hook (the caller's
composed postprocess: bg removal / crop / upscale) → report line →
pause → next. A crash or a quota stop costs nothing — **"done" is
the SAVED FILE itself** (owner 2026-07-19: no progress sidecar), so
an unattended rerun resumes past every image already on disk and the
report keeps every finished line. The loop writes ONLY under
`out_base`; sheets are READ ONLY by construction.

## Connections

### Uses
- [Sheet Parser](sheet_parser.md) — consumes `Sheet`
- [CDP Driver](driver.md) — the per-item protocol, `sniff_format`,
  the `NoImage` exception (the stuck-response case the nudge catches)
- [Config](config.md) — `Timing`, `REPORT_SUFFIX`,
  `SAFER_PREAMBLE`, `CONTINUE_NUDGE`, `dest_for`, `fmt_duration`,
  `fmt_size`

### Used by
- [Main (Entry Point)](../main.md) and [GUI](../gui.md)

## Resume model (owner 2026-07-19)

"Done" is the SAVED FILE itself — there is NO progress sidecar. An
unattended rerun (`only=None`) skips every item whose dest file
`out_base / dest_for(drop, site)` already exists and generates the
rest (sheet-advised items sit out). A ticked `only` set OVERRIDES
this: it generates EXACTLY those drop paths, OVERWRITING any that
already exist — the regenerate path, so a bad image can be redone by
re-ticking it in the GUI's Select window. This replaces the old
`.progress.json` reading, which could disagree with the real files
on disk (an item recorded done whose file was never at the output
location showed as done yet could not be regenerated).

## Classes

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
  post_save, prompt_suffix, report, only, on_event, safer_retry,
  continue_nudge) -> int` — `on_event` receives structured progress
  dicts: `sheet_start` (sheet, pending, total), `item_start` (title,
  idx, of), `item_retry` (safer retry), `item_nudge` (continue nudge,
  drop_path), `item_progress` (idx, of, gen_s — the live
  count), `item_done` (title, drop_path, gen_s, over_s, orig_res,
  final_res, size), `item_refused`, `sheet_done` (generated) — the
  GUI dashboard is built from these. Logs the
  sheet's skipped entries, resumes by FILE EXISTENCE (or drives the
  ticked `only` set, which overrides existence to regenerate),
  drives every pending item, appends `prompt_suffix` (the caller
  resolves the per-site rules), runs the `post_save` hook — the
  caller composes the postprocess steps by flags and returns the
  full action description; failures are loud, counted, never fatal
  — paces between prompts,
  honors `should_stop`, and feeds `RunReport` when `report` is on.
  `only` narrows the queue to the owner's ticked drop paths,
  generating EXACTLY those and OVERWRITING any that already exist
  (the regenerate path). A
  SAFETY refusal (`ItemRefused`) skips just that item and the run
  continues; when `safer_retry` is on the item is re-sent ONCE with
  `SAFER_PREAMBLE` first, and only a second refusal counts as
  REFUSED. A **stuck `NoImage`** (the done edge fired but no image and
  no marker — ChatGPT's recurring stall) is handled the same shape as
  the safer retry but for the OTHER failure: when `continue_nudge` is
  on (the default) the runner sends `CONTINUE_NUDGE` ONCE into the same
  chat (a plain "continue" message, NO prompt suffix — the prompt is
  already there) and, if that yields the image, uses it as a normal
  success (its `gen_s` timed from the nudge's own send). One nudge
  attempt per item: if the nudge still raises `NoImage` (or any other
  `DriverError` — e.g. the nudge itself hits quota/refusal) it
  propagates and the site stops loudly, exactly as before. With
  `continue_nudge` off, the first `NoImage` stops the site immediately.
  Terminal/driver errors propagate to the caller — the
  report stays saved (resume is by the files already on disk). A `TerminalState` is re-raised
  UNCHANGED, so callers read its `retry_after_s` (the quota reset
  time the site named, parsed by the driver); the runner logs it
  first (`quota — reset in ~N min`) and stamps it into the report's
  stop reason.
