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

An item that carries an INPUT IMAGE (`PromptItem.input_image` — the
sheet's `← \`ref\`` line, owner 2026-07-23) has that reference
resolved RELATIVE TO THE SHEET'S OWN FOLDER (`sheet.source.parent`,
read only) and attached into the composer BEFORE the prompt via
`driver.submit_with_image` ("put THIS character into that scene");
plain items still go through `submit_prompt`. A missing reference
file is a loud per-item SKIP (logged, counted, reported) so the rest
of the batch still runs. The image-failed escalation re-attaches the
reference in its fresh session (the earlier same-chat rungs do not).

## Connections

### Uses
- [Sheet Parser](sheet_parser.md) — consumes `Sheet`
- [CDP Driver](driver.md) — the per-item protocol, `sniff_format`,
  the `NoImage` exception (the stuck-response case the nudge catches),
  the `ImageGenFailed` exception (BUG 3 — ChatGPT's own "image
  generation failed" answer, the retry-resend case)
- [Config (subfolder)](config/___config.md) — `Timing`, `REPORT_SUFFIX`,
  `RETRY_PREAMBLES` (the per-category safer-retry preambles:
  `SAFER_PREAMBLE` / `COPYRIGHT_PREAMBLE`), `CONTINUE_NUDGE`,
  `IMAGE_RETRY_NUDGE`,
  `IMAGE_FAILED_RETRY_MAX`, `IMAGE_FAILED_RETRY_DELAY_RANGE_S`,
  `IMAGE_FAILED_ESCALATION_DELAYS_S`, `dest_for`, `fmt_duration`,
  `fmt_size`

### Used by
- [Main (Entry Point)](../main.md) and [GUI](../gui.md)

## Resume model (owner 2026-07-19, revised 2026-07-21)

"Done" is the SAVED FILE itself — there is NO progress sidecar. The
folder is ALWAYS the source of truth: an unattended rerun
(`only=None`) skips every item whose dest file
`out_base / dest_for(drop, site)` already exists and generates the
rest (sheet-advised items sit out). A ticked `only` set NARROWS the
candidates to those drop paths but NEVER overwrites a dest file
already on disk — a ticked item that is already saved is skipped
exactly like the unattended path, logged (`RESUME: N/M already saved
on disk under <site>/`) and added to the report as a skip. To redo a
bad image the owner deletes the file first, then reruns (ticked or
not) — ticking alone can never force a regenerate.

(Owner 2026-07-21: a real run hit this precisely — 18 finished
images got regenerated after a restart because the old `only` branch
built its queue straight from the ticks, never checking the disk.
"The folder is the source of truth; the selection must check the
folder" is now the hard rule.) This replaces the old `.progress.json`
reading, which could disagree with the real files on disk (an item
recorded done whose file was never at the output location showed as
done yet could not be regenerated).

## Pause (owner 2026-07-21)

The GUI's per-job Pause toggle — a SEPARATE concept from the
`Timing.pause_min_s`/`pause_max_s` PACING wait between prompts (an
unrelated, existing feature that happens to share the word "pause").
`run_sheet` takes `should_pause: Callable[[], bool] | None`, checked
at the SAME item boundary as `should_stop` (between items, never
mid-generation — an in-flight image always finishes, exactly like
Stop's graceful semantics). While `should_pause()` is True the loop
blocks in `wait_while_paused` — a poll-wait (`PAUSE_POLL_INTERVAL_S`,
[Config (subfolder)](config/___config.md)), no busy spin — until it flips False (Resume) or
`should_stop` fires (Stop always wins over a pending or active
pause). `sheet_paused` / `sheet_resumed` fire on `on_event` exactly
ONCE per transition, never once per poll; `sheet_resumed` is skipped
when a Stop interrupted the wait (the run is ending, not continuing).

`wait_while_paused(should_pause, should_stop, log, emit) -> bool` is
a MODULE-level function (not a `run_sheet` internal) so it is shared
verbatim by the GUI's tool / AI-check worker loops (`_run_tool_job`,
`_run_ai_check_job` in [GUI](../gui.md)), which have no `should_stop`
of their own (there is no Stop for those jobs — `should_stop=None` is
passed, so the wait simply blocks for Resume) but still gain a Pause
toggle checked between images. It returns True only when a Stop
interrupted an ACTIVE pause, so a caller that already checked
`should_stop()` once this iteration never double-counts the call by
checking it again — `run_sheet`'s own loop relies on exactly this to
keep `should_stop`'s call frequency unchanged when pause is unused.

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
  should_pause, post_save, prompt_suffix, extra_suffix, report, only,
  on_event, safer_retry, continue_nudge, image_failed_retry) -> int` —
  `on_event` receives structured progress
  dicts: `sheet_start` (sheet, pending, total), `item_start` (title,
  idx, of), `item_retry` (safer retry AND every rung of the BUG 3
  recovery ladder — button click, "retry" resend, escalation round;
  same event, all recoveries reuse it), `item_nudge` (continue nudge,
  drop_path), `sheet_paused` / `sheet_resumed` (the Pause toggle, see
  **Pause** above), `item_progress` (idx, of, gen_s — the live
  count), `item_done` (title, drop_path, gen_s, over_s, orig_res,
  final_res, size), `item_refused`, `sheet_done` (generated) — the
  GUI dashboard is built from these. `item_progress` AND `item_done`
  also carry `actions` (the post_save description string, e.g.
  `REMOVE BG: done, CROP: done, UPSCALE: nothing`) and `retried`
  (True when the SAFER RETRY produced the image) — the dashboard's
  per-image STATUS BADGES map them via `config.badge_keys_for`
  (owner 2026-07-20). Logs the
  sheet's skipped entries, resumes by FILE EXISTENCE (or narrows to
  the ticked `only` set, which still never overwrites a file already
  on disk),
  drives every pending item, appends `prompt_suffix` (the caller
  resolves the per-site rules), runs the `post_save` hook — the
  caller composes the postprocess steps by flags and returns the
  full action description; failures are loud, counted, never fatal
  — paces between prompts,
  honors `should_stop`, and feeds `RunReport` when `report` is on.
  `only` narrows the queue to the owner's ticked drop paths, but a
  ticked item whose dest file already exists is SKIPPED just like the
  unattended resume path (owner 2026-07-21 — the folder is always the
  source of truth; redo = delete the file first). `extra_suffix`
  (owner 2026-07-20, the AI
  checker's re-send) is an optional `{drop_path: text}` map — the
  mapped item gets its text appended AFTER the site suffix (the
  "previous attempt had these flaws" fix note), unmapped items get
  nothing, and the note also rides a safer retry (the preamble is
  prepended to the same base); default `None` keeps every existing
  caller unchanged. A
  refusal (`ItemRefused`) skips just that item and the run
  continues; when `safer_retry` is on the item is re-sent ONCE with the
  preamble that matches the refusal's `category` (owner 2026-07-23) —
  `RETRY_PREAMBLES[exc.category]`: `SAFER_PREAMBLE` (allegory) for a
  safety block, `COPYRIGHT_PREAMBLE` (homage) for a copyright block — and
  only a second refusal counts as REFUSED. A category with no preamble
  (or an unclassified refusal) is reported with no retry. A **stuck `NoImage`** (the done edge fired but no image and
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
  **BUG 3 recovery LADDER** (owner 2026-07-21, escalation added
  2026-07-23): an `ImageGenFailed` — ChatGPT's own "Image generation
  failed" answer OR the generic "something seems to have gone wrong."
  error turn, both caught by the driver WITHOUT burning the hard
  timeout (see [CDP Driver](driver.md)) — is handled by
  `_recover_image_failed`, which walks one ladder cheapest rung first
  (only active when `image_failed_retry` is on, the default):
  1. **native Retry button** — `driver.click_error_retry()`; when the
     site has one for this state and it clears the error, done.
  2. **paced text "retry"** — resend `IMAGE_RETRY_NUDGE` up to
     `IMAGE_FAILED_RETRY_MAX` times, each after a random
     `IMAGE_FAILED_RETRY_DELAY_RANGE_S` wait (1-3 min).
  3. **escalation rounds** — one per `IMAGE_FAILED_ESCALATION_DELAYS_S`
     entry (default two: 1-3 min, then 22-36 min): wait a random
     duration in that entry's range, then `driver.refresh()` +
     `driver.new_chat()` and resend the WHOLE original prompt (a fresh
     chat has no context, so "retry" alone would mean nothing).
  The first rung that yields an image counts as a normal success (the
  image's `retried` badge is set). When EVERY rung is spent the ladder
  re-raises `ImageGenFailed` and the whole site STOPS (owner's "GASI",
  2026-07-23) — finished items are safe on disk, so a restart resumes
  past them; there is no per-item skip for this failure any more. Every
  wait polls `should_stop`, so a Stop never hangs behind the 22-36 min
  round; a Stop mid-ladder abandons recovery at once. With
  `image_failed_retry` off, the FIRST `ImageGenFailed` propagates and
  stops the site immediately, same shape as `continue_nudge=False`.
  Terminal/driver errors propagate to the caller — the
  report stays saved (resume is by the files already on disk). A `TerminalState` is re-raised
  UNCHANGED, so callers read its `retry_after_s` (the quota reset
  time the site named, parsed by the driver); the runner logs it
  first (`quota — reset in ~N min`) and stamps it into the report's
  stop reason.
- `wait_while_paused(should_pause, should_stop, log, emit) -> bool`
  (owner 2026-07-21) — the Pause wait itself, see **Pause** above;
  public (not a `run_sheet`-only helper) so [GUI](../gui.md)'s tool /
  AI-check worker loops share the exact same poll-wait instead of a
  second copy of the logic.
