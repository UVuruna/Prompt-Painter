# GUI

**Script:** [GUI (script)](gui.py)

## Purpose
The owner's front door — a small tkinter window over the same
engine the CLI uses, built for unattended batches: queue the
sheets, press Start, go ride a bike.

## The window

- **Sheets** — a QUEUE of one or more `.md` files (Add / Remove /
  Clear). Each site works through the queue in order, closing
  sheet after sheet; broken sheets are reported and dropped from
  the run, never half-driven.
- **Output** — the folder; images save DIRECTLY to
  `<out>/<site>/<drop-path>` (no approval step).
- **Sites** — Gemini / ChatGPT checkboxes; both ticked = both run
  IN PARALLEL, one thread and one tab each. Beside each site sits
  its own **background dropdown** (`transparent` / `white` /
  `none`), preselected to the site's default — ChatGPT
  transparent, Gemini white. Gemini's three laws ride along
  automatically: the aspect law picked per prompt (badges 1:1,
  TALL lancets portrait), the background, and no reflections.
- **Background fix** — runs the in-house remover after every save.
- **Write report txt** — the per-sheet report beside the images:
  start/finish timestamps, per-image generation time, original ->
  final resolution, extra actions (REMOVE BG), average and totals.
- **Pause** — FROM–TO seconds; each pause is a random duration in
  that range (fractional, e.g. 12.56 s).
- **Open Chrome (login)** — launches the automation Chrome
  (dedicated `chrome-profile/`; log in once, sessions persist).
- **Check sheets** — parses the whole queue into the log.
- **Select images...** — the tick list, PER SITE: every sheet's
  items with one checkbox column per site (all/none toggles per
  sheet), so ChatGPT and Gemini can run different image lists.
  Already-done items (per the site's progress under the current
  output folder) show disabled; sheet-ADVISED items (REUSE /
  not-approved sections) show unticked with the ⚠ reason — tick
  them to generate them anyway. Without any explicit ticks, a run
  skips advised items by default. Rows are COLOR-CODED: green =
  done on both sites (olive = done on one), red = SUPERSEDED
  advice, orange = other advice (not approved / REUSE), default =
  pending.
- **BG removal only...** — standalone background removal, in
  place, over any existing folder (confirmation first;
  already-transparent and unclear images are skipped untouched).
- **Start / Stop** — Stop is graceful: each site finishes its
  current item; everything finished is already saved.
- **Log** — timestamped (`[HH:MM:SS]`), both sites interleaved
  with `[gemini]` / `[chatgpt]` prefixes. A SAFETY refusal skips
  only that image (REFUSED in log + report; a rerun retries it). A
  quota stop (`TERMINAL STATE`) stops only that site's queue — the
  other continues; the next Start resumes what remains.

## Threading
One worker thread per site; each creates its own Playwright
instance and `SiteDriver` (sync Playwright is per-thread) and
walks the sheet queue sequentially. Workers talk to the window
only through a queue drained on the tk timer.

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md), [CDP Driver](painter/driver.md),
  [Run Loop](painter/runner.md), [Chrome Launcher](painter/chrome.md),
  [Postprocess](painter/postprocess.md), [Config](painter/config.md)

### Used by
- The owner (`python main.py` with no arguments).
