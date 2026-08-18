# Run Loop

**Script:** [Run Loop (script)](../runner.py) ·
**Flow:** [diagram](../__flow/runner.md)

## Purpose

The paced, resumable loop over a clean sheet's pending items:
paste (prompt + the site's rule suffix) → submit → await the done
edge → extract bytes → save at `out_base / dest_for(drop, site_key)`
(the sheet's own path + the generator suffix — owner decree 2026-08-14) → the `post_save` hook (the caller's
composed postprocess: bg removal / crop / upscale) → report line →
pause → next. A crash or a quota stop costs nothing — **"done" is
the SAVED FILE itself** (owner 2026-07-19: no progress sidecar), so
an unattended rerun resumes past every image already on disk and the
report keeps every finished line. The loop writes ONLY under
`out_base`; sheets are READ ONLY by construction.

An item that carries INPUT IMAGE(S) (`PromptItem.input_images` — the
sheet's `← \`ref\`` line(s), owner 2026-07-23; MULTI + faza 2
2026-08-03, LINE ORDER = ATTACH ORDER) has each reference resolved by
`sheet_parser.resolve_input_images` — the BINDING order ① sheet folder →
② `reference_dir` (the GUI Prompt+Image section's Reference folder) →
③ absolute; sources read only, no basename guessing — and attached
into the composer BEFORE the prompt via `driver.submit_with_image`
("put THIS character into that scene"); plain items still go through
`submit_prompt`. A missing reference file is a loud per-item SKIP
(logged, counted, reported) so the rest of the batch still runs. The
image-failed escalation re-attaches the reference(s) in its fresh
session (the earlier same-chat rungs do not).

`require_input_image=True` (faza 2 — the GUI's PROMPT + IMAGE mode,
owner: "radi samo one slike koje imaju i PROMPT i PNG u prilogu")
narrows the queue to items that declare at least one `←` reference
AND whose references ALL resolve at Start — every excluded item is
loudly listed and lands in the report's skip lines, never silently
dropped.

`RunReport` moved to its own module (`painter/run_report.py`, THE
STRUCTURE LAW split, faza 2) — behavior unchanged, see
[Run Report](run_report.md).

## Connections

### Uses
- [Sheet Parser](sheet_parser.md) — consumes `Sheet`
- [CDP Driver](../driver/___driver.md) — the per-item protocol, `sniff_format`,
  the `NoImage` exception (`had_text` decides loud-skip vs the one
  allowed nudge), the `SendVanished` exception (the site dropped our
  confirmed message — re-send the item's own prompt, F1b),
  the `ImageGenFailed` exception (ChatGPT's own
  "image generation failed" answer, the retry-resend case), the
  `ModelDegraded` exception (Gemini's Flash-Lite degradation banner)
- [Config (subfolder)](../config/___config.md) — `Timing`,
  `REPORT_SUFFIX`, `RETRY_PREAMBLES` (the per-category safer-retry
  preambles: `SAFER_PREAMBLE` / `COPYRIGHT_PREAMBLE`),
  `CONTINUE_NUDGE`, `IMAGE_RETRY_NUDGE`, `IMAGE_FAILED_RETRY_MAX`,
  `IMAGE_FAILED_RETRY_DELAY_RANGE_S`,
  `IMAGE_FAILED_ESCALATION_DELAYS_S`, `PAUSE_POLL_INTERVAL_S`,
  `STATE_DIRNAME`, `dest_for`, `versioned_dest_for` (the ticked-redo
  `_vN` dest), `fmt_duration`, `fmt_size`, `parse_quota_reset`

### Used by
- [Main (Entry Point)](../../__about/main.md) and
  [GUI (folder)](../../gui/___gui.md)

## Resume model (owner 2026-07-19, revised 2026-07-21 / 2026-07-27)

"Done" is the SAVED FILE itself — there is NO progress sidecar. The
folder is ALWAYS the source of truth: an unattended rerun
(`only=None`) skips every item whose dest file
`out_base / dest_for(drop, site_key)` already exists and generates the
rest (sheet-advised items sit out), and NO file on disk is EVER
overwritten. A ticked `only` set is the queue itself: a ticked item
NOT yet on disk saves canonically, while a ticked item whose
canonical file already exists is a deliberate REDO (owner
2026-07-27) — it generates again and saves as the NEXT `_vN` sibling
(`versioned_dest_for`: the DOMY `<File>[_vN]_<sfx>.png` rotation
form, canonical = v1, first redo = `_v2`, last-on-disk + 1 after
that), logged (`NEW VERSION: N/M ticked item(s) already saved ...`)
and marked in the report's note column (`NEW VERSION: <file>`).
Every `item_progress`/`item_done` event carries `rel` — the ACTUAL
saved out-relative path — so the dashboard, the parallel checker and
the fixer follow the version file instead of re-deriving the
canonical `dest_for` guess.

(Owner 2026-07-21: a real run hit this precisely — 18 finished
images got regenerated after a restart because the old `only` branch
built its queue straight from the ticks, never checking the disk.
"The folder is the source of truth; the selection must check the
folder" is now the hard rule.)

## Pause (owner 2026-07-21)

The GUI's per-job Pause toggle — a SEPARATE concept from the
`Timing.pause_min_s`/`pause_max_s` PACING wait between prompts (an
unrelated, existing feature that happens to share the word "pause").
`run_sheet` takes `should_pause: Callable[[], bool] | None`, checked
at the SAME item boundary as `should_stop` (between items, never
mid-generation). While `should_pause()` is True the loop blocks in
`wait_while_paused` — a poll-wait (`PAUSE_POLL_INTERVAL_S`), no busy
spin — until it flips False (Resume) or `should_stop` fires (Stop
always wins over a pending or active pause). `sheet_paused` /
`sheet_resumed` fire on `on_event` exactly ONCE per transition;
`sheet_resumed` is skipped when a Stop interrupted the wait.

`wait_while_paused(should_pause, should_stop, log, emit) -> bool` is
a MODULE-level function (not a `run_sheet` internal) so it is shared
verbatim by the GUI's tool / AI-check worker loops, which have no
`should_stop` of their own (`should_stop=None` is passed, so the wait
simply blocks for Resume) but still gain a Pause toggle. It returns
True only when a Stop interrupted an ACTIVE pause.

## Model degradation (Gemini's Flash-Lite banner)

The site can silently drop to a weaker model under load
(`SiteConfig.degrade_banner`) two different ways, both resolved by
the SAME caller decision (`on_degrade`):

- **No image produced** — `driver.await_done`/`extract_image` raises
  `ModelDegraded` (checked before the quota markers, since the
  banner's companion text also matches them). The runner calls
  `on_degrade(retry_after_s)`: `"continue"` loud-skips just this item
  and keeps the run alive on the weaker model; `"wait"` (and a missing
  callback — the CLI) re-raises as `TerminalState` with the parsed
  reset time, riding the existing quota auto-restart.
- **An image STILL arrived** — the banner can be up while Flash-Lite
  still renders. Probed via `driver.degrade_banner_text()` AFTER every
  save (never wasting a made image); the choice is asked ONCE per run
  (`degrade_handled` latches it) — `"continue"` just logs and carries
  on, `"wait"` raises `TerminalState` the same way.

## The BUG 3 image-failure recovery ladder (owner 2026-07-21 / 2026-07-23)

An `ImageGenFailed` — ChatGPT's own "Image generation failed" answer
OR the generic "something seems to have gone wrong." error turn, both
caught by the driver WITHOUT burning the hard timeout — is handled by
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
   `driver.new_chat()` and resend the WHOLE original prompt
   (RE-ATTACHING the input image reference when the item carried one —
   a fresh session has no context and no attachment).

The first rung that yields an image counts as a normal success (the
image's `retried` badge is set). When EVERY rung is spent the ladder
re-raises `ImageGenFailed` and the whole site STOPS (owner's "GASI") —
finished items are safe on disk, so a restart resumes past them. Every
wait polls `should_stop`. With `image_failed_retry` off, the FIRST
`ImageGenFailed` propagates and stops the site immediately. An
`ItemRefused` surfacing INSIDE the ladder (e.g. after the native Retry
click the site answers a copyright block) is handled exactly like a
first-attempt refusal — one safer retry with the category preamble,
then a per-item skip.

## Classes

*(`RunReport` lives in its own module since the faza 2 STRUCTURE LAW
split — content and format unchanged, see [Run Report](run_report.md):
per-image gen/ours seconds, resolutions, sizes, actions, the averages
and the run's start/finish/why-ended lines.)*

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

- `run_sheet(sheet, driver, out_base, site_key, timing, log=print,
  should_stop=None, should_pause=None, post_save=None,
  prompt_suffix="", extra_suffix=None, report=True, only=None,
  on_event=None, safer_retry=False, continue_nudge=True,
  image_failed_retry=True, new_chat_per_folder=False,
  on_degrade=None) -> int` — `on_event` receives structured progress
  dicts: `sheet_start` (sheet, pending, total), `item_start` (title,
  idx, of), `item_retry` (safer retry AND every rung of the BUG 3
  recovery ladder — same event, all recoveries reuse it), `item_nudge`
  (continue nudge, drop_path), `sheet_paused` / `sheet_resumed` (the
  Pause toggle, see **Pause** above), `item_progress` (idx, of,
  gen_s — the live count), `item_done` (title, drop_path, gen_s,
  over_s, orig_res, final_res, size), `item_refused`, `sheet_done`
  (generated) — the GUI dashboard is built from these. `item_progress`
  AND `item_done` also carry `rel` (the ACTUAL saved out-relative
  path), `actions` (the post_save description string) and `retried`
  (True when a retry/recovery path produced the image) — the
  dashboard's per-image STATUS BADGES map them via
  `config.badge_keys_for`. `new_chat_per_folder` (owner 2026-07-20)
  opens a fresh conversation whenever the queue's drop-path FOLDER
  changes (a failed `new_chat()` is loud but never fatal — the run
  continues in the old chat).

  Logs the sheet's skipped entries, resumes by FILE EXISTENCE, drives
  every pending item, appends `prompt_suffix` (the caller resolves the
  per-site rules), runs the `post_save` hook — failures are loud,
  counted, never fatal — paces between prompts, honors `should_stop`,
  and feeds `RunReport` when `report` is on. `only` is the owner's
  ticked drop-path queue: an item not yet on disk saves canonically,
  one already saved REDOES as its next `_vN` version (see **Resume
  model** above). `extra_suffix` (owner 2026-07-20, the AI checker's
  re-send) is an optional `{drop_path: text}` map — the mapped item
  gets its text appended AFTER the site suffix, unmapped items get
  nothing, and the note also rides a safer retry.

  A refusal (`ItemRefused`) skips just that item and the run
  continues; when `safer_retry` is on the item is re-sent ONCE with the
  preamble that matches the refusal's `category` — `RETRY_PREAMBLES[exc.
  category]` — and only a second refusal counts as REFUSED. The safer
  retry catches EVERY per-item verdict of its own attempt
  (`ItemRefused`, `NoImage`, `ImageGenFailed`, `GenerationTimeout`,
  `SendVanished`, `SendNotConfirmed`), not
  just a second refusal (owner 2026-08-04, the 18:43:46 stop: a
  `NoImage` raised inside the retry flew past the outer per-item
  catches — Python never routes an exception from one `except` block
  to its siblings — and stopped the WHOLE site); quota
  (`TerminalState`) still propagates. `NoImage`
  never stops the site: `had_text=True` is LOUD-SKIPPED immediately
  (never nudged); `had_text=False` with `continue_nudge` on (the
  default) sends `CONTINUE_NUDGE` ONCE and uses a recovered image as a
  normal success; a nudge that raises `NoImage` again loud-skips the
  item. **`SendVanished`** (F1b, owner 2026-08-04 — the Padmé/Qui-Gon
  incident): the site DROPPED our confirmed message — the recovery
  re-sends the item's OWN prompt ONCE (never the content-blind nudge,
  which regenerated the PREVIOUS request and saved a Qui-Gon badge as
  `Padme_v3_gem.png`); a second vanish is a loud per-item skip.
  **`SendNotConfirmed`** (owner 2026-08-11) rides the same handler:
  the send provably did not take, so the same safe re-send applies.
  **`GenerationTimeout`** is a per-item skip on the FIRST attempt too
  (owner 2026-08-11) — it was catchable in every nested handler but
  not there, so one item whose result never arrived could end the site.
  `ImageGenFailed` is likewise listed in every nested handler now: it
  was left out of the 2026-08-04 fix and kept the same hole open (the
  18:55:54 stop, a run ended at 38/69 collections). **Duplicate guard:** a result whose bytes hash identical to the
  PREVIOUS save this run means the site re-served the old image — one
  fresh re-submit, then a loud skip; a duplicate file is never silently
  saved. **Model degradation:** see the section above.
  **BUG 3 recovery LADDER:** see the section above. Terminal/driver
  errors propagate to the caller — the report stays saved (resume is
  by the files already on disk). A `TerminalState` is re-raised
  UNCHANGED, so callers read its `retry_after_s`; the runner logs it
  first and stamps it into the report's stop reason.
- `wait_while_paused(should_pause, should_stop, log, emit) -> bool`
  (owner 2026-07-21) — the Pause wait itself, see **Pause** above;
  public (not a `run_sheet`-only helper) so the GUI's tool / AI-check
  worker loops share the exact same poll-wait instead of a second copy
  of the logic.

## 2026-08-11 — transcript, refusal diagnostic, recovery split

- **The recovery ladder moved out** ([Recovery](recovery.md)): when the
  transcript/diagnostic work pushed `runner.py` over the god-file line
  guard, `_recover_image_failed` + the Stop-aware sleep split into
  `painter/recovery.py` (moved whole; the runner's `ImageGenFailed`
  handler now calls `recover_image_failed`, `_pause` shares
  `interruptible_sleep`).
- **The AI response transcript** ([Transcript](transcript.md)):
  `run_sheet` builds one `Transcript` per run and its per-item `t_rec`
  helper records every outcome (`refused` / `retry_failed` /
  `no_image` / `skipped` / `diagnosis` / `saved`) with the FULL raw
  response text from `driver.last_response_text`.
- **The refusal diagnostic question** (owner 2026-08-11): when a
  refusal survives the safer retry (every retry the run allows is
  spent), the runner asks `REFUSAL_DIAGNOSTIC_QUESTION` once via
  `driver.ask_text` — text only, no image burned — and the answer
  lands in the transcript, the report txt (`WHY (site's answer)` line
  via `RunReport.diagnosis`) and the `item_refused` event's
  `diagnosis` field (shown by the dashboard's double-click viewer).
  Best-effort: a failed question never fails the run; duck-typed
  drivers without `ask_text` (the API job, tests) simply skip it.
- **`item_refused` now carries `reason` (+ `diagnosis`)** — the GUI
  stores them per drop path (`DashPanel._refused_info`).

## 2026-08-11b — condensed NOT ELIGIBLE log

Prompt+Image mode's exclusions log ONE summary line per reason
("N item(s) — first four names … +M more") instead of a line per item
(the 69-collection run drowned the log); the FULL per-item list still
lands in the report txt via `report_skips` — nothing silently dropped.
