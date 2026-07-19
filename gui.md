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
`(day, night)` tuple, so a single
`ctk.set_appearance_mode()` flip repaints all CTk controls with zero
re-walk. The SOLID kinds (secondary / success / danger / info) draw
their fill AND label from the per-theme `config.BUTTON_FILL` /
`BUTTON_TEXT` pairs (owner 2026-07-19): the DAY shade differs from NIGHT
for every kind and the neutral `secondary` is a LIGHT sand fill with
DARK text on day (it used to borrow the dark warm-grey palette key and
render brown on the cream window); coloured kinds keep a white label in
both themes. every factory also pins `bg_color` to the active window
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
  the in-place-tools button row — all held in `self._controls_box`)
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
- **Collapsible per-agent fine-tune** (owner 2026-07-19) — a second
  `▸ Settings` toggle (top strip, left of `▾ Controls`) shows/hides
  ALL the per-agent FINE-TUNE blocks as one: each `AgentPanel`'s
  **Upscale gate (this site)** block — min W / min H / aspect FROM /
  aspect TO spinners that feed THAT site's pipeline Upscale toggle.
  HIDDEN by DEFAULT so the main UI stays clean; `_set_settings_collapsed`
  drives every panel's `set_finetune_visible` (pack ↔ pack_forget of the
  panel's `_finetune_box`, built at the panel's bottom), the glyph flips
  `▾/▸ Settings`, and the state persists (`settings_collapsed`, default
  collapsed). Independent of the Controls collapse (which hides the whole
  upper area including these blocks).
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
  its own **pause** and **action delay** Spinner ranges, its own
  **Start / Stop** pair, and (owner 2026-07-19) its own **Upscale
  gate (this site)** FINE-TUNE block — four Spinner fields (min W,
  min H, aspect FROM, aspect TO) that `panel.upscale_params()` feeds
  into THAT site's pipeline `upscale_if_small` when its Upscale
  switch is on; the block is HIDDEN until the top-strip `▸ Settings`
  toggle expands it (`set_finetune_visible`), and Start validates the
  four values (positive, FROM ≤ TO) before spawning. Defaults 800 /
  800 / 0.90 / 1.10 reproduce the old locked gate. A site "participates" in a run by
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
- **BG removal / Crop / Upscale / Aspect ratio** — the four in-place
  tools (owner 2026-07-19; the three renamed buttons DROPPED "only"),
  each its OWN CONCURRENT JOB with its own worker thread and its own
  dashboard panel — up to all four plus both sites (6 panels) run at
  once. Each button carries the panel's COLOUR + emoji (BG removal
  cyan/teal 🫧, Crop amber ✂, Upscale violet 🔍, Aspect ratio magenta
  📐, all in `config.JOB_COLORS`/`JOB_EMOJI`). A click (`_start_tool`)
  refuses a second job of the SAME kind (a messagebox — one job per
  kind), opens the input pick + a confirm, then spawns
  `_run_tool_job` on a daemon thread; the engine function
  (`remove_background` / `crop_transparent` / `upscale_if_small` /
  `change_aspect`) runs over the picked images, in order.
  **BG removal / Crop** pick a FOLDER (`askdirectory`) and run over
  every image under it. **Upscale** (owner 2026-07-19) is folder-based
  too, but first pops `UpscaleParamsDialog` — a modal asking the FOUR
  gate params (min W, min H, aspect FROM, aspect TO), PRE-FILLED with the
  last-used values (`self._upscale_tool_params`, remembered/persisted,
  positive-number + FROM≤TO validation), then runs `upscale_if_small`
  with those params bound. **Aspect ratio** is different: a folder can
  hold images of DIFFERENT ratios, so it picks INDIVIDUAL image FILES
  (`askopenfilenames`, multi-select) after the `AspectRatioDialog` — a
  tiny modal with two positive-integer fields **W** and **H**, PRE-FILLED
  with the last-used ratio (`self._aspect_ratio`, remembered/persisted;
  first run 16 : 9) — and warns it DEFORMS the N selected images (a
  non-proportional stretch written in place). Both dialogs share
  `_ModalToolDialog` (the centre-on-parent placement). The selection is
  keyed by `config.selection_base_and_rels` (the common-ancestor folder
  + each file's relative path), so picks spanning sub-folders still group
  under their folder node and restore correctly. Each image's ORIGINAL is
  BACKED UP first (`painter/jobtemp.py`, see **Temp / before-after /
  restore**), so `done` = the file was changed (its backup kept,
  before→after measured and shown), REFUSED = the engine said
  "nothing"/"unclear" — nothing to do, its no-op backup dropped (for
  Upscale: failed the gate — aspect outside the chosen FROM–TO or both
  sides already ≥ the chosen min W/H; for Aspect: already at the target
  ratio, left byte-unchanged).
  The op is also TIMED (per-image seconds; skipped items add no time).
  "Changed" keys ONLY on the engine ACTUALLY REWRITING the file: a "done"
  is NEVER demoted on a small/rounded metric (owner 2026-07-19) — a 3px
  crop or a small BG clear rounds the metric to 0 % yet the FILE WAS
  MODIFIED, so its backup + before/after must survive. Keying "changed"
  on a resolution/metric change (instead of on the file being rewritten)
  was the old before/after bug for BG removal, which changes ALPHA, not
  dimensions. The engine already returns "nothing" for a true
  byte-unchanged no-op, so a "done" is always a real, restorable change.
  The panel shows the tool's own PARAMETER + timing (below).
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
  the font zoom base, the **theme** (`day` / `night`), the window
  geometry, the **collapsed/expanded** controls state AND the
  per-agent fine-tune (Settings) collapse state (selection ticks stay
  per-run; the old dashboard `sash` is gone with the PanedWindow — a
  stale key is ignored). The **collection queue is NOT persisted** — the app
  starts with an empty list every launch (owner 2026-07-18); and a
  saved output folder that no longer exists is ignored in favour of
  the default `out/`, so done-detection never reads an empty
  `_state`. Saves debounce on every meaningful change (var traces,
  zoom, theme flip, either collapse, the two remembered dialogs) and
  always fire on close; loading applies missing keys as current
  defaults (a missing `theme` = `night`, `settings_collapsed` = True)
  and drops queued files that no longer exist (reported in the log).
  The stored dict: `output`, `font_base`, `theme`, `geometry`,
  `controls_collapsed`, `settings_collapsed`, `upscale_tool`
  (the standalone Upscale dialog's last-used `min_width`/`min_height`/
  `aspect_min`/`aspect_max`), `aspect_ratio` (the last `[W, H]` from
  the Aspect dialog), and `agents.<site>` with `background`,
  `bg_removal`, `crop`, `upscale`, `report`, `safer_retry`,
  `new_chat`, `pause_min/max`, `act_min/max`, and the per-agent
  upscale-gate `up_minw`/`up_minh`/`up_aspmin`/`up_aspmax`.

## The Dashboard — per-JOB panels (owner 2026-07-19)
The dashboard shows one panel PER RUNNING JOB, up to SIX in parallel:
the two generation SITES (ChatGPT, Gemini) plus the four in-place TOOLS
(BG removal, Crop, Upscale, Aspect ratio). Panels are no longer fixed —
a panel APPEARS when its job STARTS (a site Start / a tool button) and
gets a **✕ Close** button when the job FINISHES; Close removes the
panel from the grid AND clears that job's temp backups. Only
running-or-ran jobs show.

**`JobPanel`** is the shared base: a coloured header (an SVG
`config.JOB_LOGO` for the two sites, a `config.JOB_EMOJI` for the four
tools, plus the job NAME in the job's `(day, night)` `JOB_COLORS`
pair), the muted state line (quota countdown / current item), and the
hidden CLOSE button `finish()` reveals / `reset_finished()` hides.
`DashPanel(JobPanel)` is one gen site's view; `ToolPanel(JobPanel)` is
one tool's. Both are BUILT ONCE (never destroyed) and fed ONLY by the
runner/worker's structured events on the main thread.

**`DashGrid`** replaces the old draggable `ttk.PanedWindow`. It holds
the six build-once panels and re-flows them by ACTIVE COUNT via
`config.GRID_COLS_BY_COUNT` (1→1 col, 2→2, 3→3, 4→2×2, 5→2×3, 6→2×3;
rows = ceil(N/cols)), row-major over `JOB_ORDER` (gen FIRST) so ChatGPT
+ Gemini always fill the TOP row — at N=5 the 6th cell stays empty.
Cells share a `uniform` group so they are equal and evenly fill the
area; `add(kind)` / `remove(kind)` re-grid live as jobs start / close;
a muted placeholder shows when no job has run yet. The `sash` setting
key is gone (a stale one in an old settings.json is ignored).

**`DashPanel`** (one gen site), header + state line then:
- **Task** — a whole-run progress bar and `done / total
  (done/collections)` across every queued collection (pre-counted at
  Start by `_plan`, which mirrors the runner's queue rule).
- **File / Image** — the current collection file, the current image,
  and a per-collection progress bar.
- **Stats table** — two columns, `This one` and `Whole run`. Rows:
  Done, Refused, a collapsible **Average** (its value is the total
  per-image time; click ▶ to break it into **AI generation**, **Our
  processing** (save+bgfix+pause), **Minimum** and **Maximum**), then
  Tempo (/h) and ETA.
- **Collections (running + done)** — a three-level `ttk.Treeview`
  (Name · Done · AI · Ours · Res · Time · Size, both scrollbars,
  `stretch=False` everywhere): **Collection** → **Folder** →
  **Image**. The running collection appears live and open; **Show**
  (or double-click a row) opens the same formatted viewer — a
  collection's whole file, a folder's sheet excerpt, or an image's
  prompt + the saved image.

**`ToolPanel`** (one in-place tool), header + state line then:
- a progress bar, an aggregate metric label — `avg N% <metric> ·
  X changed, Y skipped`, where the metric is the tool's own PARAMETER
  (`config.JOB_METRIC`): BG removal `removed` (% removed pixels), Crop
  `reduction` (% area), Upscale `increase` (% area), Aspect ratio
  `deformation` (% growth of the stretched axis) — and a TIME label
  `⏱ <total> total · <avg>/img`. Both the total and the average count
  ONLY images actually PROCESSED (changed); skipped images add no time
  (owner 2026-07-19). Times use `config.fmt_op_duration` (sub-second
  below 10 s — bg/crop/aspect run in fractions of a second — so a fast
  op is `0.2s`, not `fmt_duration`'s flattened `0s`).
- a **collection → folder → image** `ttk.Treeview` (Name · Before ·
  After · % · Time · Size): each image row shows its BEFORE / AFTER
  resolution, the tool's %, and its per-image op time; a refused (no-op)
  row shows `—` in % and BLANK Time.
- **Double-click an image row** opens a `BeforeAfterWindow` for that
  image with a **Restore** (reverts ONLY it); **double-click the
  collection / folder node** opens a viewer of ALL the job's changed
  images with **RESTORE ALL** (reverts the whole job). A restore marks
  the row(s) restored and puts the ORIGINAL back on disk (see below).
  Works for ALL four tools — BG removal included: it changes ALPHA, not
  dimensions, and the viewer keys off the BACKUP existing (never a
  resolution change), so a cleared-background image shows before/after
  just like a resized one.

### Temp / before-after / restore
Every tool job holds a `painter.jobtemp.JobTemp` (a per-slot subdir
under the gitignored `.painter_tmp/` project temp). The worker
`backup`s each ORIGINAL before the op; on `done` (the file was actually
rewritten) it `measure`s before→after (the metric shown) and keeps the
backup, on a no-op it `drop`s the backup. The `BeforeAfterWindow` (a
themed Toplevel like DocWindow — skinned, registered in
`THEME_TOPLEVELS`, holding its scaled PhotoImages via the shared
`_scaled_photo` helper) stacks each image's before + after. The AFTER of
a BG removal / crop is TRANSPARENT where the background was cleared;
drawn straight onto the panel colour it looks unchanged, so the viewer
composites any image WITH ALPHA over a neutral checkerboard
(`_scaled_photo(..., on_checker=True)` → `_checkerboard` /
`_has_alpha`, greys in `config.CHECKER_*`) — the removed area reads as
removed. Restore / RESTORE ALL delegate to the `JobTemp`. Temp is
CLEARED on the panel's CLOSE, on app exit (`_on_close`) and swept at
startup — gen jobs make NEW files, so they need no restore.

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

**`apply_theme(name, animate=False)`** is the ONE coherent flip, used
by BOTH startup and the toggle. Its core (`_apply_theme_now`): set the
module `ACTIVE_THEME` → `theme_use` → `setup_style()` →
`set_appearance_mode()` → `recolor_tk_registry()` → fire every open
Toplevel's `apply_theme()`. It NEVER tears down the window, so an
active run's worker threads, dashboard counters and quota countdowns
survive a flip. **Open Toplevels** (`SelectWindow`, `DocWindow`) each
register in `THEME_TOPLEVELS` on `__init__`, unregister on
`<Destroy>`, and expose their own `apply_theme()` — because their
per-widget foregrounds (Select tree leaf colours + the header progress
label, DocWindow's Text tags) do NOT follow ttk styles and must be
recomputed from `status()`/`colors` live (Select retains each leaf's
`advice` + `n_done` to recompute its colour).

**The cross-fade** (owner 2026-07-18): tkinter has no native colour
transitions, so a live flip repaints as an ugly cascade of half-themed
frames (black boxes, half-styled spinners). When `animate=True` AND the
window is on-screen (`winfo_ismapped` + `winfo_viewable`), the whole
cascade is hidden behind a SNAPSHOT CROSS-FADE: `_snapshot_overlay`
grabs the current OLD-theme window client area with `PIL.ImageGrab`
(from `winfo_rootx/rooty/width/height`) into an `ImageTk.PhotoImage`
(held on the overlay so tk cannot GC it), and mounts it in a
borderless, topmost, `overrideredirect` Toplevel placed exactly over
the window at `-alpha` 1.0. The snapshot also carries a BIG CENTRED ICON
of the theme being switched TO — the SUN going to day, the MOON going to
night (`_render_theme_cover_icon`, the SAME anti-aliased PIL sun/moon
renderers as the switch knob, sized to `SWITCH_COVER_ICON_FRAC` = 30 % of
the window's min dimension) — `alpha_composite`-d INTO the grab so the
icon fades with the cover. Order matters (owner 2026-07-19, the flash
fix): the overlay is FORCED fully mapped + painted first —
`deiconify` → `lift` → `update_idletasks` → `update()` (so DWM actually
paints the cover on screen) — and ONLY THEN does `_apply_theme_now`
repaint the REAL window in the new theme UNDERNEATH the cover; one forced
`update_idletasks` settles that cascade invisibly, and
`_fade_out_overlay` ramps the overlay's window `-alpha` 1.0 → 0.0 over
`SWITCH_FADE_MS` (≈500 ms) in `SWITCH_FADE_STEPS` (28) `root.after`
ticks (ease-out) before destroying it. Forcing the paint before the
repaint GUARANTEES only the snapshot + sun/moon is ever seen mid-flip,
never a half-themed cascade. It is a pure visual nicety: any failure
(ImageGrab unavailable, `-alpha` unsupported) is caught, any partial
overlay destroyed, and the plain instant `_apply_theme_now` runs instead
with a one-line log note (root Rule #1 — never a stuck overlay or an
un-themed app). Caveats: `ImageGrab` grabs SCREEN pixels, so a window
occluding ours is captured in the snapshot; the app is frozen (static
snapshot) for the ~500 ms fade, so live dashboard updates are briefly
hidden. Startup passes `animate=False` (no window yet) — instant flip,
no overlay.

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
`apply_theme(name, animate=True)` (the snapshot cross-fade above) +
`_schedule_save`, then runs a ~36-frame smoothstep `after()` knob slide
(cancel/restart if re-clicked) — the slide runs CONCURRENTLY on the
switch canvas underneath the fade overlay, revealed as the snapshot
fades; hover swaps in the 1.05x knob. A missing track SVG is a loud `FileNotFoundError`
(Rule #1). Its canvas is registered as a `canvas` surface so its
background re-tints with the window — the pill's transparent corners
blend into the top strip in both themes.

## Threading
One worker thread per site, started and stopped INDEPENDENTLY by
its panel's buttons (per-site stop events); each creates its own
Playwright instance and `SiteDriver` (sync Playwright is
per-thread) and walks the theme queue sequentially. The four TOOLS
add up to four MORE daemon workers (`_run_tool_job`), one per kind
(one job per kind — a second click is refused), so up to six jobs run
CONCURRENTLY; each tool worker only backs up + processes files under
its own picked folder and its own `JobTemp` subdir (disjoint writes).
Every worker touches the window ONLY through the single `self._q`
queue drained on the tk timer (`_drain_queue` via `root.after`) — so
every widget mutation runs on the main thread. Queue messages:
`('__event__', slot, ev)` routes to `self.panels.get(slot).handle(ev)`
(`.get` is the defensive guard for a late event after a panel closed),
`('__tool_done__', slot)` and `('__worker_done__', key)` reveal the
panel's CLOSE and clear the worker bookkeeping, a quota
`TerminalState` posts its `retry_after_s` the same way and the main
thread schedules the auto-restart via `root.after` (the panel keeps its
countdown, no CLOSE, until the restart or a Stop).

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md), [CDP Driver](painter/driver.md),
  [Run Loop](painter/runner.md), [Chrome Launcher](painter/chrome.md),
  [Postprocess](painter/postprocess.md), [Upscale](painter/upscale.md),
  [Change Aspect Ratio](painter/aspect.md), [Job Temp](painter/jobtemp.md),
  [Settings](painter/settings.md), [Config](painter/config.md)

### Used by
- The owner (`python main.py` with no arguments).
