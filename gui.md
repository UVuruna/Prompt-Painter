# GUI

**Script:** [GUI (script)](gui.py)

## Purpose
The owner's front door — a themed tkinter window over the same
engine the CLI uses, built for unattended batches: queue the
collections, press a site's Start, go ride a bike. The widget
stack (2026-07-18) is **customtkinter rounded controls over a
ttkbootstrap `darkly` base — the same mix RHMH uses**: every
button is a `CTkButton` with RHMH's strong corner radius (12 px,
hover = the same colour darkened to 0.75), the output path field a
rounded bordered `CTkEntry`, the pace fields compact `Spinner`s
(ONE reusable class — a rounded `CTkFrame` holding
[−] [entry] [+]: ~24 px pads, step 1 s for the pauses, 0.1 s for
the action delays, direct typing still allowed and validated on
Start, never below 0), the background / New-chat dropdowns rounded
`CTkComboBox`es, the option toggles `CTkSwitch`es, and each site's
whole control set an `AgentPanel` labelframe with the site's LOGO
in its header. All
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
(`compound="left"`). The five PNGs the svgs replaced
(add/clear/remove/right/start) were DELETED (2026-07-18);
`assets/icons/` now holds only the svgs plus `web.png`, `ai.png`
and the `gemini.png` sibling.

**Global font zoom** (2026-07-18) — CSS-rem style: ONE root size
(`FONT_BASE`, default 10, clamped 7–20) and a role table of
multipliers (`FONT_ROLES`: root 1.0, bold 1.0, head 1.1, title
1.6, spin 1.2, mono 0.9, doc_h1 1.5, doc_h2 1.2 — the exact
pre-zoom ratios). Every font in the GUI — the ttk styles, all CTk
factories/Spinner, the Treeview body+heading fonts, the queue
Listbox, the log Text, DocWindow's body and tags — pulls a SHARED
font object per role from the registry (`tk_font(role)` named tk
fonts / `ctk_font(role)` CTkFonts), so `set_font_base` rescales
the whole window with one `.configure(size=…)` per role; only the
Treeview rowheight (root x 2.4) is re-applied explicitly.
Shortcuts, bound on `all` (SelectWindow/DocWindow answer too, and
new Toplevels open at the current zoom because the shared fonts
ARE the current zoom): **Ctrl+MouseWheel** up/down,
**Ctrl+Numpad +/-**, plain **Ctrl+plus/minus** (and Ctrl+equal
for keyboards without a numpad). The wheel handler returns
"break" and is also bound on the Text/Listbox/Treeview class tags
so Ctrl+wheel zooms without ALSO scrolling the widget under the
pointer.

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
- **The two AGENT PANELS** (2026-07-18, full per-agent
  separation) — ChatGPT and Gemini each get their OWN
  `AgentPanel` labelframe (site logo in the header) holding
  everything below the shared Output line: the **background
  dropdown** (`transparent` / `white` / `none`, preselected to the
  site's default — ChatGPT transparent, Gemini white; Gemini's
  three laws still ride along automatically), the three composable
  **post-save switches** — `BG removal`, `Crop`, `Upscale` (all ON
  by default; each site's post-save pipeline runs exactly ITS
  ticked steps, in that order, loud on failure but never killing
  the run), **Report txt**, **Safer retry**, the **New chat** mode,
  its own **pause** and **action delay** Spinner ranges, and its
  own **Start / Stop** pair. A site "participates" in a run by
  being STARTED — there are no site on/off switches any more, and
  one site running never blocks starting the other. Start/Stop
  availability is STYLED (`style_action_button`): an available
  button is FILLED with its colour (solid green Start / solid red
  Stop), an unavailable one is a disabled OUTLINE — re-applied on
  every run-state change (while a quota auto-restart is pending,
  BOTH are available: Start starts earlier, Stop cancels the
  timer).
- **Open Chrome (login)** — launches the automation Chrome with
  both sites' tabs (dedicated `chrome-profile/`; log in once,
  sessions persist).
- **Check sheets** — parses the whole queue into the log AND
  switches the view to the Log tab so the output is immediately
  visible.
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
  pending. The window opens SIZED TO ITS CONTENT width (clamped to
  90 % of the screen) with every section COLLAPSED, and a
  section's rows — hundreds of checkbuttons across a big queue,
  the old eager build was the window's lag — are built LAZILY on
  its first expand.
- **BG removal only... / CROP only... / UPSCALE only...** — the
  three standalone in-place tools (one at a time): pick a folder,
  confirm, and the engine function (`remove_background` /
  `crop_transparent` / `upscale_if_small`) runs over every image
  under it, in order. They are site-less, so progress reports on
  the FIRST VISIBLE dashboard panel (its counters restart for the
  run): done = the file was changed, REFUSED = the engine said
  "nothing"/"unclear" — nothing to do for that file (for Upscale:
  failed the gate — aspect outside 0.9–1.1 or both sides already
  ≥ 800).
- **Stop** — graceful: the site finishes its current item;
  everything finished is already saved.
- **Pause / Action delay** — both are random FROM–TO ranges: the
  pause between prompts (fractional seconds) and the human-like
  hesitation between UI steps (click → paste → send, default
  0.2–0.6 s — never instant). All four fields per panel are the
  compact `Spinner` units ([−]/[+] step or type directly).
- **Instructions** — opens the sheet-authoring guide
  (`instructions.md`) in the in-app `DocWindow` — light Markdown
  formatting, selectable read-only text, and a **Copy (for AI)**
  button — so a non-programmer never needs a code editor. Every
  `DocWindow` opening (instructions, a collection file, a folder
  excerpt, a single prompt) sizes its WIDTH to the text content
  (clamped to 90 % of the screen).
- **Two views** (tabs): the **Dashboard** and the **Log
  (detailed)** (timestamped `[HH:MM:SS]`, both sites interleaved
  with `[gemini]` / `[chatgpt]` prefixes). A SAFETY refusal skips
  only that image (REFUSED in log + report; a rerun retries it). A
  quota stop (`TERMINAL STATE`) stops only that site's queue — the
  other continues. When the site named its reset time
  (`TerminalState.retry_after_s`), the GUI schedules a **QUOTA
  AUTO-RESTART** — reset + a polite random 30–120 s, live
  countdown ("quota — auto-restart in MM:SS") on the site's
  dashboard panel; it fires whenever the app is open. That site's
  Stop cancels the pending restart, its Start just starts earlier
  (cancelling the timer); an unparseable reset keeps the plain
  stop behaviour.
- **Settings persistence** (`painter/settings.py`) — remembered
  across starts: the queue file list, the output folder, EVERY
  per-agent panel setting, the font zoom base, the dashboard sash
  position and the window geometry (selection ticks stay
  per-run). Saves debounce on every meaningful change (var
  traces, queue edits, zoom, sash release) and always fire on
  close; loading applies missing keys as current defaults and
  drops queued files that no longer exist (reported in the log).
  The stored dict: `queue` (list of paths), `output`,
  `font_base`, `sash`, `geometry`, and `agents.<site>` with
  `background`, `bg_removal`, `crop`, `upscale`, `report`,
  `safer_retry`, `new_chat`, `pause_min/max`, `act_min/max`.

## The Dashboard
One `DashPanel` per site, fed ONLY by the runner's structured
events (never by log-parsing). The panels live in a horizontal
`ttk.PanedWindow` — DRAG the divider to give one panel more width
(the sash position persists in the settings). The tab is
ADAPTIVE: a panel shows only while its site is RUNNING (or
waiting on a quota restart) or once it HAS DATA — a single
visible panel takes the full width, no sash; when nothing runs
and nothing has data yet, both show. Hidden panels keep all their
state. Each panel (title, then the state line — the quota
countdown lives there):

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
  · Size), both scrollbars, everything column-aligned; every column
  (Name included) has `stretch=False`, so widening Name grows the
  tree's content width and the horizontal scrollbar takes over
  instead of squeezing the other columns:
  1. **Collection** — `Done` (done/total), `Time` (wall), `Size`.
  2. **Folder** (the drop-path directory) — `Done` (count in that
     folder), `Time`, `Size`, same columns as the collection.
  3. **Image** — `AI` (generate), `Ours` (fills after its pause),
     `Res`, `Size`.
  The RUNNING collection appears live and open, images streaming in
  under their folder as they save; it collapses when done. **Show**
  (with its right-arrow icon; or double-click a row) opens, in the
  same formatted viewer: a COLLECTION row — its whole file; a
  FOLDER row — only that folder's excerpt of the sheet (from the
  first member entry through the last one's prompt fence, titled
  with the folder name); an IMAGE row — its own prompt AND, when
  the destination file already exists, the saved image below it,
  scaled to fit the window width.

## Threading
One worker thread per site, started and stopped INDEPENDENTLY by
its panel's buttons (per-site stop events); each creates its own
Playwright instance and `SiteDriver` (sync Playwright is
per-thread) and walks the theme queue sequentially. Workers touch
the window ONLY through a queue drained on the tk timer
(`_drain_queue` via `root.after`) — every widget mutation runs on
the main thread; a quota `TerminalState` posts its
`retry_after_s` the same way and the main thread schedules the
auto-restart via `root.after`. The standalone tools run on one
extra worker (one at a time).

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md), [CDP Driver](painter/driver.md),
  [Run Loop](painter/runner.md), [Chrome Launcher](painter/chrome.md),
  [Postprocess](painter/postprocess.md), [Upscale](painter/upscale.md),
  [Settings](painter/settings.md), [Config](painter/config.md)

### Used by
- The owner (`python main.py` with no arguments).
