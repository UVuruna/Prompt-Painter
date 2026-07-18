# GUI

**Script:** [GUI (script)](gui.py)

## Purpose
The owner's front door — a themed tkinter window over the same
engine the CLI uses, built for unattended batches: queue the
collections, press Start, go ride a bike. The widget stack
(2026-07-18) is **customtkinter rounded controls over a
ttkbootstrap `darkly` base — the same mix RHMH uses**: every
button is a `CTkButton` with RHMH's strong corner radius (12 px,
hover = the same colour darkened to 0.75), the output path and
pace fields are rounded bordered `CTkEntry`s, the background /
New-chat dropdowns rounded `CTkComboBox`es, the site and option
toggles `CTkSwitch`es. All their colours are PULLED from the live
darkly palette (`tb.Style().colors`) by the `rounded_button` /
`rounded_entry` / `rounded_combo` / `rounded_switch` factories and
`_button_colors` (semantic kinds: secondary, success Start, danger
outline Stop, info Copy, outlines, flat link and ▶/▼ expander), so
the CTk and ttk families read as ONE dark look; appearance is
pinned with `ctk.set_appearance_mode("dark")`. What stays ttk:
the `Treeview` table, `Notebook` tabs, striped progressbars, round
scrollbars, labels/frames — darkly widgets CTk has no better
equivalent for — plus the Select grid's hundreds of per-image
checkbuttons (deliberately light widgets). `setup_style` only adds
the few named label styles darkly lacks; `dark_text` /
`dark_listbox` skin the plain tk widgets from `Style().colors`,
and the four semantic STATUS colours (done green, olive one-site,
advice orange, superseded red) stay named constants aligned to
darkly's accents. A reusable `ScrollFrame` backs the selection
list and a `ttk.Treeview` is the dashboard's collection table.

**Button icons** (2026-07-18) are PNGs REUSED from the RHMH
project's icon set, copied into `assets/icons/` (RHMH untouched):
`add` / `remove` / `clear` on the queue buttons, `web` (globe) on
Open Chrome, `start` (play) on Start, `right` on the dashboard's
Show button, `ai` on DocWindow's Copy (for AI). The module-level
`icon()` loader resolves them beside `gui.py` (never the CWD),
loads each PNG through Pillow into a `CTkImage` scaled to ≤20 px
(smooth resampling — sharper than the old `PhotoImage.subsample`),
and caches every image in `_ICONS` for the process lifetime so all
buttons share one instance per icon. A missing icon file raises
`FileNotFoundError` loudly (root Rule #1); buttons keep their text
(`compound="left"`).

## The window

- **Collections** — a QUEUE of one or more prompt `.md` files (each
  file is one COLLECTION — a set of images to make: a theme, an icon
  set, a landscape series …; Add / Remove / Clear). Each site works
  through the queue in order, closing collection after collection;
  broken files are reported and dropped, never half-driven. Two
  queued files that share a filename are refused (their progress and
  report would collide).
- **Output** — the folder; images save DIRECTLY to
  `<out>/<site>/<drop-path>` (no approval step).
- **Sites** — Gemini / ChatGPT switches; both ticked = both run
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
- **Safer retry on refusal** — ON by default: on a SAFETY refusal,
  re-send the item ONCE with an allegory-framing preamble before
  giving up (then it just moves on — rework the prompt later).
- **New chat** — `off` / `collection` (default: a fresh chat after
  every finished collection) / `folder` (also between folder groups
  INSIDE a collection, primary → colored …). A failed New-chat
  click is loud but never stops the run (the old chat still works,
  just longer).
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
  (`instructions.md`) in the in-app `DocWindow` — light Markdown
  formatting, selectable read-only text, and a **Copy (for AI)**
  button — so a non-programmer never needs a code editor. The same
  `DocWindow` shows a collection file or a single prompt (Show).
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
  (done/collections)` across every queued collection (pre-counted
  at Start by `_plan`, which mirrors the runner's queue rule).
- **File / Image** — the current collection file, the current
  image, and a per-collection progress bar.
- **Stats table** — two columns, `This one` and `Whole run`. Rows:
  Done, Refused, a collapsible **Average** (its value is the total
  per-image time; click ▶ to break it into **AI generation**, **Our
  processing** (save+bgfix+pause), **Minimum** and **Maximum**),
  then Tempo (/h) and ETA. Title/value pairs, not one crammed line.
- **Collections (running + done)** — a `ttk.Treeview` TABLE, three
  levels deep, column headers (Name · Done · AI · Ours · Res · Time
  · Size), both scrollbars, everything column-aligned:
  1. **Collection** — `Done` (done/total), `Time` (wall), `Size`.
  2. **Folder** (the drop-path directory) — `Done` (count in that
     folder), `Time`, `Size`, same columns as the collection.
  3. **Image** — `AI` (generate), `Ours` (fills after its pause),
     `Res`, `Size`.
  The RUNNING collection appears live and open, images streaming in
  under their folder as they save; it collapses when done. **Show**
  (with its right-arrow icon; or double-click a row) opens the
  selected collection's whole file,
  or a single image's own prompt, in the same formatted viewer.

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
