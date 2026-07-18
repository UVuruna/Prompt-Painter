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
their colours come from the active theme (see **Theming** below) via
the `rounded_button` / `rounded_entry` / `rounded_combo` /
`rounded_switch` factories and `_button_colors` (semantic kinds:
secondary, success Start, danger outline Stop, info Copy, outlines,
flat link and ▶/▼ expander) — every CTk colour kwarg is a fixed
`(day, night)` tuple via `theme_pair()`, so a single
`ctk.set_appearance_mode()` flip repaints all CTk controls with zero
re-walk; every factory also pins `bg_color` to the active window
background so rounded corners never show a foreign gray on ttk
parents. Two smooth-field fixes
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
equivalent for — plus the whole Select tree (frames, wrapped
labels, per-site checkbuttons — deliberately light widgets; NO CTk
inside a scroll canvas, since a CTkButton is a drawn canvas that
re-renders on every configure). `setup_style` only adds
the few named label styles the base theme lacks (re-run on every
flip); `skin_text` / `skin_listbox` / `skin_canvas` /
`skin_toplevel` colour the plain tk widgets from `Style().colors`
AND register them in the `THEMED_TK` role registry so a flip
re-tints them; the semantic STATUS colours (done, olive one-site,
advice, superseded, code text) live PER THEME in `THEMES[*].status`
and are read live through `status(role)`. A reusable `ScrollFrame` backs the selection
tree, WRAPS the whole main window (see **Collapse & global scroll**),
and a `ttk.Treeview` is the dashboard's collection table.
`ScrollFrame` COALESCES its scrollregion: a body `<Configure>`
only schedules ONE `after_idle` `bbox('all')` pass, so an expand
that grids dozens of children costs one geometry scan, not one per
child; `suspend_scrollregion` / `resume_scrollregion` pause even
that during a bulk build (the Select tree's Expand-all) so the
O(content) `bbox` scan runs ONCE at the end, not once per chunk.
An optional `fill_height=True` (the whole-window wrap uses it)
keeps the body window AT LEAST as tall as the canvas — so a child
packed `expand=True` (the Dashboard notebook) fills the viewport
when the content is shorter than the window — behind a change-guard
that breaks the itemconfigure→`<Configure>`→recompute loop
(`winfo_reqheight` is invariant under the forced height, so one
settle converges); `refresh()` re-fits after a collapse/expand.
The module-level `folder_of(drop_path)` (a drop path's
POSIX parent, `(root)` fallback) is the shared L2 folder identity
for both the dashboard tree and the Select window.

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

**Collapse & global scroll** (2026-07-18) — two window-wide
reachability fixes:

- **Collapsible controls** — a `▾ Controls` toggle (top strip, left
  of the Day/Night switch) collapses the WHOLE upper control area
  (the Collections queue, Output row, both `AgentPanel` bodies and
  the standalone-tools button row — all held in `self._controls_box`)
  down to a thin per-agent strip (`self._compact_box`): one
  `[logo] Name [Start][Stop]` cluster per site, so the Dashboard/Log
  notebook takes the full height while the owner watches a run.
  Nothing is destroyed — the swap is `pack_forget` ↔
  `pack(before=self.notebook)`, so every StringVar/Spinner/Listbox
  keeps its state and `before=` pins the vertical order regardless of
  build order. `AgentPanel.build_compact()` builds each cluster and
  appends its Start/Stop to the panel's `_button_pairs`; the
  unchanged-signature `set_run_state` loops that list so the compact
  and full buttons ALWAYS share the same filled/outline availability
  and drive the same `_start_site`/`_stop_site`. The glyph flips to
  `▸ Controls` when collapsed; the state persists
  (`controls_collapsed`).
- **Whole-window vertical scroll** — the entire content lives in ONE
  `fill_height` `ScrollFrame` (the top strip is pinned OUTSIDE it, so
  the collapse toggle is always reachable). When the content exceeds
  the window height (a short window, or the owner's stale too-tall
  geometry) the outer view scrolls so the bottom buttons / Dashboard
  bottom are never unreachable. **Wheel routing**: the outer view
  keeps `ScrollFrame`'s `<Enter>`/`<Leave>` → `bind_all` pattern
  (per-canvas scoped, correct for the multi-Toplevel app); the inner
  scrollables get a PERMANENT `bind_class('<MouseWheel>')`
  (`_inner_wheel`) on Treeview/Text/Listbox that scrolls that widget
  and returns `"break"`, halting the bindtag chain BEFORE the outer
  `all`-tag handler — so over a dashboard tree / the Log / the
  Collections list the INNER widget scrolls once (never a
  double-scroll), and over anything else the OUTER view scrolls.
  Ctrl+wheel is untouched: `_bind_zoom`'s `<Control-MouseWheel>` on
  the same class tags is more specific than the plain `<MouseWheel>`,
  so a Ctrl event fires only the zoom (no new guard needed).
- **Geometry cap** — `_clamp_geometry` clamps a restored
  `WxH(+X+Y)` to the screen minus `WINDOW_SCREEN_MARGIN_PX` and on to
  an on-screen offset (below `WINDOW_MIN_W/H` it raises to the min;
  unparseable passes through), applied in `_apply_settings`, so a
  stale `1381x2061` (taller than the owner's screen) can never again
  place the window past the screen edge with the bottom unreachable.

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
- **Select images...** — a PER-SITE 3-LEVEL tree
  (`SelectWindow`): level 1 the COLLECTION (sheet file + theme),
  level 2 the FOLDERS inside it (the drop paths' parent dirs — a
  sheet may have several, e.g. `life` has `tree/` and `animals/`,
  keyed by the shared `folder_of`), level 3 the IMAGE files. Only
  the LEAVES carry checkboxes — one column per site — so ChatGPT
  and Gemini can run different image lists. Every level shows a
  LIVE `selected/total` count per site: the collapsible header
  totals the whole queue per site (accent Head style, e.g.
  `ChatGPT 49/55`), and each collection and folder row shows its
  own `sel/tot`. **Clicking any count is all/none** for that
  scope+site (header = whole site, collection, or folder); it
  flips only the ENABLED (non-done) leaves, and every count
  re-derives live. Already-done items (per the site's progress
  under the current output folder) show disabled + unticked;
  sheet-ADVISED items (REUSE / not-approved sections) show
  unticked with the ⚠ reason truncated — tick them to generate
  them anyway. Without any explicit ticks a run skips advised
  items by default (eager var materialisation is run-safe: the
  default advice-free, not-done set equals the runner's own
  "never opened Select" rule). Leaf names are COLOR-CODED: green =
  done on both sites (olive = done on one), red = SUPERSEDED
  advice, orange = other advice, default = pending — and a
  **colour LEGEND** under the top hint bar spells out those four
  (BOTH DONE / ONE SITE DONE / SUPERSEDED / ADVICE), each label
  painted in its own live status colour so a Day/Night flip
  recolours it too. The window is sized FIT-CONTENT
  (`_fit_content_width`): a bounded `font.measure` sweep over just
  the ~30 L1 collection titles (+ their L2 folder paths, never the
  leaves) picks the width so the widest title stays on ONE line,
  clamped to `[SELECT_MIN_W, screen*DOC_MAX_FRAC]`; the
  `ttk.Label(wraplength=)` follows that width so only genuinely
  over-long names wrap (recomputed on resize/zoom). The two
  fixed-width per-site columns stay aligned however deep a row is.
  **Performance** (the owner's "a collapsible list must not lag"):
  the body is plain ttk only, L1/L2 nodes are always materialised
  (cheap — a few dozen) while L3 leaf rows are BUILT on a folder's
  open and DESTROYED on its close (live widgets track only open
  folders, never accumulating), counts update via ONE coalesced
  `after_idle` recount driven by a dirty flag (a var trace just
  raises the flag — the traces are detached on window close), and
  the scrollregion is coalesced too. **Expand all** would otherwise
  materialise EVERY leaf in one synchronous geometry pass (~280
  wraplength rows ≈ 3 s frozen at the owner's real queue); instead
  it builds FOLDER-ATOMIC chunks across `after()` ticks
  (`SELECT_EXPAND_CHUNK` leaves per tick ≈ 120 ms median block),
  suspends the scrollregion scan for the run, and shows a live
  `Expanding… done/total (pct)` cue (root Rule #10) — the tree
  fills in progressively and the main thread is never blocked; any
  manual toggle / Collapse-all cancels an in-flight expand cleanly
  (folders are atomic, so the tree is always in a consistent
  built-or-not state to stop at). The window opens at the
  fit-content width above and a screen-tall height
  (`screen*DOC_HEIGHT_FRAC`, floored at `SELECT_OPEN_H`) with every
  section COLLAPSED — the L1-title measure is bounded (~30 titles),
  never the old open-time sweep over every leaf.
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
  button — so a non-programmer never needs a code editor.
  `DocWindow` sizes in TWO modes (replacing the old longest-line
  measure that blew the window near full-screen on a ~200-word
  one-line prompt): the SINGLE-IMAGE prompt viewer (`image_path`
  set) sizes its WIDTH to the IMAGE — native width + `DOC_IMG_PAD_PX`,
  clamped to `screen*DOC_MAX_FRAC` — so the picture shows large and
  the prompt WRAPS into that column above it; every TEXT opening
  (instructions, a collection file, a folder excerpt) uses a
  portrait A4 width (`screen*DOC_HEIGHT_FRAC*DOC_A4_RATIO`, clamped
  `[DOC_MIN_W, screen*DOC_MAX_FRAC]`) so long one-line prompts wrap
  into a readable column. The HEIGHT is fitted to the rendered
  content (`_fit_height` measures the Text's `ypixels` on the first
  `<Map>`, when it is finally laid out) and clamped to
  `screen*DOC_MAX_FRAC`, so a short excerpt shrinks to content while
  a tall medallion / long doc scrolls.
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
- **Day/Night switch** (top-right, `DayNightSwitch`) — a mini
  image pill ported from the owner's website switch: OFF/left =
  MOON on the dark starfield track (NIGHT = the dark theme),
  ON/right = SUN with a soft glow on the sky-and-clouds track
  (DAY = the light theme). CRISP (owner 2026-07-18): the pill is
  composited from ANTI-ALIASED PIL images — the two tracks straight
  from the website SVGs, the sun/moon knobs rendered supersampled
  with a radial gradient — because tkinter Canvas cannot anti-alias
  raw ovals. A click flips the WHOLE app SYNCHRONOUSLY (coherent
  instantly) and persists the choice, then a ~600 ms smoothstep
  slide runs as flourish. See **Theming**.
- **Settings persistence** (`painter/settings.py`) — remembered
  across starts: the output folder, EVERY per-agent panel setting,
  the font zoom base, the **theme** (`day` / `night`), the dashboard
  sash position, the window geometry and the **collapsed/expanded**
  controls state (selection ticks stay per-run). The **collection queue is NOT persisted** — the app
  starts with an empty list every launch (owner 2026-07-18); and a
  saved output folder that no longer exists is ignored in favour of
  the default `out/`, so done-detection never reads an empty
  `_state`. Saves debounce on every meaningful change (var traces,
  zoom, sash release, theme flip) and always fire on close; loading
  applies missing
  keys as current defaults (a missing `theme` = `night`) and drops
  queued files that no longer exist (reported in the log). The
  stored dict: `queue` (list of paths), `output`, `font_base`,
  `theme`, `sash`, `geometry`, `controls_collapsed`, and
  `agents.<site>` with `background`, `bg_removal`, `crop`, `upscale`,
  `report`, `safer_retry`, `new_chat`, `pause_min/max`, `act_min/max`.

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

## Theming
Two coordinated palettes — **night** (the built-in `darkly`, kept
byte-for-byte: the owner is happy with the dark look) and **day** (a
custom light theme, the owner's warm-gold website palette) — flipped
as ONE by the top-right `DayNightSwitch`. The single source of truth
is `THEMES` in [Config](painter/config.md): each entry
carries its ttkbootstrap theme name, the customtkinter appearance
mode, the switch knob side, the 16 ttkbootstrap colour keys and a
`status` block (the semantic colours set PER WIDGET at construction).
`config.py` stays framework-free (pure hex data), so the engine and
all tests import it without tkinter/ttkbootstrap.

**The three widget families each flip differently — and each is
covered so NO widget is ever stranded in the other theme** (the bug
the owner caught in an accidental half-light window):

- **customtkinter** — every colour kwarg in the factories is a fixed
  `(day, night)` tuple via `theme_pair()` (and `status_pair()` for
  the solid-button text, `_darken_pair()` for hover shades). CTk
  stores the tuple and re-resolves it per mode, so a single
  `ctk.set_appearance_mode()` repaints EVERY CTk control with zero
  re-walk. `style_action_button` takes a semantic KEY
  (`success`/`danger`) for the same reason — its runtime Start/Stop
  recolour stays a tuple.
- **ttkbootstrap** — `Style().theme_use()` swaps the theme and
  `setup_style()` is re-run (it reads `style.colors` live, so it
  reproduces the named styles in the new palette). ttk looks styles
  up at draw time, so this updates every style-driven widget with no
  per-widget work. The custom `painter_day` theme is registered ONCE
  at startup (`register_painter_day`, idempotent) via
  `Style().register_theme(ThemeDefinition(...))`.
- **plain tk** (Text / Listbox / Canvas / Toplevel) — created through
  `skin_text` / `skin_listbox` / `skin_canvas` / `skin_toplevel`,
  which colour the widget AND append `(widget, role)` to the flat
  `THEMED_TK` registry; `recolor_tk_registry()` re-walks it on a
  flip, re-applying each role's skin and pruning dead widgets via
  `tk.TclError`. This is the ONLY place plain-tk colours live.

**`apply_theme(name)`** is the ONE coherent flip, used by BOTH
startup and the toggle: set the module `ACTIVE_THEME` → `theme_use`
→ `setup_style()` → `set_appearance_mode()` → `recolor_tk_registry()`
→ fire every open Toplevel's `apply_theme()`. It NEVER tears down the
window, so an active run's worker threads, dashboard counters and
quota countdowns survive a flip. **Open Toplevels** (`SelectWindow`,
`DocWindow`) each register in `THEME_TOPLEVELS` on `__init__`,
unregister on `<Destroy>`, and expose their own `apply_theme()` —
because their per-widget foregrounds (Select tree leaf colours + the
header progress label, DocWindow's Text tags) do NOT follow ttk
styles and must be recomputed from `status()`/`colors` live (Select
retains each leaf's `advice` + `n_done` to recompute its colour).

**Startup order** (`PainterGui.__init__`) applies the saved theme
BEFORE building any widget — `register_painter_day()` → load settings
→ font zoom → `apply_theme(saved_theme)` → pin a thin top strip
(Day/Night switch + `▾ Controls` toggle) on the `shell`, then wrap
the rest in ONE `fill_height` `ScrollFrame` whose body holds the
collapsible controls, compact strip and the Dashboard/Log notebook →
`_bind_zoom` / `_bind_wheel_routing` / `_set_collapsed(False)` →
`_apply_settings` (which caps the geometry and may restore the
collapsed state). Because the theme is live before the first widget
is born, CTk tuples
resolve to the right end and tk skinners read the active palette — no
first-frame flash, no half-theme window. The chosen theme persists in
`settings.json` (`theme` key, missing = `night`).

**The switch** (`DayNightSwitch(tk.Canvas)`) composites the whole
pill from ANTI-ALIASED PIL images (owner 2026-07-18 — raw tkinter
ovals stair-step). Six images are rendered ONCE at construction and
held on `self._imgs` (so tkinter cannot garbage-collect them): the
two track pills via the icon SVG->PIL path (`_render_switch_track`
rasterizes `switch_night`/`switch_day` from `assets/icons/`), and the
sun/moon knobs in a rest + a 1.05x hover size (`_render_sun_knob` /
`_render_moon_knob` draw a supersampled RGBA radial-gradient disc via
`_radial_disc` — silver moon + 3 craters, gold sun over a blurred
glow — then LANCZOS-down). It is a FIXED size (it does not follow the
font zoom), so once is enough. Each `_redraw` just re-places the track
`create_image` (hard-swapped night/day at the knob's midpoint) and the
knob `create_image` at the animated x. A click toggles state, calls
`apply_theme` + `_schedule_save` synchronously, then runs a ~36-frame
smoothstep `after()` slide (cancel/restart if re-clicked); hover swaps
in the 1.05x knob. A missing track SVG is a loud `FileNotFoundError`
(Rule #1). Its canvas is registered as a `canvas` surface so its
background re-tints with the window — the pill's transparent corners
blend into the top strip in both themes.

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
