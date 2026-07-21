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
`ScrollFrame` also DEBOUNCES the resize re-fit (owner 2026-07-19,
tightened 2026-07-20): customtkinter re-renders on every intermediate
`<Configure>`, so a window drag / maximize used to run the
fill-height + scrollregion scan per frame (visible jank). A canvas
`<Configure>` now only REMEMBERS the newest width and re-arms a
settle timer (`_arm_settle`); the `_resizing` flag gates `_on_body`'s
per-frame scheduling, and the WHOLE re-fit — the body-width
itemconfigure (`_apply_width`), fill-height and the scrollregion scan
— runs ONCE via `_settle` ~`RESIZE_SETTLE_MS` (150 ms) after the LAST
`<Configure>` ("wait for mouse release"). The width used to stay live
per frame, but every width write reflows the body and fires a
`<Configure>` into each CTk child — measured over a synthetic 30-step
drag: 30 width writes → 55 CTk `_draw` re-renders before vs 0 and 0
during the drag now (one width write + 2 scans + 5 redraws on
settle); the first configure of a settled window still applies
immediately so the viewport never opens with a dead strip. Trade-off
(owner accepted): mid-drag the content freezes at its pre-drag width
— a window-bg strip grows (or the content clips) at the right edge —
and snaps to fit 150 ms after release. The drag stream itself also
buffers the dashboard events (see **Threading**).
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
  the AI features row — all held in `self._controls_box`; the four
  standalone tools' OWN quick-access buttons used to live in this same
  toolbar too, DELETED GUI rework Phase 14 — the Main Menu/IconBar
  tiles fully supersede them, see **Standalone-tool settings panels**)
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
  and drive the same `_start_site`/`_stop_site`. The button carries the
  **gamepad icon** (`assets/icons/controls.png`, owner 2026-07-19) beside
  the glyph, which flips to `▸ Controls` when collapsed; the state
  persists (`controls_collapsed`). The toggle runs behind the shared
  **`smooth_transition` snapshot cover** (owner 2026-07-20): the swap
  moves the whole upper window, so `_toggle_collapsed` covers it with
  a window snapshot, relayouts hidden behind it and fades the cover
  out over `TRANSITION_FADE_MS` (~260 ms) instead of one hard jump
  (see **Theming — the snapshot cover**).
- **Per-agent Settings gear** (owner 2026-07-19) — each `AgentPanel`
  owns its OWN `⚙ Settings` gear button (`assets/icons/settings.png`, on
  the Start/Stop row) that shows/hides THAT agent's collapsible
  **fine-tune** area — its **pause** range, its **action-delay** range,
  AND its **Upscale gate (this site)** block (GUI rework Phase 6: ONE
  min-side Spinner + an embedded `FilterEditor`, replacing the old min
  W / min H / aspect FROM / aspect TO four-field layout) — independently
  of the other site. HIDDEN by DEFAULT so
  the panel stays compact; `_toggle_settings` flips the panel's own
  `settings_collapsed_var` and `_apply_finetune_visibility` packs ↔
  `pack_forget`s the panel's `_finetune_box` (built at the panel's bottom)
  and swaps the `▾/▸ Settings` caret — the reveal runs behind the same
  `smooth_transition` snapshot cover as the Controls toggle (owner
  2026-07-20), since it moves everything below the panel. The state is
  per agent, persisted in
  that agent's settings (`settings_collapsed`, default collapsed) and
  reflected on load. There is NO global Settings toggle (the 0.0.079
  top-strip one was removed). Collapsing the whole Controls area hides
  the panels — gear and all — as before.
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
- **The root `<Configure>` watcher** (`_on_root_configure`, owner
  2026-07-20) — bound `add="+"` on the root at the END of `__init__`
  (after the saved geometry applies, so startup never arms it), and
  since every child widget carries the toplevel bindtag, its FIRST
  line drops child configures (one identity check per frame — the
  whole added per-frame cost). Two jobs: a **zoomed↔normal state
  change** is the DISCRETE maximize/restore jump — it runs the
  `smooth_transition` cover (mutate = nothing; the WM already resized
  us, the relayout settles behind the cover) and can never fire
  mid-drag because the state stays `normal` through a whole drag; a
  **same-state size change** marks a continuous drag active and
  re-arms a `RESIZE_SETTLE_MS` settle — while active, `_drain_queue`
  BUFFERS `__event__` messages (dashboard tree/label updates) into
  `_pending_events` and `_resize_settled` flushes them in order on
  release, so a live run stops re-rendering tree rows per drag frame
  (measured: 30 mid-drag events handled during the drag before, 0
  after — all 30 on settle). This is the ONLY root-level `<Configure>`
  bind; the audit found no other per-frame `<Configure>` work in
  gui.py beyond `ScrollFrame` (debounced above) and the Select
  window's wrap re-flow (now also settle-debounced).

## Main Menu (GUI rework Phase 10)

The FIRST thing the owner sees is no longer "everything at once" — a
full-window grid of 8 big tiles (`MainMenu(ttk.Frame)`, one per
functionality: Website GEN, New collection (AI), API Image GEN
(disabled placeholder — Phase 19 wires it up), AI check, BG removal,
Crop, Upscale, Aspect ratio), reading `config.MENU_TILES` (pure data —
id/label/description/icon stem/`(day, night)` accent colour/`enabled`).
`MainMenu._make_tile` is the ONE tile factory (Rule #5, not 8
copy-pasted blocks): a rounded `ctk.CTkFrame` card (`MENU_TILE_RADIUS`
= 16, DESIGN.md's "cards, panels" bracket) holding a centred icon +
title (`ctk_font("title")`, the SAME role the site panel titles use) +
description, built from the SAME primitives every other rounded
surface in this file already uses (`icon()` / `theme_pair` /
`ctk_font`) — no new visual language. The card's `fg_color` is the
`theme_pair("dark")` elevated surface (both themes already use this
token for "raised" chrome — DocWindow's code box, hover surfaces);
its border is the tile's own accent, `MENU_TILE_BORDER_PX` (2) at
rest, `MENU_TILE_BORDER_HOVER_PX` (4) on `<Enter>` — the ONE thing
that changes on hover, deliberately: widening the border needs no
child widget to update in lockstep, unlike a fill-colour hover would
(every icon/title/description label is bound to the SAME `<Button-1>`/
`<Enter>`/`<Leave>` handlers as the card, so the whole tile is one
click target). A DISABLED tile (`enabled=False` — only `api_image_gen`
today) renders with a muted `theme_pair("light")` border/title instead
of its accent and binds NO hover/click at all — visibly inert, not
just unwired. Three tiles (website_gen/ai_sheet_gen/api_image_gen)
have no natural `JOB_COLORS` entry (Website GEN spans BOTH gen sites,
not one job) and carry their OWN new accent tuples in `MENU_TILES`
(indigo/yellow/orange) chosen to stay visually distinct from the seven
existing `JOB_COLORS` hues; the other five tiles (bg/crop/upscale/
aspect/image_checker→`aicheck`) reuse `JOB_COLORS`/`JOB_LABEL`/
`JOB_LOGO` directly — a genuine reuse, not a duplicate literal.

**The view switch** — `PainterGui._view` (`"menu"` | `"main"`,
initial `"menu"`, never persisted: every launch lands on the menu) is
a state completely ORTHOGONAL to `_collapsed` (the pre-existing
Controls toggle keeps working unmodified, independently, in either
view — the design's suggested `_collapsed`→`_view` rename was
deliberately NOT done: correctness + zero regression on the riskiest
phase of the rework outweighed the tidiness). Mechanically it is
`_set_collapsed`'s pack_forget/pack technique applied ONE LEVEL UP:
`__init__` builds `self._main_view` (a plain `ttk.Frame(outer)`) as
the new, sole parent for the ENTIRE pre-Phase-10 tree — the Collections
queue, Output row, both `AgentPanel`s, the tool/AI toolbar rows, the
Dashboard/Log notebook and the status label all construct into it
exactly as before, only their immediate parent changed from `outer` to
`self._main_view` (their own `_build_*` methods take `parent` as an
argument and are otherwise byte-identical) — and `self._menu_view`
(the `MainMenu`) as its SIBLING, also a child of `outer`. `_set_view`
pack_forgets one and packs the other (`fill="both", expand=True`) —
nothing is ever destroyed, every StringVar/Listbox/panel/worker thread
keeps its state regardless of which container is currently on screen,
so a job started from the "main" view keeps running (and its dashboard
panel keeps updating) even after the owner navigates back to the menu.
`_go_view(view)` is the UI-facing wrapper — a no-op when already on
that view, otherwise the swap runs behind the shared `smooth_transition`
snapshot cover exactly like `_toggle_collapsed` (see **Theming — the
snapshot cover**), so it fades instead of jumping.

**Tile routing** (`PainterGui._select_tile(tile_id)`) — picking a tile
WITHOUT its own persistent panel (`_tool_panels`) calls `_go_view
("main")`, then invokes the SAME existing, UNMODIFIED handler the
always-visible toolbar already called before Phase 10:

| Tile id | Handler |
|---|---|
| `website_gen` | none — the owner drives the now-visible queue + per-site Start buttons, same as always |
| `ai_sheet_gen` | `_new_collection_ai()` |
| `api_image_gen` | none (disabled tile — `_select_tile` is never reached; Phase 19 wires the adapter) |
| `image_checker` / `bg` / `crop` / `upscale` / `aspect` | `_open_tool_panel(tile_id)` — GUI rework Phase 13 (bg/crop), Phase 14 (upscale/aspect), Phase 15 (image_checker), see below |

ALL FIVE standalone-job tiles (GUI rework Phase 15 completes what
Phase 13/14 started) go straight to `_open_tool_panel` and SKIP the
`_go_view("main")` hop entirely — going through "main" first, like
every other tile, would reveal-then-immediately-hide the old controls
box behind a wasted extra fade, since `_open_tool_panel` itself
transitions straight to "running" (see **Standalone-tool settings
panels** under **The window**, and **Running view** below for how it
shares `_inline_kind`/`_apply_running_layout` with website_gen's own
toggle). `_open_tool_panel` is always called with the TILE id
(`"image_checker"`, not `"aicheck"`) — `_tool_panels` itself is keyed
the same way; see **Standalone-tool settings panels**' own note on
`PainterGui._tool_panel_key` for the one place that bridges back from
a JOB_ORDER kind. The old `UpscaleParamsDialog`/`AspectRatioDialog`
modals upscale/aspect used to open here are DELETED (Phase 14, along
with `_start_tool` itself, their only caller); the AI checker's own
`askdirectory`+confirm `askyesno`, inline in `_start_ai_check`, is
DELETED the same way (Phase 15 — Rule #6, no dead wrappers left
behind in either case); `_ModalToolDialog` (the shared centre-on-
parent placement math) survives only because `_AiDialog` (the key
wizard, the sheet generator) still uses it. A
minimal **"Menu"** button (plain text — no icon asset fits "menu/home"
yet, and DESIGN.md's emoji policy rules out a hamburger glyph standing
in for a real one) sits in the pinned top strip beside the Day/Night
switch and the Controls toggle — reachable from "menu"/"main";
**Running view** below is what happens while a job is actually going.

## Running view (GUI rework Phase 11)

While ANY job is going, the visible surface shrinks to exactly what
the owner needs to watch it: a compact **`IconBar(ttk.Frame)`** (one
small button per `config.MENU_TILES`, plus a "Menu" button) sits above
the SAME Dashboard/Log `Notebook` Phase 10 already built; the big
controls area (Collections queue, Output row, both `AgentPanel`s, the
tool/AI toolbar rows) is hidden entirely — not destroyed, just
unpacked, the exact `_set_collapsed` pack_forget/pack idiom Phase 10
already leaned on for the menu/main swap, applied one container
further down.

**`_view` gains a third value, `"running"`.** `_set_view` packs it at
the OUTER level exactly like `"main"` (the `_main_view`/`_menu_view`
branch is byte-identical to Phase 10) — everything new happens one
container down, inside `_main_view`, via a new `_apply_running_layout`:

```python
def _apply_running_layout(self) -> None:
    self._controls_box.pack_forget()
    self._compact_box.pack_forget()
    for panel in self._tool_panels.values():
        panel.pack_forget()
    self._icon_bar.pack(fill="x", before=self.notebook)
    if self._inline_kind == "website_gen":
        self._controls_box.pack(fill="x", before=self.notebook)
    elif self._inline_kind in self._tool_panels:
        self._tool_panels[self._inline_kind].pack(
            fill="x", before=self.notebook
        )
    self._icon_bar.set_active(self._active_tile_ids())
    self._scroll.refresh()
```

(GUI rework Phase 13 generalized the single `"website_gen"` special
case above to a small `_inline_kind -> panel` lookup over
`self._tool_panels` — BG/Crop's own `ToolSettingsPanel` today, Phase
14 growing the dict to Upscale/Aspect, Phase 15 growing it again to
the AI checker (keyed `"image_checker"`, its MENU_TILES id — see
**Standalone-tool settings panels**' note on `_tool_panel_key` for why
that differs from its `"aicheck"` JOB_ORDER slot). AT MOST ONE inline
surface shows at a time either way.)

Entering `"running"` also disables the Controls-collapse toggle
(collapsed/expanded is meaningless once neither `_controls_box` nor
`_compact_box` is what's showing) and hands the Menu affordance to
IconBar's own copy — the pinned top-strip button `pack_forget`s itself
so only ONE "Menu" is ever on screen; leaving `"running"` reverses
both and calls `_set_collapsed(self._collapsed)` to restore whichever
of controls/compact was showing before, unmodified.

**The transition rules live in one pure, Tk-free function**, unit-
tested directly (`tests/test_gui_running_view.py`):

```python
def _next_view(
    current: str, active_count: int, menu_requested: bool = False,
) -> str:
    if menu_requested:
        return "menu" if active_count == 0 else current
    if active_count > 0:
        return "running"
    return current
```

- **any** active job forces `"running"` — the auto-enter-on-first-start
  rule (0 → ≥1 while on `"menu"` or `"main"` lands on `"running"`);
- it then STAYS `"running"` through every Stop, all the way down to
  zero active jobs — closing the LAST job never auto-navigates by
  itself;
- `"menu"` is reachable again ONLY on an explicit Menu click, and ONLY
  once `active_count == 0` — a click while anything is still active is
  a refused no-op (a status-bar hint explains why).

`PainterGui._active_kinds()` (`self._running | set(self._tool_workers)`
— sites + tools + the AI checker, ONE set) is the single source of
truth every running-view method reads; `_active_tile_ids()` maps it
back through the NEW `config.TILE_JOB_KINDS` dict (which
`JOB_ORDER` kind(s) light up which `MENU_TILES` id — `website_gen` is
the one entry spanning two kinds, the two AI dialogs map to `()` since
neither has a dashboard job). **`_sync_running_state()`** is the ONE
call site that reconciles both after every change: called at the end
of `_start_site`/`_launch_tool_worker`/`_start_ai_check` (right after
their worker thread starts) and from the `__worker_done__`/`__tool_done__`
dispatch branches (right after a kind is dropped from `_running`/
`_tool_workers`) — it recomputes `_next_view` and, whenever the result
IS `"running"`, refreshes `IconBar.set_active`. It is deliberately the
ONLY place that can ENTER `"running"`; leaving it only ever happens
through `_request_menu`.

**IconBar** reuses `MENU_TILES` exactly like `MainMenu` does (one
factory, not two copies): a `rounded_button` per tile (icon + label),
the ONE permanently-disabled `api_image_gen` placeholder styled once
at construction and never touched again, plus a "Menu" button.
`set_active(active_ids)` recolours every enabled tile — FILLED with
its accent while active, a quiet outline otherwise — via a new
`_style_icon_bar_button(btn, color, active)`, which generalizes the
existing `style_action_button`'s filled/outline language (today keyed
to a NAMED semantic kind like `"success"`/`"danger"`) to an arbitrary
`(day, night)` accent pair, so it works for any `MENU_TILES`/
`JOB_COLORS` tuple without a new visual language.

**Clicking an IconBar tile — `_click_icon_bar_tile(tile_id)`:**

- if the tile's `TILE_JOB_KINDS` are CURRENTLY active, the click just
  selects the Dashboard tab — never a settings toggle for a running
  job, and that job's own panel stays exactly as hidden as before;
- `"website_gen"` is a persistent inline surface: the click toggles
  `self._inline_kind` and re-runs `_apply_running_layout`, showing/
  hiding the EXISTING `_controls_box` (the queue + BOTH `AgentPanel`s)
  right above the Dashboard/Log — nothing new was built, Phase 10's
  own controls area is simply repacked into a different slot;
- ALL FIVE standalone-job tiles (`"bg"`/`"crop"`, GUI rework Phase 13;
  `"upscale"`/`"aspect"`, Phase 14; `"image_checker"`, Phase 15) are
  ALSO a persistent inline surface — routed through the SAME generic
  fallthrough below (`_tile_handler("bg")` resolves to
  `partial(self._open_tool_panel, "bg")`, etc. — no per-slot branch in
  either caller, the OLD `_start_tool` modal/the AI checker's own
  inline `askdirectory`+confirm these used to open are both deleted),
  toggling their OWN `ToolSettingsPanel` (see **Standalone-tool
  settings panels** under **The window**) the exact same way;
- the ONE remaining not-running tile, `"ai_sheet_gen"`, still launches
  through the EXISTING dialog handler — `_tile_handler(tile_id)`, the
  SAME mapping `_select_tile` uses (extracted once, Rule #5, so the
  Main Menu and the running view never carry two copies of "what does
  this tile do"). It has no PERSISTENT settings panel of its own (a
  request → clarifying-questions → sheet flow has no "settings" to
  leave open — see `AiSheetDialog`), so "toggle the inline surface"
  for it means "open the SAME dialog the toolbar button already
  opens", which disturbs nothing else (always its own Toplevel) but is
  not literally a persistent panel the owner can leave open to inspect
  later. `"api_image_gen"` is disabled — its IconBar button never
  fires a click at all.

**Start/Pause/Stop view semantics** (spec item 4), wired into the
EXISTING handlers — none forked:

| Action | What changes |
|---|---|
| **Start** (`_start_site`) | Unconditionally clears `_inline_kind` (Start hides the launching tool's OWN settings panel — website_gen's is shared by both sites, so EITHER starting hides it) then calls `_sync_running_state()` — auto-enters `"running"` on the first job. |
| **Start** (`_start_tool_from_panel`, GUI rework Phase 13/14, ALL FOUR tools; `_start_ai_check`, Phase 15, the AI checker — a DIFFERENT method, same view-tail) | Clears `_inline_kind` AND explicitly re-calls `_apply_running_layout()` (unlike the row above: the panel can ONLY be visible while ALREADY `"running"`, so `_sync_running_state()`'s own view-transition check is always a no-op here). `_start_ai_check` used to have no panel to hide at all (Phase 11–14); Phase 15 gives it `ImageCheckerSettingsPanel`, so its tail now matches `_start_tool_from_panel`'s exactly, just written by hand (see **Standalone-tool settings panels** for why it cannot share `_launch_tool_worker`). |
| **Pause** (`_toggle_pause_job`) | Unchanged pause/resume bookkeeping, PLUS: pausing `chatgpt`/`gemini` while `_view == "running"` sets `_inline_kind = "website_gen"`; pausing ANY of the FIVE standalone jobs (bg/crop/upscale/aspect, the AI checker since Phase 15) sets `_inline_kind` to `PainterGui._tool_panel_key(kind)` — identical to `kind` for the four tools, `"image_checker"` for `"aicheck"` — either way `_apply_running_layout()` re-applies the layout ("Pause returns the settings panel for future tasks", spec item 4), and the revealed `ToolSettingsPanel`'s OWN Pause/Resume label is kept in sync too (`_tool_panels[panel_key].set_paused`). Resuming never hides it again — only a fresh Start, a Stop (see below), or the owner's own icon click does. A no-op only outside `"running"` (already fully visible there) — no kind is left without a panel to reveal any more. |
| **Stop** (`_stop_site`) | UNCHANGED — signals the stop event; the worker exits on its own next poll and posts `__worker_done__`, which calls `_sync_running_state()` (recolours the icon; the design's "STOP … returns to the main menu" reads as "the Menu click that follows now succeeds", not an auto-jump — see below). Site Stop's own review-before-Close lifecycle is untouched by Phase 14/15. |
| **Stop** (`_stop_tool`, GUI rework Phase 14 — ALL FIVE standalone jobs since Phase 15, closing Phase 13's own flagged gap) | Requests the halt (sets the job's stop event, wins over a pending Pause) — see **Standalone-tool settings panels**' own "Stop" write-up for the FULL "smart stop" sequence (worker finishes the in-flight image/vision call, then `__tool_done__`'s dispatch closes the panel + clears its JobTemp (a no-op for the AI checker — it has none) + calls `_request_menu()`). GUI rework Phase 15 wires the AI checker's OWN settings panel to this SAME method, UNCHANGED (`on_stop=PainterGui._stop_tool`, keyed `"aicheck"`) rather than a new near-duplicate — it never touched `_tool_panels` to begin with, so nothing about it was tool-specific. A DELIBERATE divergence from site Stop's review-then-Close lifecycle — a quick, disk-based (or read-only) job has nothing left worth reviewing once stopped. |
| **Close** (`_close_panel`) | UNCHANGED — the existing `_dashgrid.remove`/`reset_finished`/`JobTemp.clear`. For a NATURAL tool/checker finish (not a Stop) and every site finish, `finish()` reveals CLOSE first and the owner clicks it manually, same as always; a Stop-triggered finish calls `_close_panel` itself (see the Stop row above) — `__tool_done__`'s dispatch ALSO re-enables the finished slot's `ToolSettingsPanel` Start button (`set_run_state(running=False)`, resolved via `_tool_panel_key` since Phase 15) either way. |
| **Menu** (`_request_menu`, shared by the pinned button and IconBar's own) | Routes through `_next_view(…, menu_requested=True)` — navigates to `"menu"` once `active_count == 0`, otherwise refused with a status-bar hint ("Stop every running job before returning to the menu."). GUI rework Phase 14's `_stop_tool`→`__tool_done__` sequence calls this SAME gate itself once its slot is popped from `_tool_workers`, so a Stop that happens to be the LAST active job (a tool OR, since Phase 15, the AI checker) lands on "menu" automatically; refused (silently, from this internal caller) if another job is still active. |

**Reading "Stop … returns to the main menu" (spec item 4) precisely:**
the binding design doc is explicit that "menu" is reachable "only when
NO jobs are active AND the owner clicks Menu" — `_next_view`'s own
rules are UNCHANGED by Phase 14 (Stop of the last job still never
auto-navigates BY ITSELF). What Phase 14 adds is a single new internal
caller of the EXISTING `_request_menu()` gate: once a STOPPED tool's
worker actually confirms the halt, `_dispatch` calls `_request_menu()`
on the tool's behalf — equivalent to "the owner clicking Menu right
after Stop", succeeding only when nothing else is active. Site Stop is
untouched: it still keeps the existing, tested Stop→finish→Close
lifecycle (the owner reviews a finished panel before a manual Close).

**Non-regression:** the Main Menu (Phase 10) is unchanged and still
the app's front door; every job kind still starts/pauses/stops exactly
as before AS FAR AS THE OWNER CAN SEE (`_start_site`/`_stop_site`/
`_close_panel`'s own bodies were never rewritten, only extended at
their tail; `_start_tool` itself is gone, GUI rework Phase 14, along
with its two callers). `_start_ai_check` is the ONE exception to
"never rewritten" — GUI rework Phase 15 replaces its BODY (the
`askdirectory`+confirm it used to own) while preserving its own
EXTERNALLY-VISIBLE contract (one job at a time, key-gated, same
worker/event stream) — see **Standalone-tool settings panels**' own
Phase 15 write-up, not a claim made lightly given root Rule #1. The
Dashboard/Log, per-job panels, before/after + `StepRestoreWindow`,
Select window, Day/Night theming, font zoom, scroll and settings
persistence are all untouched — Phase 11 only changes what is PACKED
where, via the same `pack_forget`/`pack` technique already proven safe
in Phase 10.

**Verified (0.0.09x):** full suite green (386 tests, up from 345) plus
`tests/test_gui_running_view.py` — `_next_view`'s rules table above,
`_active_kinds`/`_active_tile_ids`/`_sync_running_state`/
`_apply_running_layout`/`_request_menu`/`_click_icon_bar_tile`/
`_toggle_pause_job`'s new reveal, all run through a duck-typed
`FakeGui` (never a full `PainterGui` — its `__init__` is too heavy for
a unit test, same convention every other GUI-phase test file already
follows), plus real-widget `IconBar` construction/click/`set_active`
checks; `config.TILE_JOB_KINDS` coverage lives in `test_config.py`
beside `MENU_TILES`'s own pure-data tests. Real-window screenshots (Day
theme, settings.json redirected to a scratch file so the owner's real
one is never touched, the site job driven through fake
`SiteDriver`/`run_sheet` so no Chrome/network is needed) confirmed: (1)
Website GEN → Start → IconBar + Dashboard only, controls hidden,
`website_gen` tile filled; (2) clicking the BG-removal icon while
`chatgpt` "runs" starts a REAL local bg job alongside it (0.0.09x-era
behaviour — GUI rework Phase 13 replaced the direct-start click with
opening BG's own settings panel first, see below) — BOTH tiles filled,
BOTH dashboard panels visible, controls still hidden, `chatgpt`'s own
panel undisturbed; (3) Stop + Close everything, then Menu → the
full-screen 8-tile menu again, Controls/Menu restored to their
pre-running spots.

## The window

- **Collections** — a QUEUE of one or more prompt `.md` files (each
  file is one COLLECTION — a set of images to make: a theme, an icon
  set, a landscape series …; **Add…** / **Remove** / **Clear** plus
  **Add folder…** (owner 2026-07-21) — picks a folder and recursively
  queues every `.md` underneath via `config.iter_md_files` (mirrors
  `iter_images`), however deep it is nested. All four buttons share
  ONE append/de-dup/insert body, `_queue_sheets(paths)` (de-dup is by
  full PATH, so two same-named sheets in different sub-folders both
  queue — see the filename-collision refusal below); `_add_sheets`
  (the file picker) and `add_generated_sheet` (the AI sheet
  generator's queue-one-sheet call) both reduce to a call into it —
  Rule #5). Each site works
  through the queue in order, closing collection after collection;
  broken files are reported and dropped, never half-driven. Two
  queued files that share a filename are refused (their progress and
  report would collide).
- **Output** — the folder; images save DIRECTLY to
  `<out>/<site>/<drop-path>` (no approval step).
- **Show/hide per site** (GUI rework Phase 12, spec item 3A — "moze da
  se prikaze/sakrije bilo koji tj da ostane samo jedan vidljiv") — a
  "Show:" row of two compact switches sits ABOVE both panels (never
  INSIDE either one — a control that could hide itself would strand
  the owner with no way back), each bound to that `AgentPanel`'s own
  `visible_var` (`build_visibility_toggle`, default True, persisted
  per agent). `PainterGui._relayout_agents` — driven by a trace on
  `visible_var`, wired once both the panel grid and the collapsed
  strip's `build_compact` clusters exist — `grid()`/`grid_remove()`s
  each panel AND its collapsed-strip cluster together, and the pure
  `_visible_agent_columns(order, visible)` helper compacts whichever
  panel(s) remain toward column 0 (reset-then-reassign column weight,
  the same technique `DashGrid.relayout` already uses) so hiding one
  site never leaves the other stuck in a half-width column with a dead
  gap beside it. Hiding a site whose job is RUNNING or has a pending
  quota auto-restart is disallowed — `set_run_state` greys the toggle
  out for that same window (Stop/Pause live only on this panel, so
  hiding it then would strand the job) and, since a HIDDEN site can
  still go live without a click (a quota auto-restart, an AI-check
  resend both call `_start_site` directly), forces `visible_var` back
  to True and logs why whenever that happens, so the toggle and what
  is on screen never silently disagree. DashGrid's own JOB_ORDER-driven
  dashboard-panel handling is untouched by any of this — a hidden
  site's Dashboard panel still appears exactly as before when its job
  runs; only the CONTROLS surface hides.
- **The two AGENT PANELS** (2026-07-18, full per-agent
  separation) — ChatGPT and Gemini each get their OWN
  `AgentPanel` labelframe (site logo in the header) holding
  everything below the shared Output line: the **background
  dropdown** (`transparent` / `white` / `none`, preselected to the
  site's default — ChatGPT transparent, Gemini white; Gemini's
  three laws still ride along automatically), the **Style dropdown**
  (owner 2026-07-19 — one of the 7 `config.STYLES`, default `None`;
  a PRIMARY per-generation choice so it sits in the always-visible
  area near Background / New chat, NOT under the gear; its clause is
  appended at the very END of that site's `prompt_suffix`, after the
  background rule + Gemini laws, and it is passed into the worker via
  `partial(prompt_suffix, key, background, style=...)`), the three
  always-visible composable **post-save switches** — `BG removal`,
  `Crop`, `Upscale` (all ON by default) — plus a FOURTH, **Force
  Aspect Ratio** (GUI rework Phase 8, default OFF, under the Settings
  gear — see below): each site's post-save pipeline runs exactly ITS
  ticked steps, ALWAYS in the fixed order **BG → Crop → Aspect(force)
  → Upscale** regardless of which are ticked (never reordered by
  switch state), loud on failure but never killing the run — see
  **Pipeline reorder + per-step backups** below. **Report txt**,
  **Safer retry**, **Continue nudge**
  (owner 2026-07-20 — ON by default; on a stuck `NoImage` response
  the runner sends `CONTINUE_NUDGE` once into the same chat to un-stick
  ChatGPT before giving up, passed to `run_sheet(continue_nudge=…)`),
  the **New chat** mode,
  its own **Start / Pause / Stop** trio (owner 2026-07-21 adds
  **Pause** between them — a plain neutral `btn_pause` whose LABEL
  alone flips Pause ↔ Resume, wired to the shared `_toggle_pause_job`;
  see **Pause** below), and its own **⚙ Settings gear**
  (owner 2026-07-19). The gear reveals THIS agent's collapsible
  **fine-tune** area (`_finetune_box`, hidden by default): the **pause**
  Spinner range, the **action delay** Spinner range, the **Force
  Aspect Ratio (this site)** block (GUI rework Phase 8 — see below),
  the **Keep every pipeline step (uses more disk)** switch (see
  **Pipeline reorder + per-step backups**) and the **Upscale
  gate (this site)** block. GUI rework Phase 6 simplified the gate from
  four scalar fields to ONE **min-side** Spinner (the smaller side's
  target minimum, px) plus an embedded stacked **`FilterEditor`**
  (deciding WHICH images qualify, pre-seeded with a single Aspect
  (range) condition at the old default 0.9–1.1 band) — `panel.
  upscale_params()` resolves the two via the pure module-level
  `_upscale_params_from_side_and_filter(min_side, conditions)` into
  `upscale_if_small`'s UNCHANGED `min_width`/`min_height`/`aspect_min`/
  `aspect_max` kwargs (`min_width = min_height = min_side`; the aspect
  band comes from the filter's first IF-polarity Aspect condition, or
  widens to `(0, inf)` — "every ratio qualifies" — when the owner
  removed it or set it to IF NOT, a shape the plain kwargs cannot
  express). Any OTHER stacked condition in the same filter (a Width /
  Height / Any-side row, a second aspect row) is NOT silently dropped
  (root Rule #1): `panel.upscale_conditions()` exposes the FULL stack,
  and the site's post-save pipeline (`_compose_post_save`) runs every
  image through the pure `_gate_and_upscale(path, log, conditions,
  params)` helper, which checks `painter.filters.matches()` against
  the WHOLE stack BEFORE calling `upscale_if_small` — a match failure
  short-circuits to `"nothing"` without ever reaching the engine. Both
  fields moved UNDER the gear (they were formerly always-visible /
  global); `_toggle_settings` + `_apply_finetune_visibility` show/hide
  them per agent, and Start still validates (min side positive; a
  filter row's own FROM ≤ TO is already enforced by `FilterEditor`
  itself, so no separate aspect-ordering check is needed here) before
  spawning. The shipped default (min side 800, Aspect (range) 0.90–1.10
  IF) reproduces the OLD locked/four-field gate byte-identically. GUI
  rework Phase 12 additionally gates the WHOLE gate sub-block
  (`_upscale_gate_box`: the "Upscale gate (this site):" heading, the
  min-side Spinner row and the embedded `FilterEditor`) on the
  **Upscale** switch itself, live, via a `trace_add("write", …)` on
  `upscale_var` calling `_apply_upscale_gate_visibility` — turning
  Upscale off hides the whole sub-block EVEN WHILE the Settings gear
  stays expanded (it used to sit there always, gear-expanded or not);
  turning it back on reshows it with whatever it was last configured
  to. Composes as a plain AND with the gear's own collapse (a pack/
  pack_forget on a CHILD of `_finetune_box` is independent of the
  parent's own pack state), and the trace fires identically for an
  interactive click and a settings-restore `.set()` — no separate
  "apply on load" call needed, unlike `settings_collapsed_var`, which
  has no trace of its own.
  **Force Aspect Ratio (this site)** (GUI rework Phase 8, default OFF)
  — a `Force to ratio` switch plus a target **W : H** pair, edited
  two-way with an embedded **`AspectRatioCanvas`** (the SAME Phase 5
  widget the standalone Aspect tool's own panel uses — see
  **Theming**'s `THEME_TOPLEVELS`/`job_color` note for why a non-modal
  host matters). `panel.force_aspect_ratio()` returns the validated
  `(w, h)` int pair (`ValueError` propagates to Start's validation,
  same contract as `upscale_params()`); when the switch is on, the
  post-save pipeline runs `painter.aspect.change_aspect(path, w, h,
  log)` on the just-saved image — a deliberate DEFORM, never a
  proportional fit (see [Change Aspect Ratio](painter/aspect.md)) — as
  the pipeline's THIRD step, between Crop and Upscale. A site
  "participates" in a run by
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
  flips only the non-done leaves, and every count
  re-derives live. Already-done items — their SAVED FILE exists
  under the current output folder (owner 2026-07-19: file existence,
  no longer a sidecar record) — show green/olive + unticked but
  ENABLED, so re-ticking one REGENERATES (overwrites) a bad image;
  sheet-ADVISED items (REUSE / not-approved sections) show
  unticked with the ⚠ reason truncated — tick them to generate
  them anyway. Without any explicit ticks a run skips advised
  items by default (eager var materialisation is run-safe: the
  default advice-free, not-on-disk set equals the runner's own
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
  once. Each carries the panel's COLOUR + its PNG icon (owner
  2026-07-19, replacing the old emoji: BG removal cyan/teal, Crop amber,
  Upscale violet, Aspect ratio magenta — colours in `config.JOB_COLORS`,
  icons `bg`/`crop`/`upscale`/`aspect` via `config.JOB_LOGO` + `icon()`).
  Everything from here through the end of this bullet — the JobTemp
  backup, the timing, the "changed" contract, the dashboard panel
  itself — is SHARED by all four tools UNCHANGED (`_run_tool_job`'s
  worker loop + event contract — plus its own should_stop, GUI rework
  Phase 14, see below — and `ToolPanel`'s rendering, engine-untouched
  throughout); **all four are now configured and started the SAME
  way, through their own persistent panel** — see **Standalone-tool
  settings panels** right below, which is where the OLD per-tool
  askdirectory+confirm-modal writeup used to live (GUI rework Phase 13
  for BG/Crop, Phase 14 for Upscale/Aspect — the `UpscaleParamsDialog`/
  `AspectRatioDialog` modals both retired, deleted along with their
  only caller `_start_tool`). Once Started, `upscale_if_small` /
  `change_aspect` run over the picked (and filter-narrowed) images, in
  order, EXACTLY as before this migration — the engine functions
  themselves are BYTE-UNCHANGED, only how their kwargs get assembled
  moved from a modal's `.result` dict to a panel's own fields. Each
  image's ORIGINAL is BACKED UP first (`painter/jobtemp.py`, see
  **Temp / before-after / restore**), so `done` = the file was changed
  (its backup kept, before→after measured and shown), REFUSED = the
  engine said "nothing"/"unclear" — nothing to do, its no-op backup
  dropped (for Upscale: failed the FULL filter stack, or the resolved
  aspect band, or both sides already ≥ the chosen min side; for
  Aspect: already at the target ratio OR filtered out by the input
  filter, left byte-unchanged). The op is also TIMED (per-image
  seconds; skipped items add no time). "Changed" keys ONLY on the
  engine ACTUALLY REWRITING the file (a "done"), never on the metric
  size (owner 2026-07-19) — a 3px crop or a small BG clear is a
  genuine, restorable change even though its % is tiny, so its backup
  + before/after must survive. The % itself is rendered by
  `config.fmt_pct` (2 decimals below 10, 1 decimal from 10), so that
  3px crop reads `0.24%`, never a rounded-away `0%`. Keying "changed"
  on a resolution/metric change (instead of on the file being
  rewritten) was the old before/after bug for BG removal, which
  changes ALPHA, not dimensions. The engine returns "nothing" for a
  true byte-unchanged no-op (crop: a 0px-change box), so a "done" is
  always a real change. The panel shows the tool's own PARAMETER +
  timing (below).
- **Standalone-tool settings panels** — `ToolSettingsPanel(ttk.Frame)`
  + `BgSettingsPanel`/`CropSettingsPanel` (GUI rework Phase 13) +
  `UpscaleSettingsPanel`/`AspectSettingsPanel` (Phase 14) +
  `ImageCheckerSettingsPanel` (Phase 15 — the AI checker; see its own
  paragraph below for how it differs), all the SAME base, the last
  three replacing a retired modal/inline-dialog flow
  (`UpscaleParamsDialog`/`AspectRatioDialog`; the AI checker's own
  `askdirectory`+confirm `askyesno`, formerly inline in
  `_start_ai_check`) with ONE PERSISTENT panel family shown inline
  above Dashboard/Log — the exact surface website_gen's own
  `_controls_box` occupies (see **Running view**'s
  `_apply_running_layout`/`_inline_kind`), reached via `PainterGui.
  _open_tool_panel(tile_id)` from either the Main Menu (`_select_tile`)
  or the running view's IconBar (`_click_icon_bar_tile`'s generic
  `_tile_handler` fallthrough) — ONE shared toggle, not five copies
  (Rule #5). `_tool_panels` is keyed by MENU_TILES id throughout (tile
  id == slot for the four tools, so this is invisible for them);
  `ImageCheckerSettingsPanel`'s own `SLOT`/JOB_ORDER kind is
  `"aicheck"`, predating the tile system (owner 2026-07-20 vs. GUI
  rework Phase 10/11) and never renamed to match its `"image_checker"`
  tile — `PainterGui._tool_panel_key(kind)` (backed by
  `config.tile_for_kind`) is the ONE place that bridges a JOB_ORDER
  kind back to its `_tool_panels` key, used by `_toggle_pause_job` and
  the `__tool_done__` dispatch branch (both below); `_open_tool_panel`/
  `_select_tile`/`_click_icon_bar_tile` never needed it — they already
  operate purely in tile-id space. Each panel owns:
  * an **input picker** — **Folder…** (`askdirectory` → the shared
    `iter_images`, re-scanned LIVE at Start so a folder edited after
    the pick is honored) or **Files…** (`askopenfilenames`, based via
    `config.selection_base_and_rels`, exactly like the old Aspect
    dialog always offered) — every panel gets BOTH, unconditionally
    (the base builds this once; Upscale's old modal only ever offered
    Folder…, so this is a genuine small upgrade, not a behaviour the
    owner has to opt into);
  * an OPTIONAL always-visible **`_build_extra` block** (GUI rework
    Phase 14 hook, base no-op — BG/Crop don't use it) for a tool's own
    PRIMARY control, shown between the input picker and the Filter
    section: `UpscaleSettingsPanel` — the min-side Spinner (px, the
    smaller side's target minimum); `AspectSettingsPanel` — the
    target-ratio **W**/**H** entries beside a visual
    **`AspectRatioCanvas`** (GUI rework Phase 5 — see below), two-way
    synced exactly like the old `AspectRatioDialog`/`AgentPanel`'s own
    Force Aspect Ratio block;
  * an embedded **`FilterEditor`** (see below) narrowing WHICH images
    the run touches — pre-seeded via an overridable `_default_
    conditions()` hook (base empty, matching BG/Crop's own "no filter
    by default"): `UpscaleSettingsPanel` seeds ONE Aspect (range)
    [`UPSCALE_ASPECT_MIN`, `UPSCALE_ASPECT_MAX`] condition, the SAME
    default `AgentPanel`'s own upscale gate and the old
    `UpscaleParamsDialog` used; `AspectSettingsPanel` starts empty,
    matching the old `AspectRatioDialog`'s own "no conditions = every
    image" default;
  * an **Advanced** collapsible (the SAME Settings-gear idiom
    `AgentPanel._toggle_settings` established) — ONLY when the
    subclass sets `HAS_ADVANCED = True` (the base default; `Upscale
    SettingsPanel`/`AspectSettingsPanel` set it False and skip
    building the collapsible ENTIRELY, Rule #16: a gear that reveals
    nothing would be a dead affordance — their one primary control
    already lives in the ALWAYS-VISIBLE `_build_extra` block above,
    not tucked behind a gear). Exposes engine knobs as PER-RUN
    overrides for the two panels that DO have one: `BgSettingsPanel`
    — the two SAFETY GUARD fractions `remove_background` aborts past
    (`safety_max_remove_frac` black / `safety_max_remove_frac_white`
    white); `CropSettingsPanel` — every knob `crop_transparent` reads
    (the border-halo cleanup toggle, the safety margin, the
    ink-detection alpha + minimum ink pixels). **Deviation from the
    design's own Phase 13 notes:** those notes assign the halo-cleanup
    toggle to BG's Advanced section, but the real code only ever wires
    `CLEAN_EDGE_ENABLE` into `crop_transparent` (its own docstring:
    "only serves to ENABLE a tighter crop") — `remove_background`
    never calls `clean_edge_halo` at all, so putting the toggle on
    BG's panel would silently do nothing (root Rule #1). It lives on
    Crop's panel instead, where it is real.
    [Postprocess](painter/postprocess.md)'s `remove_background`/
    `crop_transparent` gained matching OPTIONAL keyword-only
    parameters, one per constant, defaulting to the config value — an
    ADDITIVE signature change (every existing caller passes neither
    and keeps today's exact behaviour), not a wrapper (root Rule #6).
    `_advanced_settings()`/`_apply_advanced_settings()` (the settings-
    round-trip hooks) run REGARDLESS of `HAS_ADVANCED` — for Upscale/
    Aspect they carry the ALWAYS-VISIBLE `_build_extra` fields instead
    (min-side, target ratio) into the SAME JSON shape, so "subclass's
    own extra data" is one hook pair either way, just displayed
    differently;
  * an OPTIONAL always-visible **`_build_footer` block** (GUI rework
    Phase 14 hook, base no-op) shown just above the button row:
    `AspectSettingsPanel` carries the non-proportional-STRETCH warning
    the old `AspectRatioDialog`'s confirm `askyesno` used to show
    ("DEFORM N image(s) … a non-proportional STRETCH written IN
    PLACE … originals are backed up so you can Restore … already at
    the ratio are skipped untouched") — since a panel's Start has no
    confirm step of its own (the panel, deliberately configured then
    Started, already IS the confirmation, same contract as every other
    panel), the warning is a permanent label instead of a one-off
    dialog, so the owner is never surprised even on a THIRD/FOURTH run;
  * **Start**/**Pause**/**Stop** buttons. Start (`PainterGui.
    _start_tool_from_panel`) reads the panel's OWN
    `resolve_input()`/`get_conditions()`/`build_func()` (each raising
    `ValueError` — shown as a messagebox — instead of the old modal's
    inline validation), pre-filters via the SAME module-level
    `_filter_files` every panel now shares, then hands off to
    `_launch_tool_worker` — the ONE shared tail EVERY tool's Start
    uses (Rule #5; the OLD modal-driven path this used to also serve
    is gone). **`_run_tool_job`'s worker spawn + event contract are
    UNCHANGED** — `ToolPanel.handle` needed no edits at all. Pause
    reuses `_toggle_pause_job` — see **Running view**'s Start/Pause/
    Stop table above for how it reveals the panel again mid-run,
    keeping ITS OWN Pause/Resume label in sync with the dashboard
    `ToolPanel`'s. **Stop** (GUI rework Phase 14, closing Phase 13's
    own flagged gap — "no literal Stop button… flagged as a candidate
    for a future phase" is now built): `PainterGui._stop_tool` sets
    the tool's should_stop event (mirrors `_stop_site`'s own request
    half, wins over a pending Pause the same way); `_run_tool_job`
    checks it BETWEEN images (mirrors `run_sheet`'s own `should_stop`
    check exactly, including threading it into `wait_while_paused` so
    a Stop wins over a paused wait too) — the IN-FLIGHT image always
    finishes first. Once the worker actually confirms the halt
    (`__tool_done__`, never synchronously on the click — see **Running
    view**'s Stop row above), `_dispatch` closes the panel + clears
    its JobTemp (the existing `_close_panel`, same as a manual Close)
    and calls `_request_menu()` — landing on "menu" if that was the
    LAST active job, a no-op status hint otherwise. This is a
    DELIBERATE divergence from site Stop's review-then-Close lifecycle
    (**MUST NOT REGRESS, verified**: site Stop is completely
    untouched) — a quick, disk-based tool run has nothing left worth
    reviewing once stopped, so "smart" here means "decisively finish
    the job", not "linger". Reachability mirrors Pause's own existing
    quirk (not a NEW one): the settings panel (Start/Pause/Stop) hides
    the moment Start runs, same as before Phase 14; the dashboard
    `ToolPanel`'s OWN always-visible Pause button is what reveals it
    again mid-run (`_toggle_pause_job`'s tail) — the owner clicks
    Pause first, then Stop becomes reachable on the now-revealed
    panel. A more direct dashboard-level Stop is a candidate for a
    future polish pass, not built this round;
  * **`ImageCheckerSettingsPanel`'s own differences** (GUI rework Phase
    15) — `HAS_ADVANCED = False` (no engine knobs; a `_build_footer`
    note instead, carrying what the retired confirm dialog used to say:
    model + pacing + where flags persist — the SAME "footer replaces a
    one-off confirm" pattern `AspectSettingsPanel` already established);
    `_picker_title_suffix()` overridden to `"(read-only)"` (a NEW
    `ToolSettingsPanel` hook, base `"runs IN PLACE"` — a read-only
    vision pass must never claim to write anything, root Rule #1) so
    its **Folder…**/**Files…** dialog titles read "AI check
    (read-only)", not the other four tools' shared wording; no
    `_build_extra`/`build_func` override (its Start does not read
    `build_func()` at all — see below). **Start** is `PainterGui.
    _start_ai_check`, NOT `_start_tool_from_panel` — the checker's
    worker (`_run_ai_check_job`) has no JobTemp/per-file-engine-
    callable shape to share with `_run_tool_job` (the run is READ-ONLY:
    nothing is backed up, nothing is written but the flag file), so its
    body reads the panel's `resolve_input()`/`get_conditions()` (NOT
    `build_func()`), pre-filters via the SAME `_filter_files`, and
    spawns `_run_ai_check_job` by hand, mirroring `_launch_tool_
    worker`'s tail (stale-Stop/stale-pause sweep, dashboard reveal,
    `_sync_running_state()`) — see **`AiCheckPanel`** under **The
    Dashboard** for the worker itself, UNCHANGED except for the new
    `stop_event` below. **Stop** reuses `PainterGui._stop_tool`
    VERBATIM — no `_stop_ai_check` method exists: `_stop_tool` never
    referenced `_tool_panels` to begin with (it only touches
    `_tool_workers`/`_stop_events`/`_paused`/`self.status_var`, all
    already keyed `"aicheck"`), so it was ALREADY fully generic over
    any slot with those three entries — a second, near-identical method
    would only duplicate it byte-for-byte (root Rule #5); the
    constructor wires `on_stop=self._stop_tool` exactly like the four
    tools. `_run_ai_check_job` gained the matching `stop_event`
    parameter, checked BETWEEN images (mirrors `_run_tool_job`'s own
    pattern exactly — see **Pause** below for `wait_while_paused`'s own
    updated row) — the in-flight vision call always finishes first.
  * a settings round-trip — `get_settings()`/`apply_settings(stored,
    conditions=…)` mirror `AgentPanel`'s own contract (missing key =
    keep default; `"advanced_collapsed"` is only ever emitted when
    `HAS_ADVANCED`); `PainterGui._collect_settings`/`_apply_settings`
    persist each panel under the `"tool_panels"` key, keyed by
    `_tool_panels`' own dict key — the MENU_TILES id
    (`{tile_id: panel.get_settings()}`; `"image_checker"` for the AI
    checker, GUI rework Phase 15, its ONLY field `conditions` — no
    Advanced/extra overrides of its own, no migration needed either,
    unlike Upscale/Aspect below) — the picked folder/files are NEVER
    persisted (every tool has always asked fresh; only the filter
    stack + Advanced/extra overrides survive a restart). GUI rework
    Phase 14 also retires the OLD top-level `"upscale_tool"`/
    `"aspect_ratio"`/`"aspect_filter_conditions"` settings.json keys
    the standalone dialogs used to own — `_collect_settings` no longer
    emits them; `_apply_settings`'s `_migrate_upscale_panel_settings`/
    `_migrate_aspect_panel_settings` do a ONE-TIME LOUD migration
    (same additive/read-old-once/log-loudly contract as every other
    migration in this file, including chaining into the EXISTING
    `_migrate_legacy_upscale_gate`/`_migrate_legacy_aspect_filter`
    pure functions for an even-older pre-Phase-6/pre-Phase-4 shape)
    into `UpscaleSettingsPanel`/`AspectSettingsPanel`'s own
    `up_minside`/`ratio` fields — a no-op once each panel has saved
    itself at least once under the NEW key.

  **Verified (0.0.1xx):** `tests/test_gui_tool_panels.py` (pure
  `_filter_files` + the Advanced-field parsers; `resolve_input`/
  `get_conditions`/`build_func` against a real withdrawn-root panel
  for all FOUR panels; monkeypatched engine calls
  (`postprocess.remove_background`/`crop_transparent`,
  `upscale.upscale_if_small`, `aspect.change_aspect`) each proving a
  NON-default override reaches the real call; run-state/pause/**Stop**
  button availability; the settings round-trip incl. Upscale's
  min-side and Aspect's target-ratio + filter; `PainterGui.
  _start_tool_from_panel`'s pre-filter path end to end through a
  duck-typed `FakeGuiForPanel`, its `_run_tool_job` a RECORDING
  stand-in; `PainterGui._stop_tool`'s request half (sets the event,
  wins over a pending pause, no-ops when nothing is running); `_run_
  tool_job`'s should_stop halting BETWEEN images — mirrors test_
  runner.py's own `test_stop_flag_stops_between_items` — over a
  duck-typed fake with a real `queue.Queue`) plus 3 engine-level tests
  in `tests/test_postprocess.py` (Phase 13, the safety/margin/
  clean-edge overrides each produce an observably different result
  than the default) plus updated `tests/test_gui_running_view.py`
  coverage (`_open_tool_panel`/`_select_tile`'s shortcut and `_toggle_
  pause_job`'s reveal for ALL FOUR tools, not just bg/crop) — full
  suite green throughout (453 → 479 tests, GUI rework Phase 14).
  Real-window screenshots (Day theme, settings.json redirected to a
  scratch file, synthetic images — never DOMY Watch, never the
  project's own `out/`) confirmed: the Upscale panel (min-side spinner
  + filter, no Advanced gear); the Aspect panel (visual ratio box +
  W/H entries + filter + the permanent deform warning, no Advanced
  gear); and a tool job STOPPED genuinely mid-run — Stop clicked on
  the revealed panel, the dashboard shows the halt, the panel closes
  and the view settles back toward the menu once nothing else is
  running. Phase 13's own BG-removal-flow screenshot walkthrough
  (Menu → BG tile → panel → Start → Pause reveals it → Resume →
  completes → switching to Crop leaves BG undisturbed) is UNCHANGED
  and still accurate — re-verified, not re-screenshotted, this phase.

  **Verified, GUI rework Phase 15 (0.0.1xx):** `ImageCheckerSettingsPanel`
  gets the SAME `tests/test_gui_tool_panels.py` treatment as its four
  siblings — no Advanced section, `_picker_title_suffix()` overridden
  to `"(read-only)"` (checked against `BgSettingsPanel`'s own unchanged
  `"runs IN PLACE"` default, side by side), the input picker + the
  `conditions`-only settings round-trip. `PainterGui._start_ai_check`'s
  pre-filter path end to end through a NEW small duck-typed
  `FakeGuiForAiCheck` (`_run_ai_check_job` a RECORDING stand-in — the
  SAME `FakeGuiForPanel`/`_run_tool_job` convention, one level over:
  the one-job guard, the `_ensure_ai_key()` gate, the "nothing picked"
  messagebox, and the Start tail — panel hidden, `_apply_running_
  layout()`/`_sync_running_state()` called, the dashboard `AiCheckPanel`
  stand-in `.reset()`). **Stop** needed NO new request-half test of its
  own — `PainterGui._stop_tool` is reused UNCHANGED, so the EXISTING
  `FakeGuiForPanel`-based Stop tests just gained an `"aicheck"`-keyed
  pair proving the same generic method also covers this slot.
  `_run_ai_check_job`'s new `stop_event` gets the EXACT mirror of
  `_run_tool_job`'s own should_stop test — `painter.ai.check_one_image`
  MONKEYPATCHED (no network, no API quota spent), should_stop firing on
  the SECOND between-image check halts after exactly one (mocked)
  vision call, `sheet_done`/`__tool_done__` still posted (the `finally`
  block is unconditional). `config.tile_for_kind` gets its own
  `test_config.py` coverage (the four tools resolve to themselves,
  `"aicheck"` → `"image_checker"`, a shared/multi-kind or unknown kind →
  `None`). `tests/test_gui_running_view.py` gained a fifth
  `_tool_panels` entry (`FakeGui`, keyed `"image_checker"`) and its own
  `_tool_panel_key` alias, then the SAME bg/upscale-shaped assertions
  for the checker: `_select_tile`/`_click_icon_bar_tile` open/toggle its
  panel (never the old `_start_ai_check`-calls-directly stub, now
  deleted along with the stub itself), and pausing `"aicheck"` reveals
  `_tool_panels["image_checker"]` — proving the tile-id/slot bridge for
  real. Full suite green throughout (479 → 496 tests). Real-window
  screenshots (Day theme, settings.json redirected to a scratch file,
  synthetic images, `painter.ai.check_one_image` MOCKED so a live run
  spends no API quota) confirmed: the Image Checker panel from its Menu
  tile (folder picked, Start/Pause/Stop, the read-only footer note) and
  a mocked check run Stopped mid-way — the dashboard halts on the
  in-flight image, the panel closes and the view settles back toward
  the Menu once nothing else is running, the SAME shape the Phase 14
  screenshot already proved for a tool.
- **FilterEditor** (GUI rework Phase 4, `ttk.Frame`) — the reusable
  stacked-condition widget wrapping [Shared Filter
  Framework](painter/filters.md): zero or more removable ROWS (each a
  kind combo from `FILTER_KINDS`, an IF/IF-NOT polarity combo, and
  either ONE numeric field — "Aspect (exact)", a target ratio, see
  below — or a lo/hi pair for every other kind), a rounded "+ Add
  condition" button seeding a fresh ~square Aspect-range row, and a
  PRESET row (an editable `rounded_combo` of saved names + Save / Load
  / Delete). Public API `get_conditions() -> list[FilterCondition]` /
  `set_conditions(conditions)` — `get_conditions` raises `ValueError`
  (naming the offending kind) on an unparsable or inverted row rather
  than returning a partial list; the embedding dialog/panel catches it
  and shows a messagebox (every embedding caller does exactly this,
  see below). Callers as of GUI rework Phase 14 — ALL embedded,
  always-visible (the old MODAL callers, `AspectRatioDialog`/
  `UpscaleParamsDialog`, are both retired): each `AgentPanel`'s
  upscale-gate block, pre-seeded with one Aspect (range) condition
  (see **The two AGENT PANELS**); `BgSettingsPanel`/`CropSettingsPanel`
  — unseeded, empty by default; `UpscaleSettingsPanel` — pre-seeded
  the SAME way `AgentPanel`'s own gate is; `AspectSettingsPanel` —
  unseeded, matching the old `AspectRatioDialog`'s own default (see
  **Standalone-tool settings panels** above for all four). None of
  these have a "Run"/"OK" moment to read `get_conditions()` at, so
  their conditions are captured FRESH every settings save (`AgentPanel
  .get_settings`/`ToolSettingsPanel.get_settings`) rather than through
  a per-keystroke `tk.Variable` trace like every other persisted field
  — never silently lost (the debounced autosave any OTHER field edit
  schedules, or the app's close-time save, both pick up the current
  widget state), just not INSTANTLY scheduled by a filter-only edit
  the way e.g. the min-side spinner is.
  **Exact-aspect tolerance** (fixes Phase 3's flagged caveat): a pinned
  "Aspect (exact)" `lo == hi` is a razor-thin float equality a REAL
  decoded image's W/H division almost never lands on, so ITS row shows
  only ONE ratio field — `to_condition` widens it into
  `[ratio - FILTER_ASPECT_EXACT_TOL, ratio + FILTER_ASPECT_EXACT_TOL]`
  (0.02) before building the `FilterCondition`; the reverse display
  (`_filter_row_display_bounds`) shows the stored band's MIDPOINT, so a
  round-trip through set/get reproduces the same band as long as the
  tolerance constant is unchanged. **Presets are a SHARED library** —
  ONE `settings.json` key (`config.FILTER_PRESETS_SETTING`,
  `{name: [condition-dict, ...]}`) every `FilterEditor` instance reads
  and writes via dependency injection, not a direct file open: the
  constructor takes the owner's live `presets` dict (mutated IN PLACE
  by Save/Delete) and an `on_presets_changed` callback
  (`PainterGui._on_filter_presets_changed` → `_schedule_save`, the same
  debounce every other remembered choice already uses) — both are
  OPTIONAL, so a standalone construction (a test, or a future panel
  with no PainterGui yet) still works against a private in-memory
  dict. This split matters: `_collect_settings`/`_save_now` always
  overwrite the WHOLE settings.json from `PainterGui`'s own in-memory
  fields (never a merge — see **Settings persistence** below), so a
  preset saved anywhere MUST live in `PainterGui._filter_presets` (not
  only on disk) or the next unrelated autosave — even the one
  `_on_close` always fires — would silently erase it.
  `FilterCondition<->dict` (de)serialization
  (`painter.filters.condition_to_dict`/`condition_from_dict`) is what
  makes both settings.json persistence and presets JSON-safe.
- **`AspectRatioCanvas`** (GUI rework Phase 5, `tk.Canvas`) — a live,
  draggable preview of the TARGET output ratio, embedded beside a
  target-ratio W/H field pair — today `AgentPanel`'s Force Aspect
  Ratio block and `AspectSettingsPanel`'s own `_build_extra` (GUI
  rework Phase 14, replacing the retired `AspectRatioDialog`, which
  used to be its third host). NOT to be confused with
  **FilterEditor** above: FilterEditor picks WHICH images a tool
  touches, this widget shapes WHAT ratio the tool deforms them TO. A
  rectangle, centred in a fixed square arena, represents `w:h`;
  grabbing any of its 4 edges reshapes it (LEFT/RIGHT change WIDTH,
  TOP/BOTTOM change HEIGHT, the box always stays centred), with a
  live label showing BOTH forms — the exact decimal
  (`painter.aspect.decimal_ratio_label`, owner-decision standard
  rounding, e.g. "1.778:1") and the smallest-integer form
  (`painter.aspect.reduced_ratio`, gcd-based, e.g. "16:9"). A live
  drag EMPHASIZES the box (thicker outline, bigger handles) as
  feedback that it is actively grabbed.
  **Two-way sync** with the host's own W/H entries — the SAME pattern
  reproduced identically by each of the three hosts (`AgentPanel.
  _on_force_aspect_canvas_drag`/`_on_force_aspect_wh_typed`,
  `AspectSettingsPanel._on_canvas_drag`/`_on_wh_typed`, and the
  retired `AspectRatioDialog`'s own — Rule #5, one PATTERN, each host
  its own tiny glue since the target StringVars differ): dragging an
  edge calls `on_change(w, h)`, which the host mirrors into its own
  W/H StringVars; typing in either entry (a `trace_add("write", ...)`)
  parses both as positive ints and calls the canvas's `set_ratio(w,
  h)` — a bad or incomplete value (mid-edit, e.g. a momentarily empty
  field) is silently skipped, never an error dialog on every keystroke
  (final validation happens on Start/Run: `AgentPanel.
  force_aspect_ratio()` / `AspectSettingsPanel.target_ratio()`).
  `set_ratio` NO-OPS when passed the SAME `(w, h)` it already holds,
  which is exactly what a drag's own `on_change` round-trips back as
  through the entry-var trace — without that guard, every drag tick
  would re-"fit" the box to the arena and visibly SNAP, fighting the
  live gesture.
  **Drag math**: each of the 4 edges (not just 2 axes) is tracked
  individually — grabbing the RIGHT edge clamps its effective x to
  never cross the centre, so an overshot/fast drag HOLDS at the
  minimum size instead of "growing" again once the cursor passes the
  opposite side (a real bug caught while writing this widget's
  headless drag-math smoke checks, fixed before it ever shipped).
  **Theming**: a FIXED pixel size (`ASPECT_CANVAS_*` geometry
  constants in gui.py, same Rule #4 split as `FILTER_ROW_*` above —
  pure engine constants live in `painter/config.py`, pure Tk pixel
  geometry lives here) — it does not track the font zoom, like
  `DayNightSwitch`. Its background is a `skin_canvas` surface
  (re-tints automatically on a flip); its drawn content (box, handles,
  label) reads `job_color("aspect")`/`THEMES[ACTIVE_THEME]` LIVE at
  draw time and exposes `redraw_theme()` for a host to call
  explicitly on a flip. Both of today's hosts are non-modal, LIVE
  parts of the main window, so both register in `THEME_TOPLEVELS` and
  call `redraw_theme()` from their OWN `apply_theme()` (the pattern
  every other themed Toplevel already follows): `AgentPanel`'s Force
  Aspect Ratio block (GUI rework Phase 8) and `AspectSettingsPanel`
  (Phase 14). The retired `AspectRatioDialog` never needed this — it
  was fully MODAL (`grab_set`), so — exactly like `AiKeyWizard` (see
  **Theming** below) — a flip could never happen while it was open,
  and it deliberately did NOT register in `THEME_TOPLEVELS`.
- **Stop** — graceful: the site finishes its current item;
  everything finished is already saved.
- **Pause (the toggle button, owner 2026-07-21)** — indefinite, not
  timed: blocks the run BETWEEN items/images until Resume (the same
  button, label flipped) or Stop (Stop always wins over a pending or
  active pause). One toggle PER JOB — pausing ChatGPT never touches
  Gemini or a running tool. See **Pause** further below for the full
  mechanism; not to be confused with the NEXT bullet's pace range,
  which shares the word but is a different, pre-existing feature.
- **Pause / Action delay (the pace RANGES, unrelated to the button
  above)** — both are random FROM–TO ranges: the
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
- **The AI row** (owner 2026-07-20, a SECOND toolbar row so the tool
  row never clips at the window minimum) — TWO buttons over
  [AI Client & Flows](painter/ai.md) (a THIRD, **AI check…**, used to
  sit here directly popping its folder dialog + confirm — DELETED GUI
  rework Phase 15 alongside that inline flow itself, same reasoning as
  the four tools' own quick buttons before it: the Main Menu/IconBar's
  `image_checker` tile now opens `ImageCheckerSettingsPanel`, see
  **Standalone-tool settings panels** and `AiCheckPanel` under the
  Dashboard section):
    - **New collection (AI)…** opens `AiSheetDialog` — the owner
      types the request (any language), the model returns a short
      clarifying POLL (first call: the sheet contract + a
      questions-only system prompt), the answers (each skippable)
      feed the second call, and the produced `.md` is validated with
      the REAL parser plus ONE automatic repair round. Valid → saved
      under the project-local `sheets/` (slugged filename, created on
      demand) and ADDED to the Collections queue; still broken → the
      raw md opens in a `DocWindow` for manual fixing and is NOT
      loaded. Non-modal, worker-threaded, progress in the Log.
    - **AI key…** opens `AiKeyWizard` — the guided key onboarding:
      four numbered steps (1. a button opening
      `aistudio.google.com` via `webbrowser`, 2. sign in with any
      Google account, 3. Get API key → Create API key, 4. paste it),
      a **Test key** making one tiny real call on a worker thread
      (OK in green / the loud `AiError` in red), and **Save key**
      persisting it. The wizard ALSO opens AUTOMATICALLY whenever an
      AI feature is invoked and `painter.ai` raises `NoKey`
      (`_ensure_ai_key` re-checks after it closes).
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
  across starts: the output folder, EVERY per-agent panel setting
  (including each agent's OWN Settings-gear collapse state), the font
  zoom base, the **theme** (`day` / `night`), the window geometry, and
  the **collapsed/expanded** controls state (selection ticks stay
  per-run; the old dashboard `sash` is gone with the PanedWindow, and
  the old TOP-LEVEL `settings_collapsed` from 0.0.079 is gone too — a
  stale key is ignored). The **collection queue is NOT persisted** — the app
  starts with an empty list every launch (owner 2026-07-18); and a
  saved output folder that no longer exists is ignored in favour of
  the default `out/`, so done-detection checks the real output tree
  instead of a stale path. Saves debounce on every meaningful change (var traces —
  the per-agent gear collapse rides a BooleanVar so it saves like every
  other field —, zoom, theme flip, the Controls collapse, the two
  remembered dialogs) and always fire on close; loading applies missing
  keys as current defaults (a missing `theme` = `night`, a missing agent
  `settings_collapsed` = True) and drops queued files that no longer
  exist (reported in the log). The stored dict: `output`, `font_base`,
  `theme`, `geometry`, `controls_collapsed`, `gemini_api_key` (the AI
  features' credential, owner 2026-07-20 — held on the GUI so the
  whole-dict save round-trips it; the wizard's Save persists
  IMMEDIATELY via `set_gemini_key` → `_save_now`, since `painter.ai`
  reads the key back from disk per call), `filter_presets`
  (`config.FILTER_PRESETS_SETTING` — the shared `FilterEditor` preset
  library, `{name: [condition-dict, ...]}` — shared by EVERY
  `FilterEditor` instance in the app, including each agent's own
  upscale-gate filter and all five standalone job panels'), `agents.
  <site>` (below) and `tool_panels.<tile-id>` — ALL FIVE standalone
  jobs' own settings (`{tile_id: panel.get_settings()}`, keyed by
  MENU_TILES id — `"image_checker"` for the AI checker, GUI rework
  Phase 15, its own JOB_ORDER slot `"aicheck"` — see **Standalone-tool
  settings panels** for each panel's own field shape: BG/Crop's safety/
  margin/ink-alpha overrides + `advanced_collapsed`; Upscale's
  `up_minside`; Aspect's `ratio`; the AI checker has none of its own;
  every panel's `conditions`). GUI rework Phase 14 RETIRED the OLD
  top-level `upscale_tool`/
  `aspect_ratio`/`aspect_filter_conditions` keys the standalone Upscale/
  Aspect MODAL dialogs used to own (`_collect_settings` no longer emits
  any of the three) — see **the tool-panel migration** below for how an
  owner's already-saved values move into `tool_panels` instead.

  `agents.<site>` carries
  `background`, `style`
  (the rendering-style dropdown), `bg_removal`, `crop`, `upscale`,
  `report`, `safer_retry`, `continue_nudge`, `new_chat`,
  `pause_min/max`, `act_min/max`,
  the per-agent upscale-gate `up_minside` (GUI rework Phase 6, REPLACING
  the old `up_minw`/`up_minh`/`up_aspmin`/`up_aspmax` four scalars) plus
  `up_filter_conditions` (that agent's embedded `FilterEditor` stack —
  NOT a plain `tk.Variable`, so `AgentPanel.get_settings`/
  `apply_settings` handle it explicitly, outside the `_PERSIST`-tuple
  loop every other field goes through), `force_aspect`/
  `force_aspect_w`/`force_aspect_h` (GUI rework Phase 8's Force Aspect
  Ratio switch + target ratio — plain `tk.Variable`s, so they DO go
  through the ordinary `_PERSIST` loop) and `keep_all_steps` (that
  agent's "keep every pipeline step" disk-usage toggle, default
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT`), and that agent's
  `settings_collapsed`.

  **The `aspect_filter` -> `aspect_filter_conditions` migration** (GUI
  rework Phase 4, owner decision 2026-07-21; Phase 14 moves the TARGET
  from a PainterGui attribute to `AspectSettingsPanel`'s own field, see
  below — the SOURCE keys and the pure conversion are unchanged): if
  the OLD scalar `aspect_filter` key is on disk (an owner who used the
  tool before Phase 4) and NEITHER `aspect_filter_conditions` (Phase
  4–13) NOR the panel's own `conditions` (Phase 14+) is present, a
  ONE-TIME LOUD migration (`gui._migrate_legacy_aspect_filter`, logged
  via `self._log`) converts it to an equivalent single-condition list —
  `off` -> an empty list (already "matches everything"), `IF`/`IF NOT`
  -> one `FILTER_KIND_ASPECT_RANGE` condition with the SAME from/to/
  polarity numbers, so behaviour is preserved exactly. A malformed
  condition entry, or an `aspect_filter` whose `mode` isn't one of the
  three legacy strings, is DROPPED with a loud log line rather than
  crashing startup (`gui._parse_condition_dicts` / a caught `ValueError`
  around the migration call) — the same "a corrupt file loses the
  remembered choice, never the app" precedent `painter.settings.
  load_settings` already sets.

  **The upscale-gate migration** (GUI rework Phase 6, same additive
  pattern; Phase 14 moves the STANDALONE half's target the same way):
  both upscale gates — each agent's `up_minw`/`up_minh`/`up_aspmin`/
  `up_aspmax` AND the standalone dialog's OLD top-level `upscale_tool`
  `min_width`/`min_height`/`aspect_min`/`aspect_max` — migrate to the
  NEW `up_minside`+condition shapes via the shared pure `gui._migrate_
  legacy_upscale_gate(min_width, aspect_min, aspect_max) -> {"min_side",
  "conditions"}` (Tk-free, unit-tested against the owner's real saved
  numbers in `test_gui_upscale.py`). `min_height` is intentionally
  DROPPED — the two axes collapse into ONE min-side spinner, and
  `min_width`/`up_minw` is kept for it (every shipped default and every
  real settings.json seen so far already had width == height, so
  nothing observable is lost in practice); the aspect `[from, to]`
  becomes ONE `FILTER_KIND_ASPECT_RANGE` IF condition, the SAME numbers.
  The per-agent call site (`_apply_settings`'s `agents` loop) triggers
  migration only when the OLD keys are present AND the NEW `up_minside`
  key is ABSENT, logs loudly via `self._log` on success (and separately
  on a genuinely unparsable legacy value, falling back to the shipped
  default gate rather than crashing startup), and never rewrites the
  old keys — they naturally drop off disk on the next save, same as
  every other migration in this file.

  **The tool-panel migration** (GUI rework Phase 14): `_apply_settings`'s
  `tool_panels` loop runs `_migrate_upscale_panel_settings`/`_migrate_
  aspect_panel_settings` on each panel's stored dict BEFORE calling
  `panel.apply_settings(...)` — a no-op once a panel has saved itself
  at least once under the NEW `tool_panels` key (its own `up_minside`/
  `ratio` already present). Otherwise each reads the retired top-level
  `upscale_tool` / `aspect_ratio` + `aspect_filter_conditions` (or the
  even older scalar `aspect_filter`) keys, chaining into the SAME
  `_migrate_legacy_upscale_gate`/`_migrate_legacy_aspect_filter` pure
  functions the per-agent/Phase-4 migrations above already use (Rule
  #5 — one conversion each, several target shapes), and injects
  `up_minside`/`ratio`/`conditions` into the panel's stored dict before
  handing it to `apply_settings`. Logs loudly on every migration and on
  every unreadable legacy value (falls back to the panel's shipped
  default, never crashes startup); the old top-level keys are never
  rewritten — `_collect_settings` no longer emits them at all, so they
  naturally drop off disk on the next save, exactly like every other
  retired key in this file.

## The Dashboard — per-JOB panels (owner 2026-07-19)
The dashboard shows one panel PER RUNNING JOB, up to SEVEN in parallel:
the two generation SITES (ChatGPT, Gemini), the four in-place TOOLS
(BG removal, Crop, Upscale, Aspect ratio) and the AI CHECKER (owner
2026-07-20). Panels are no longer fixed —
a panel APPEARS when its job STARTS (a site Start / a tool button) and
gets a **✕ Close** button when the job FINISHES; Close removes the
panel from the grid AND clears that job's temp backups. Only
running-or-ran jobs show.

**`JobPanel`** is the shared base: a coloured header (an ICON via
`config.JOB_LOGO` + `icon()` — a brand logo for the two sites, a
dedicated PNG for each of the four tools, owner 2026-07-19 — plus the
job NAME in the job's `(day, night)` `JOB_COLORS` pair), the muted state
line (quota countdown / current item / paused), an OPTIONAL `btn_pause`
(owner 2026-07-21 — built only when the panel is constructed with
`on_pause`; a plain `kind="secondary"` button whose label alone flips
Pause ↔ Resume, beside Close in the header) and the
hidden CLOSE button `finish()` reveals / `reset_finished()` hides.
`set_paused(is_paused)` is the shared visual update both
`_toggle_pause_job` and a panel's own construction rely on: it always
sets the state line (`"paused — waiting to resume"` / `""`) and, when
`btn_pause` exists, its label. `ToolPanel` and `AiCheckPanel` are
built WITH `on_pause` (their own toggle, since neither has a separate
control panel); `DashPanel` is built WITHOUT it (chatgpt/gemini's
button lives on `AgentPanel` instead — a different class, its OWN
`set_paused` toggling just its `btn_pause` label) — `set_paused` still
works there because `DashPanel` inherits it from `JobPanel`, so the
Dashboard tab's state line reflects a site's pause even though the
BUTTON that caused it lives in the Controls area. See **Pause** below
for the full mechanism. It
also carries the shared root/folder TREE-NODE plumbing
(`_ensure_root` / `_ensure_folder`) for the folder-based panels
(ToolPanel, AiCheckPanel), whose rowed table itself is built by the
module `build_job_tree` helper (Rule #5 — one home for the Treeview +
round scrollbars + theme tags); DashPanel builds its own theme-keyed
nodes and never calls these.
`DashPanel(JobPanel)` is one gen site's view; `ToolPanel(JobPanel)` is
one tool's. Both are BUILT ONCE (never destroyed) and fed ONLY by the
runner/worker's structured events on the main thread.

**`DashGrid`** replaces the old draggable `ttk.PanedWindow`. It holds
the seven build-once panels and re-flows them by ACTIVE COUNT via
`config.GRID_COLS_BY_COUNT` (1→1 col, 2→2, 3→3, 4→2×2, 5→2×3, 6→2×3,
7→3×3;
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
  prompt + the saved image. **Steps…** (GUI rework Phase 9, beside
  Show — never the double-click) opens a per-step restore filmstrip
  for the SAME focused image row; see **Per-step restore viewer**
  below.
- **Status badges** (owner 2026-07-20; the `aspect` dot added GUI
  rework Phase 8) — each image row carries small coloured DOTS beside
  its name for what actually HAPPENED to that image: green `bg` = BG
  removed, orange `crop` = cropped, magenta/fuchsia `aspect` = aspect
  forced, blue `upscale` = upscaled, purple `retry` = the one-shot
  safer retry produced it — render order matches the PIPELINE order
  (bg, crop, aspect, upscale), retry last. A post-save step earns its
  dot ONLY when it really
  CHANGED the file (`config.badge_keys_for` maps the runner's
  `actions` string — a step counts on status `done`, never `nothing`
  / `unclear` / `FAILED`; `"ASPECT"` is `BADGE_ACTION_STEPS`' new
  fourth key); `retried` comes from the same
  `item_progress`/`item_done` payload. The dots are PIL-DRAWN
  (module `badge_dots`, supersampled + LANCZOS, one cached
  PhotoImage per key-combination) and attached as the row's Treeview
  image — Tk 8.6 on Windows renders colour EMOJI as identical
  monochrome circles (probed live 2026-07-20), so glyph badges were
  not an option; a row image is the only per-row colour a
  `ttk.Treeview` offers and sits LEFT of the name. Colours/labels
  are pure config data (`config.BADGES` — the owner retints there;
  deliberately theme-agnostic mid-tones that read on both the dark
  and the cream tree). A tiny mono-font LEGEND line under the
  Collections header (`● BG removed ● cropped ● aspect forced ●
  upscaled ● safer retry`, each label tinted its badge colour) spells
  them out.

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
  op is `0.2s`, not `fmt_duration`'s flattened `0s`); every % (the avg
  stat AND the per-row column) uses `config.fmt_pct` (2 decimals below
  10, 1 from 10) so a tiny metric reads `0.24%`, not `0%`.
- a **collection → folder → image** `ttk.Treeview`. The dimensional
  tools (Crop / Upscale / Aspect) show Name · Before · After · % · Time
  · Size — each image row its BEFORE / AFTER resolution, the tool's %,
  and its per-image op time. **BG removal DROPS the Before/After
  columns** (owner 2026-07-19): it changes ALPHA, not dimensions, so
  before == after resolution is meaningless — its panel shows Name · % ·
  Time · Size only (`self._is_bg` picks the column set). CHANGED vs
  SKIPPED rows are tinted by TWO theme-aware Treeview tags (owner
  2026-07-19), so they NEVER blur together:
    - a CHANGED (restorable) row carries `TOOL_CHANGED_TAG`, a BOLD
      striking green/teal (`status["toolchanged"]` — `#2ee59d` mint on
      night, `#0a9d6e` emerald on the cream day) that POPS off both
      backgrounds;
    - a refused (no-op) row shows `—` in % and BLANK Time and carries
      `TOOL_SKIP_TAG`, the muted `status["skip"]` (`#adb5bd` night /
      `#8a8578` day). This bucket also holds the many 0px crops the
      crop-fix (SKIPPED iff output resolution == input) routes to skipped.
  Both tags are theme-aware — `skin_tree` registers them in the plain-tk
  skin registry (`_apply_tree_skin`) so they re-tint on a Day/Night flip.
- **Double-click an image row** opens a `BeforeAfterWindow` for that
  image with a **Restore** (reverts ONLY it); **double-click a FOLDER
  node** opens a viewer of ONLY that folder's changed images (title names
  the folder + count) with **RESTORE ALL** reverting JUST that folder
  (`rels_in_folder` filters `_image_rows` by `folder_of`; `restore_folder`
  restores only those rels — owner 2026-07-19, the fix for a folder click
  that used to revert the WHOLE job); **double-click the collection (top)
  node** still opens ALL the job's changed images with a whole-job RESTORE
  ALL. A restore marks the row(s) restored and puts the ORIGINAL back on
  disk (see below). Works for ALL four tools — BG removal included: it
  changes ALPHA, not dimensions, and the viewer keys off the BACKUP
  existing (never a resolution change), so a cleared-background image
  shows before/after just like a resized one.

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
startup. `self._job_temps` (RENAMED from `_tool_temps`, GUI rework
Phase 8 — grep-verified every call site) is the dict of live slot →
`JobTemp`; it now holds up to SEVEN entries (the four tools' unnamed
backups AND, since Phase 8, the two gen sites' own per-step pipeline
backups below — `_close_panel`/`_on_close` already popped/cleared it
generically by kind, so the rename needed no branching logic change).

#### Pipeline reorder + per-step backups (GUI rework Phase 8)
Gen jobs used to make NEW files only and need no restore; Phase 8
adds a SECOND kind of backup — not "undo the tool", but "step back
through the pipeline" — so each SITE job now also gets its own
`JobTemp` (created in `_start_site`, right before `_compose_post_save`
reads it, so the composed closure captures it; cleared exactly where
a tool's is, `folder=out_base` so a rel is `dest.relative_to(out_base)`
same as `dest_for`'s own output layout).

`PainterGui._compose_post_save(key)` composes the site's post-save
hook — do_bg/do_crop/do_aspect/do_upscale, read once at Start like the
pace values — into `post_save(path) -> "REMOVE BG: done, CROP: done,
ASPECT: done, UPSCALE: done"`; the per-image engine is the pure,
Tk-free module function **`_run_pipeline_steps(path, steps, temp,
keep_all_steps, on_cap)`**, given the caller-built `(label, step_name,
fn)` triples for whichever switches are ON, ALWAYS in pipeline order
— **BG → Crop → Aspect(force) → Upscale** — never reordered by which
happen to be ticked. With Force Aspect OFF (its default) this is
BYTE-IDENTICAL to the pre-Phase-8 pipeline: the backups below only
ever COPY bytes elsewhere, never touch `path` itself.

Per-step backups, when a `JobTemp` is attached:
- the FIRST enabled step's PRE-state is tagged `step="original"` — the
  pristine, restore-everything baseline (the runner's raw just-saved
  image) — and is ALWAYS taken, cap or toggle or not, so every image
  keeps at least this one restore point. This DEDUPS against that
  first step's own name (owner ask): both would be byte-identical
  backups of the same instant, so only ONE is ever written — a
  `steps_for()` filmstrip for an image whose first enabled step was BG
  therefore lists `["original", "crop", ...]`, never `["original",
  "bg", "crop", ...]`. See the `JOBTEMP_STEP_NAMES` ordering-contract
  comment in [Config](painter/config.md).
- every LATER enabled step's pre-state gets its OWN named backup
  (`"bg"`/`"crop"`/`"aspect"`/`"upscale"`) — but only when the
  per-agent **Keep every pipeline step** switch (`keep_all_steps_var`,
  default `JOBTEMP_KEEP_ALL_STEPS_DEFAULT`) is on AND the job is not
  yet `JobTemp.over_cap()` (`JOBTEMP_MAX_BYTES`, 4 GiB default). Once
  over cap, NEW per-step backups stop — "original-only" — and `on_cap`
  fires; a toggle-OFF produces the identical original-only outcome
  SILENTLY (a deliberate owner choice, not a disk emergency — `on_cap`
  is reserved for the real cap).
- a step's OWN named backup whose result was `"nothing"` (a genuine
  no-op) is DROPPED right back, mirroring the four tools' own
  restore-point hygiene — a no-op has nothing worth restoring;
  `"original"` is never dropped regardless of any step's own outcome.

`_compose_post_save`'s `on_cap` wrapper (NOT `_run_pipeline_steps`
itself, which can fire it many times) DEDUPS to exactly ONE
`{"type": "over_cap"}` event per Start, posted through the ordinary
`self._q`/`__event__` channel to `DashPanel.handle`. Unlike the muted,
constantly-overwritten `state_var` line, the banner is a dedicated,
LOUD, PERSISTENT strip (`JobPanel._show_cap_banner`/
`_hide_cap_banner`, `bootstyle="inverse-warning"`, packed right after
the state line via `after=self._state_label` so its position is fixed
regardless of build order) that survives every later progress event —
only `reset()` (a fresh Start) hides it again. `config.
JOBTEMP_CAP_BANNER_TEXT` is the message (formatted from
`JOBTEMP_MAX_BYTES` so the GiB number can never drift from the real
cap).

The Force Aspect target ratio is edited via an embedded
`AspectRatioCanvas` (Phase 5) — a non-modal host, so a live Day/Night
flip CAN happen while this panel's fine-tune box is expanded, unlike
the retired fully-modal `AspectRatioDialog` (GUI rework Phase 14).
`AgentPanel` gained its own `apply_theme()` (calls the canvas's
`redraw_theme()`) and registers itself in `THEME_TOPLEVELS` despite
not being a Toplevel — see **Theming**'s note on that list really
meaning "anything exposing apply_theme()", not literally "every
Toplevel" (`AspectSettingsPanel`, Phase 14, does the exact same thing
for its own embedded canvas).

#### Per-step restore viewer (GUI rework Phase 9)
`DashPanel` gains the same two attributes `ToolPanel` has always had
for its own before/after viewer — `self.jobtemp` (now declared once on
the shared `JobPanel` base, Rule #5, so both subclasses inherit it
identically instead of redeclaring the same line) and a NEW
`self.out_base` (mirrors `ToolPanel.folder`'s role — the site's output
root, needed to resolve a row's SITE-AGNOSTIC drop path into the
JobTemp `rel`/live file via `dest_for`). `_start_site` sets both,
right beside `reset()`, the same grouping `_launch_tool_worker`
already uses for `panel.folder`/`panel.jobtemp`.

A new **Steps…** button sits beside **Show** in the Collections
sub-header — a SEPARATE button, never overloaded onto the tree's own
double-click (which stays wired to `_show_selected`/"Show prompt +
image", untouched). No dedicated icon exists yet for "restore a
pipeline stage", so it is plain text (flagged, not a design decision).
It acts on the SAME focused/selected row `_show_selected` would use;
`DashPanel._show_steps` resolves `rel = dest_for(info["drop"],
self.slot_key)`, guards with three info dialogs (no image row
selected; no `jobtemp`/`out_base` yet — Steps clicked before this
panel instance ever ran a job; `jobtemp.steps_for(rel)` empty — no
post-save step ran, or "Keep every pipeline step" was off) and, once
past those, opens a `StepRestoreWindow`.

`StepRestoreWindow(tk.Toplevel)` shows one image's kept pipeline
stages as a horizontal filmstrip — Original → BG → Crop → Aspect →
Upscale (whichever the JobTemp actually backed up, plus the pristine
baseline; "Fixer" joins once Phase 20 lands), each thumbnail its own
**Restore to here** button, PLUS the CURRENT live file last (no
button — it already is the live state). The ordered `(label, path)`
list itself is a PURE, Tk-free module function, `_filmstrip_stages(temp,
rel, live_path)` — every named step `steps_for(rel)` returns, in its
own pipeline order, paired with `before_path`, followed by exactly one
final `(STEP_RESTORE_CURRENT_LABEL, live_path)` entry; a caller can zip
`stages[:-1]` 1:1 against `steps_for(rel)` to know which JobTemp step
name a given thumbnail's button targets (`StepRestoreWindow._render`
does exactly this). Labels come from `config.JOBTEMP_STEP_LABEL` —
reusing `JOB_LABEL` for the four real tool stages (Rule #5), plus
"Original"/"Fixer AI" for the two pipeline bookends that are not tools
themselves. Clicking **Restore to here** calls `JobTemp.restore_to(rel,
step)`, RE-RENDERS the whole filmstrip in place (the 'Current'
thumbnail and the remaining stage list both re-read straight off disk,
so a restore is immediately visible without closing/reopening the
window), then calls `on_restored` — `DashPanel.refresh_image_row`,
which re-reads the row's resolution/size straight off disk. Badge dots
are NOT retroactively recomputed on a restore (no per-row action
string survives past insert, only the rendered PIL dots already
drawn) — a known, cosmetic gap; the restored FILE itself is always
correct regardless of what its dots still show.

Non-modal, themed exactly like `BeforeAfterWindow` (skinned Toplevel,
registered in `THEME_TOPLEVELS`, its scaled `PhotoImage`s held on
`self._photos` so tk cannot GC them, `_scaled_photo(..., on_checker=
True)` so a transparent intermediate — e.g. right after BG removal —
reads as removed rather than as the window colour) — the one
structural difference is a HORIZONTAL `ScrollFrame` (`STEP_RESTORE_W`/
`STEP_RESTORE_THUMB_PX` geometry) instead of BeforeAfterWindow's
stacked vertical one, since pipeline stages read left-to-right like a
real filmstrip. `StepRestoreWindow` itself carries no direct pytest
coverage (same "real Tk/UI wiring gets a screenshot" convention as
`BeforeAfterWindow`/`DocWindow`) — only `_filmstrip_stages` (pure) and
`DashPanel._show_steps`/`refresh_image_row` (a real Tk root, `gui.
StepRestoreWindow` mocked so no actual window is constructed) are
pytest-covered; see [Tests](tests/___tests.md).

### `AiCheckPanel` — the AI image checker (owner 2026-07-20)
The seventh job slot (`aicheck`, rose `JOB_COLORS`, the `ai` png). This
is the DASHBOARD half only — the LAUNCH surface (folder/files pick +
Start/Pause/Stop) moved to its own `ImageCheckerSettingsPanel` in GUI
rework Phase 15 (see **Standalone-tool settings panels** under **The
window**); nothing below changed. `PainterGui._start_ai_check` gates
on the key (`_ensure_ai_key` — the wizard auto-opens on `NoKey`), reads
the SETTINGS PANEL's own folder/files pick + stacked filter (no more
inline `askdirectory`/confirm `askyesno` — the panel's Start already
IS the confirmation, same contract as every sibling panel; the read-
only footer note still tells the owner about the paced ~`AI_CALL_
PAUSE_S` s/call cost) and starts `_run_ai_check_job` on its own worker
(registered in `_tool_workers["aicheck"]`, so the one-job-per-kind
guard and the `__tool_done__` plumbing are reused as-is). **Stop**
(GUI rework Phase 15, closing Phase 14's own flagged gap for this job)
reuses `PainterGui._stop_tool` verbatim from the checker's settings
panel — sets a new `_stop_events["aicheck"]`, which `_run_ai_check_job`
now checks BETWEEN images (mirroring `_run_tool_job`'s own should_stop
exactly, including inside `wait_while_paused` so a Stop wins over a
pending Pause); once the worker confirms the halt, `_dispatch` closes
THIS panel (`_close_panel` — harmless no-op on its JobTemp lookup, the
checker never had one) and calls `_request_menu()`, the SAME "smart
stop" sequence the four tools already had. The worker's OWN body is
UNCHANGED: it first `prune_stale_flags` (a REGENERATED file's changed
mtime drops its old flag), then per image calls `ai.check_one_image`
(the pure driver — it times the call, retries transient 503/429
failures, parses the strict OK/DEFECTS answer, merges/clears the flag
and does the FLAGGED/FAIL logging) and maps its `kind` to a row:

- **flagged** → `ai.record_flag` (merged into
  `<out>/_state/ai_flags.json`: defects, the verbatim raw response,
  checked_at, model, the file's mtime) + a STRIKING row
  (`TOOL_CHANGED_TAG`) whose metric is the DEFECT COUNT plus the first
  defect text;
- **OK** → `ai.clear_flag` (a fixed image loses its stale flag) + a
  muted row (`TOOL_SKIP_TAG`);
- a per-image `AiError` (a 503 that survives the retries, a malformed
  answer) is LOUD in the log, counted as an error row, and never kills
  the batch (the tool-job convention).

Every row carries its own op **Time** column (`fmt_op_duration`), and
the panel's stat line shows the total + per-image average over the
CHECKED images (`fmt_time_summary`, shared with the tool panels) — the
owner wanted to see how long the paced checker actually works,
retries included.

The flag KEY is the image's path RELATIVE to the shared Output base
(`ai.flag_key`; absolute for an outside image — persists, but can
never match a queued collection). **Double-click ANY checked row**
(flagged, OK or error) → a `DocWindow` (`ai_check_doc_md`) with the
parsed defects (when any), the **verbatim** AI response under "Full AI
response:" and the image itself — so the owner sees exactly what the
model said about this exact image (the raw response also resolves the
"is this the right image?" doubt: the viewer opens `ai.flag_file`, the
same round-trip the worker's `flag_key` reverses). Two panel actions:

- **Send flagged to generator** → `_resend_flagged`:
  `ai.plan_resend` (pure, GUI-free) reverses each flag key to its
  `(drop_path, site)` (the `dest_for` reverse), matches it against
  the QUEUED sheets' items and returns the per-site plan; each
  matched site is started with
  `_start_site(site, override_selection={sheet: drops},
  extra_suffix={drop: ai.fix_note(defects)})` — the regenerate path
  (`only=` overwrites the flawed file) with the "previous attempt
  had these flaws" note appended per item. An unmatched image and an
  already-running site are LOUD log skips.
- **Clear flags** → `_clear_ai_flags` (`ai.clear_flag_keys`) wipes
  this run's entries and marks the rows `cleared`.

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
`advice` + `n_done` to recompute its colour). **FULLY MODAL dialogs
(`grab_set` + `wait_window`) deliberately do NOT register** —
`AiKeyWizard` today (the standalone `UpscaleParamsDialog`/
`AspectRatioDialog` used to, both retired GUI rework Phase 14): the
grab blocks all input to the rest of the app for as long as they are
open, so the Day/Night switch is unreachable and a flip genuinely
cannot happen while one is on screen; registering would be dead code.
The NON-modal AI dialog (`AiSheetDialog`, a long generation that must
not grab the app) registers — and, since GUI rework Phase 8,
`AgentPanel` (its fine-tune box embeds an `AspectRatioCanvas` too),
and — since Phase 14 — `AspectSettingsPanel` (same reason: its own
embedded canvas). All three are non-modal, LIVE parts of the
always-on-screen main window, so a flip CAN happen while any of them
is on screen — unlike the retired modal dialogs above. `THEME_
TOPLEVELS` is therefore not literally "every Toplevel" any more — the
loop only ever calls `.apply_theme()` on whatever is registered, so a
build-once, never-destroyed `ttk.Labelframe`/`ttk.Frame` works
identically; `AgentPanel.apply_theme()`/`AspectSettingsPanel.
apply_theme()` each just call their OWN canvas's `redraw_theme()`.
`job_color(kind)` mirrors `status(role)`
for the FEW places plain-tk drawing needs a single resolved hex from a
`(day, night)` `JOB_COLORS` pair instead of a CTk auto-resolving
tuple — `AspectRatioCanvas`'s accent, drawn from BOTH its live hosts.

**The snapshot cover — `smooth_transition(root, mutate, ...)`** (owner
2026-07-20, generalizing the 2026-07-18 theme cross-fade into ONE
shared mechanism, Rule #5): tkinter has no native colour transitions
and cannot animate a relayout, so a live theme flip repaints as an
ugly cascade of half-themed frames and a big collapse/expand or a
maximize/restore lands as one hard jump. The shared helper hides all
of these: `_snapshot_overlay` grabs the CURRENT window client area
with `PIL.ImageGrab` (from `winfo_rootx/rooty/width/height`) into an
`ImageTk.PhotoImage` (held on the overlay so tk cannot GC it) and
mounts it in a borderless, topmost, `overrideredirect` Toplevel placed
exactly over the window at `-alpha` 1.0; an optional
`icon_factory(w, h)` composites a PIL image centred INTO the grab.
Order matters (owner 2026-07-19, the flash fix): the overlay is FORCED
fully mapped + painted first — `deiconify` → `lift` →
`update_idletasks` → `update()` (so DWM actually paints the cover on
screen) — ONLY THEN does the `mutate` callback run (the theme repaint
/ the relayout) UNDERNEATH the cover, one forced `update_idletasks`
settles it invisibly, and `_fade_out_overlay` ramps the overlay's
window `-alpha` 1.0 → 0.0 (ease-out) before destroying it. Wired to
FOUR places: the **theme flip** (`apply_theme(animate=True)` passes
`icon_factory` = the NEXT theme's big sun/moon via
`_render_theme_cover_icon` at `SWITCH_COVER_ICON_FRAC` = 30 % of the
window's min dimension, and the ceremonial `SWITCH_FADE_MS` ≈ 500 ms /
`SWITCH_FADE_STEPS` 28 timing), the **▾ Controls collapse**
(`_toggle_collapsed`), each agent's **Settings gear**
(`_toggle_settings`) and the **maximize/restore** jump
(`_on_root_configure`) — the last three icon-less on the snappier
default `TRANSITION_FADE_MS` (260 ms) / `TRANSITION_FADE_STEPS` (14).
It is a pure visual nicety: with no window on screen
(`winfo_ismapped`/`winfo_viewable`) or on ANY cover failure
(ImageGrab unavailable, `-alpha` unsupported) the mutate simply runs
instantly with a one-line log note, any partial overlay destroyed
(root Rule #1 — the cover can never be the reason a toggle stops
working); a mutate exception is NEVER masked — it propagates loudly
while the overlay still fades out via the `finally`. Caveats:
`ImageGrab` grabs SCREEN pixels, so a window occluding ours is
captured in the snapshot — on MAXIMIZE the grab covers the NEW
(bigger) rect, so other windows' pixels ride the cover for its 260 ms
(they were already visible right there, so nothing leaks; it reads as
a full-screen dissolve into the maximized app); and the app shows a
static snapshot for the fade, so live dashboard updates are briefly
hidden. Startup passes `animate=False` (no window yet) — instant
flip, no overlay.

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
`_radial_disc`, then LANCZOS-down). The MOON is a real moon (owner
2026-07-20, replacing the flat 3-crater disc): 7 craters of varied
sizes (`SWITCH_CRATERS`), each with a subtle alpha-blended lit RIM
ARC on the side facing the light (`SWITCH_CRATER_RIM*`); TERMINATOR
shading — brightness ramps from the `SWITCH_MOON_LIGHT_DIR` limb down
to `SWITCH_MOON_DARK_FLOOR` on the far limb across a smoothstep band
— darkens surface, craters and rims together so the sphere reads lit
from one side; and a deterministic low-amplitude value-noise
MOTTLING (`SWITCH_MOON_NOISE_*` — FIXED seed, identical every build)
adds faint maria. The SUN stays the gold gradient over a blurred
glow. The big theme-cover icon reuses these SAME renderers at ~30 %
of the window (`_render_theme_cover_icon`), so knob and cover
improved together; the night track pill (starfield SVG) is untouched.
It is a FIXED size (it does not follow the font zoom), so once is
enough. Each `_redraw` just re-places the track
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
One worker thread per site, started and stopped INDEPENDENTLY by its
panel's buttons (per-KIND stop events — `self._stop_events`, sites
plus the four standalone tools since GUI rework Phase 14, plus the AI
checker since Phase 15, `_stop_tool` — and, owner 2026-07-21, per-KIND
pause events, one per `JOB_ORDER` entry, seven total); each site
creates its own
Playwright instance and `SiteDriver` (sync Playwright is
per-thread) and walks the theme queue sequentially. The four TOOLS
add up to four MORE daemon workers (`_run_tool_job`, GUI rework Phase
14 threads a real should_stop into its loop, mirroring `run_sheet`'s
own — see **Pause** below and **Standalone-tool settings panels**
under **The window**), one per kind
(one job per kind — a second click is refused), and the AI CHECKER a
seventh (`_run_ai_check_job`, same `_tool_workers` bookkeeping — GUI
rework Phase 15 threads its OWN real should_stop into its loop the
identical way, closing what was this section's own flagged gap), so up
to seven jobs run
CONCURRENTLY; each tool worker only backs up + processes files under
its own picked folder and its own `JobTemp` subdir (disjoint writes;
the checker writes only the flag file under `<out>/_state/`) — and,
since GUI rework Phase 8, each SITE worker's post-save pipeline backs
up under ITS OWN `JobTemp` subdir the same way (`self._job_temps`,
keyed by site instead of tool kind — see **Pipeline reorder +
per-step backups**). The AI
DIALOGS (`AiKeyWizard`'s Test, `AiSheetDialog`'s two calls) run their
API work on short-lived daemon threads too, feeding a per-dialog queue
polled with `after` (`_AiDialog` — the workers never touch a widget).
Every worker touches the window ONLY through the single `self._q`
queue drained on the tk timer (`_drain_queue` via `root.after`) — so
every widget mutation runs on the main thread. The drain hands each
message to `_dispatch`; during an ACTIVE drag-resize `__event__`
messages are BUFFERED instead (`_pending_events`) and flushed in
order by `_resize_settled` (owner 2026-07-20 — dashboard tree/label
updates stop re-rendering per drag frame; plain log lines and the
rare control messages still apply immediately). Queue messages:
`('__event__', slot, ev)` routes to `self.panels.get(slot).handle(ev)`
(`.get` is the defensive guard for a late event after a panel closed),
`('__worker_done__', key)` reveals the site panel's CLOSE and clears
the worker bookkeeping, and `('__tool_done__', slot)` does the SAME on
a natural finish — but (GUI rework Phase 14, widened to `"aicheck"` by
Phase 15) instead CLOSES the panel outright (`_close_panel` — same as
a manual Close) and calls `_request_menu()` when this slot's
should_stop event is set (a Stop-triggered finish, see
**Standalone-tool settings panels**' own "Stop" write-up); a quota
`TerminalState` posts its `retry_after_s`
the same way and the main thread schedules the auto-restart via
`root.after` (the panel keeps its countdown, no CLOSE, until the
restart or a Stop).

## Pause (owner 2026-07-21)

A per-JOB Pause toggle — ALL SEVEN `JOB_ORDER` kinds, not just the
two gen sites — separate from the pre-existing pace RANGE that
happens to share the word "pause" (`Timing.pause_min_s`/`pause_max_s`,
the random wait between prompts; see **The window** above). `self.
_pause_events: dict[str, threading.Event]` (one per kind) and `self.
_paused: set[str]` (which kinds are currently paused) live on
`PainterGui`, seeded at `__init__`. **`_toggle_pause_job(kind)`** is
the ONE handler wired to every kind's `btn_pause` — `AgentPanel`'s own
(chatgpt/gemini) and `ToolPanel`'s/`AiCheckPanel`'s own (the other
five): it flips the kind's `Event` + membership in `_paused`, then
calls `set_paused(is_paused)` on the AgentPanel (if this kind has one)
AND on `self.panels[kind]` (every kind has a dashboard panel), so both
the button label and the Dashboard tab's state line agree, and logs a
one-line `[kind] paused`/`resumed`.

The actual wait lives in [Run Loop](painter/runner.md)'s
`wait_while_paused(should_pause, should_stop, log, emit)` — a public
function, not a `run_sheet`-only helper, so THREE call sites share the
exact same poll-wait (`config.PAUSE_POLL_INTERVAL_S`, no busy spin):

- `_drive_site` passes `should_pause=pause_event.is_set` into
  `run_sheet` alongside the existing `should_stop=stop_event.is_set` —
  checked between sheet items; a Stop always wins over a pending pause
  (`should_stop` is re-checked on every poll tick inside the wait).
- `_run_tool_job` and `_run_ai_check_job` call `wait_while_paused`
  directly, once per loop iteration, BETWEEN images, each passing its
  OWN real `should_stop=stop_event.is_set` (`_run_tool_job`, GUI rework
  Phase 14; `_run_ai_check_job`, Phase 15, closing what used to be this
  section's own flagged gap) — a Stop wins over a pending Pause here
  too, the exact same contract as `_drive_site`'s row above (see
  **Standalone-tool settings panels** under **The window** for the
  full Stop write-up).

**Stale-pause hygiene** (owner 2026-07-21): a job that finishes its
LAST item right as Pause was clicked — the for-loop just ends, so the
toggle is never revisited — would otherwise leave a phantom "paused"
button/state on an now-idle panel, and a bad carry-over would silently
pre-pause the NEXT run of that kind. Two guards close this: every
`_start_*` method clears a stale pause for its kind BEFORE spawning the
worker (a fresh Start never begins pre-paused) — `_start_site` its own
copy; every standalone tool's Start via `_launch_tool_worker`'s shared
tail (GUI rework Phase 13/14, `_start_tool_from_panel`'s own caller);
`_start_ai_check` (GUI rework Phase 15) its OWN copy of the identical
sweep, since it does not share `_launch_tool_worker` (see
**Standalone-tool settings panels**' own Phase 15 write-up for why) —
and the `__worker_done__`/`__tool_done__` dispatch handlers ALSO clear
it the moment a job finishes (so an idle/finished panel never shows a
stale "Resume"). `_stop_site` clears it too when actually stopping a
running site — belt-and-suspenders with the `should_stop` re-check
inside the wait, which already lets a PAUSED run stop promptly either
way; `_stop_tool` (GUI rework Phase 14, reused UNCHANGED for the AI
checker since Phase 15) does the exact same thing for any standalone
job.

**Stale-STOP hygiene** (GUI rework Phase 14, the SAME shape as the
pause guard above, one event earlier in the chain): `_launch_tool_
worker` ALSO clears the tool's stop event before spawning the worker
— mirrors `_start_site`'s own `self._stop_events[key].clear()` —
so a job Stopped once and then Started again never begins already
should_stop()-True (which would halt it before a single image runs).
`_start_ai_check` (GUI rework Phase 15) does the identical sweep by
hand, for the same reason it has its own stale-pause copy above. The
event is intentionally NOT cleared right after `_stop_tool` requests
the halt or right when `__tool_done__` consumes it (reading `is_set()`
to decide the "smart"/natural-finish branch) — only the NEXT Start's
own sweep clears it, same timing as the pause guard.

Caveat: `_drive_site`'s OUTER per-collection loop has no pause check
of its own — only `run_sheet`'s per-ITEM loop does. Pausing while the
LAST item of a collection is already generating lets that image
finish and the NEXT collection's `run_sheet` call begin (its own log
line prints) before the pause is honored at ITS first item boundary;
no generation happens in the gap, only a log line's timing looks a
beat early. Scoped out of this phase — the letter of "checked between
items" is satisfied, and the gap is cosmetic, never functional.

**GUI rework Phase 11** extends `_toggle_pause_job` at its tail (the
bookkeeping above is otherwise untouched): pausing a SITE while the
running view is up also reveals its settings panel — see **Running
view**'s Start/Pause/Stop table below. **GUI rework Phase 13/14/15**
widens the SAME tail to ALL FIVE standalone jobs (bg/crop, Phase 13;
upscale/aspect, Phase 14; the AI checker, Phase 15): pausing any of
them while the running view is up reveals ITS OWN `ToolSettingsPanel`
via the new `PainterGui._tool_panel_key(kind)` (identical to `kind` for
the four tools, `"image_checker"` for `"aicheck"` — see
**Standalone-tool settings panels**' own note on why the checker's
JOB_ORDER slot differs from its MENU_TILES id), and additionally keeps
the revealed panel's own Pause/Resume button label in sync
(`_tool_panels[panel_key].set_paused`) — no kind is left without a
panel to reveal any more; the check is a no-op only outside
`"running"`.

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md), [CDP Driver](painter/driver.md),
  [Run Loop](painter/runner.md), [Chrome Launcher](painter/chrome.md),
  [Postprocess](painter/postprocess.md), [Upscale](painter/upscale.md),
  [Change Aspect Ratio](painter/aspect.md), [Job Temp](painter/jobtemp.md),
  [AI Client & Flows](painter/ai.md),
  [Shared Filter Framework](painter/filters.md),
  [Settings](painter/settings.md), [Config](painter/config.md)

### Used by
- The owner (`python main.py` with no arguments).
