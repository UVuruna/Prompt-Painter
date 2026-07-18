# GUI

**Script:** [GUI (script)](gui.py)

## Purpose
The owner's front door — a themed tkinter window over the same
engine the CLI uses, built for unattended batches: queue the
collections, press Start, go ride a bike. The widget stack
(2026-07-18) is **customtkinter rounded controls over a
ttkbootstrap `darkly` base — the same mix RHMH uses**: every
button is a `CTkButton` with RHMH's strong corner radius (12 px,
hover = the same colour darkened to 0.75), the output path field a
rounded bordered `CTkEntry`, the four pace fields compact
`Spinner`s (ONE reusable class — a rounded `CTkFrame` holding
[−] [entry] [+]: ~24 px pads, step 1 s for the pauses, 0.1 s for
the action delays, direct typing still allowed and validated on
Start, never below 0), the background / New-chat dropdowns rounded
`CTkComboBox`es, the site and option toggles `CTkSwitch`es with
the site's LOGO in a small `CTkLabel` beside each site switch. All
their colours are PULLED from the live darkly palette
(`tb.Style().colors`) by the `rounded_button` / `rounded_entry` /
`rounded_combo` / `rounded_switch` factories and `_button_colors`
(semantic kinds: secondary, success Start, danger outline Stop,
info Copy, outlines, flat link and ▶/▼ expander), so the CTk and
ttk families read as ONE dark look; appearance is pinned with
`ctk.set_appearance_mode("dark")` and every factory pins
`bg_color` to the darkly window background so rounded corners
never show a foreign gray on ttk parents. Two smooth-field fixes
live in the factories (2026-07-18): `_untheme_inner_entry`
unsubscribes the `tkinter.Entry` INSIDE every CTkEntry/CTkComboBox
from ttkbootstrap's constructor-hook re-styling and drops its
`highlightthickness=1` square ring (the "lighter square inside the
rounded field" defect), and `EdgeIconButton`
(`rounded_button(..., icon_edge=True)`, the stacked
Add…/Remove/Clear queue buttons) re-grids CTkButton's internal 5x5
layout so the ICON pins to the left edge while the TEXT centers in
the remaining width. What stays ttk:
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

**Icons** (2026-07-18) are SVG-FIRST: the owner's
`assets/icons/*.svg` (`add` / `remove` / `clear` on the queue
buttons, `start` (play) on Start, `right` on the dashboard's Show
button, `chatGPT` / `gemini` as the site-switch logos) rasterized
through Qt's `QSvgRenderer` (PySide6 — already the monorepo build
pipeline's SVG engine; a lazy, never-exec()-ed `QGuiApplication`
serves only offscreen painting) at 4x the target size and
LANCZOS-downscaled for crispness. PNG stays the fallback for icons
with no svg (`web` on Open Chrome, `ai` on DocWindow's Copy) AND
for svgs QtSvg cannot render: QtSvg implements the SVG *Tiny*
profile, so a file using `clipPath`/`mask`/`filter` (Illustrator
raster-trace exports — `gemini.svg` is 12 embedded rasters under
28 clipPaths) is detected by tag-sniffing the bytes and loaded
from its pre-rasterized `.png` sibling instead (`gemini.png` was
rendered ONCE from the svg via chromium, transparent, 512 px).
The module-level `icon(name, size=20)` loader resolves beside
`gui.py` (never the CWD), returns a `CTkImage`, and caches per
(name, size) in `_ICONS` for the process lifetime. A missing icon
— or a Tiny-unrenderable svg with no png sibling — raises
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
- **Sites** — Gemini / ChatGPT switches, each with its site logo
  beside it; both ticked = both run
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
  0.2–0.6 s — never instant). All four fields are the compact
  `Spinner` units ([−]/[+] step or type directly).
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
