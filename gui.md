# GUI

**Script:** [GUI (script)](gui.py)

## Purpose
The owner's front door — a themed tkinter window over the same
engine the CLI uses, built for unattended batches: queue the
themes, press Start, go ride a bike. A `clam`-themed ttk look
(setup_style) gives the whole app consistent fonts, padding and
accent colours; reusable `ScrollFrame` and `Expander` widgets back
the dashboard and the selection list.

## The window

- **Themes** — a QUEUE of one or more prompt-sheet `.md` files
  (each file is one THEME; Add / Remove / Clear). Each site works
  through the queue in order, closing theme after theme; broken
  sheets are reported and dropped from the run, never half-driven.
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
- **Report txt** — the per-theme report beside the images:
  start/finish timestamps, per-image generate + process times,
  original → final resolution, file size, extra actions (REMOVE
  BG), averages and totals.
- **Safer retry on refusal** — opt-in: on a SAFETY refusal, re-send
  the item ONCE with an allegory-framing preamble before giving up.
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
- **Pause / Action delay** — both are random FROM–TO ranges: the
  pause between prompts (fractional seconds) and the human-like
  hesitation between UI steps (click → paste → send, default
  0.2–0.6 s — never instant).
- **Instructions** — opens the sheet-authoring guide
  (`instructions.md`) for whoever writes the next sheet.
- **Two views** (tabs): the **Dashboard** and the **Log
  (detailed)** (timestamped `[HH:MM:SS]`, both sites interleaved
  with `[gemini]` / `[chatgpt]` prefixes). A SAFETY refusal skips
  only that image (REFUSED in log + report; a rerun retries it). A
  quota stop (`TERMINAL STATE`) stops only that site's queue — the
  other continues; the next Start resumes what remains.

## The Dashboard
Two scrollable columns, one `DashPanel` per site, fed ONLY by the
runner's structured events (never by log-parsing):

- **Task** — a whole-run progress bar and `done / total
  (themes-done/themes)` across every queued theme (pre-counted at
  Start by `_plan`, which mirrors the runner's queue rule).
- **Theme / Image** — the current theme, the current image, and a
  per-theme progress bar.
- **Stats table** — two columns, `This theme` and `Task`, over
  Done, Refused, **Generate avg** (SEND → image), **Process avg**
  (image → saved), Tempo (/h) and ETA. Title/value pairs, not one
  crammed line.
- **Completed themes** — a collapsible `Expander` per finished
  theme: `done/total · time · MB · folders`, expanding to every
  file with its generate/process times, resolution and size.

## Threading
One worker thread per site; each creates its own Playwright
instance and `SiteDriver` (sync Playwright is per-thread) and
walks the theme queue sequentially. Workers touch the window ONLY
through a queue drained on the tk timer (`_drain_queue` via
`root.after`) — every widget mutation runs on the main thread.

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md), [CDP Driver](painter/driver.md),
  [Run Loop](painter/runner.md), [Chrome Launcher](painter/chrome.md),
  [Postprocess](painter/postprocess.md), [Config](painter/config.md)

### Used by
- The owner (`python main.py` with no arguments).
