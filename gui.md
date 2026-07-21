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
functionality: Website GEN, New collection (AI), API Image GEN, AI
check, BG removal, Crop, Upscale, Aspect ratio), reading
`config.MENU_TILES` (pure data — id/label/description/icon stem/
`(day, night)` accent colour/`enabled`). `MainMenu._make_tile` is the
ONE tile factory (Rule #5, not 8 copy-pasted blocks): a rounded
`ctk.CTkFrame` card (`MENU_TILE_RADIUS` = 16, DESIGN.md's "cards,
panels" bracket) holding a centred icon + title (`ctk_font("title")`,
the SAME role the site panel titles use) + description, built from the
SAME primitives every other rounded surface in this file already uses
(`icon()` / `theme_pair` / `ctk_font`) — no new visual language. The
card's `fg_color` is the `theme_pair("dark")` elevated surface (both
themes already use this token for "raised" chrome — DocWindow's code
box, hover surfaces); its border is the tile's own accent,
`MENU_TILE_BORDER_PX` (2) at rest, `MENU_TILE_BORDER_HOVER_PX` (4) on
`<Enter>` — the ONE thing that changes on hover, deliberately: widening
the border needs no child widget to update in lockstep, unlike a
fill-colour hover would (every icon/title/description label is bound
to the SAME `<Button-1>`/`<Enter>`/`<Leave>` handlers as the card, so
the whole tile is one click target). A DISABLED tile (`enabled=False`)
renders with a muted `theme_pair("light")` border/title instead of its
accent and binds NO hover/click at all — visibly inert, not just
unwired; `api_image_gen` was the one tile shipped this way through
Phase 18 (a shown-but-inert placeholder), GUI rework Phase 19 flips it
to `enabled=True` and wires the real handler — EVERY tile is live
today, though the mechanism itself stays generic for any future
not-yet-wired functionality. Two tiles (website_gen/ai_sheet_gen) have
no natural `JOB_COLORS` entry (Website GEN spans BOTH gen sites, not
one job; ai_sheet_gen is a net-new AI feature with no dashboard job at
all) and carry their OWN accent tuples in `MENU_TILES` (indigo/yellow)
chosen to stay visually distinct from the `JOB_COLORS` hues in use; the
other six tiles (bg/crop/upscale/aspect/image_checker→`aicheck`/
api_image_gen→`api_image`, the last one GUI rework Phase 19) reuse
`JOB_COLORS`/`JOB_LABEL`/`JOB_LOGO` directly — a genuine reuse, not a
duplicate literal.

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
| `image_checker` / `bg` / `crop` / `upscale` / `aspect` / `api_image_gen` | `_open_tool_panel(tile_id)` — GUI rework Phase 13 (bg/crop), Phase 14 (upscale/aspect), Phase 15 (image_checker), Phase 19 (api_image_gen), see below |

ALL SIX standalone-job tiles (GUI rework Phase 19 adds `api_image_gen`
to the five Phase 15 completed) go straight to `_open_tool_panel` and
SKIP the `_go_view("main")` hop entirely — going through "main" first,
like every other tile, would reveal-then-immediately-hide the old
controls box behind a wasted extra fade, since `_open_tool_panel`
itself transitions straight to "running" (see **Standalone-tool
settings panels** under **The window**, and **Running view** below for
how it shares `_inline_kind`/`_apply_running_layout` with website_gen's
own toggle). `_open_tool_panel` is always called with the TILE id
(`"image_checker"`, not `"aicheck"`; `"api_image_gen"`, not
`"api_image"`) — `_tool_panels` itself is keyed the same way; see
**Standalone-tool settings panels**' own note on `PainterGui.
_tool_panel_key` for the one place that bridges back from a JOB_ORDER
kind. The old `UpscaleParamsDialog`/`AspectRatioDialog`
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
— sites + API Image GEN (GUI rework Phase 19: `"api_image"` tracks
through `self._running`, the SAME set chatgpt/gemini use, via
`_drive_site`) + tools + the AI checker, ONE set) is the single source
of truth every running-view method reads; `_active_tile_ids()` maps it
back through the NEW `config.TILE_JOB_KINDS` dict (which
`JOB_ORDER` kind(s) light up which `MENU_TILES` id — `website_gen` is
the one entry spanning two kinds, `ai_sheet_gen` maps to `()` since it
has no dashboard job of its own; `api_image_gen` used to be a SECOND
`()` entry through Phase 18, Phase 19 gives it `("api_image",)`).
**`_sync_running_state()`** is the ONE call site that reconciles both
after every change: called at the end of `_start_site`/
`_launch_tool_worker`/`_start_ai_check`/`_start_api_image` (right after
their worker thread starts) and from the `__worker_done__`/`__tool_done__`
dispatch branches (right after a kind is dropped from `_running`/
`_tool_workers`) — it recomputes `_next_view` and, whenever the result
IS `"running"`, refreshes `IconBar.set_active`. It is deliberately the
ONLY place that can ENTER `"running"`; leaving it only ever happens
through `_request_menu`.

**IconBar** reuses `MENU_TILES` exactly like `MainMenu` does (one
factory, not two copies): a `rounded_button` per tile (icon + label)
plus a "Menu" button — EVERY tile is enabled and live since GUI rework
Phase 19 (`api_image_gen` was the one placeholder styled disabled once
at construction and never touched again, through Phase 18; the
`if not tile.enabled:` branch that did that stays generic machinery for
any future not-yet-wired tile, simply unreached today).
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
- ALL SIX standalone-job tiles (`"bg"`/`"crop"`, GUI rework Phase 13;
  `"upscale"`/`"aspect"`, Phase 14; `"image_checker"`, Phase 15;
  `"api_image_gen"`, Phase 19) are ALSO a persistent inline surface —
  routed through the SAME generic fallthrough below (`_tile_handler
  ("bg")` resolves to `partial(self._open_tool_panel, "bg")`, etc. — no
  per-slot branch in either caller, the OLD `_start_tool` modal/the AI
  checker's own inline `askdirectory`+confirm these used to open are
  both deleted), toggling their OWN settings panel (see
  **Standalone-tool settings panels**/**API Image Generation** under
  **The window**) the exact same way;
- the ONE remaining tile with no persistent settings panel,
  `"ai_sheet_gen"`, still launches through the EXISTING dialog handler
  — `_tile_handler(tile_id)`, the SAME mapping `_select_tile` uses
  (extracted once, Rule #5, so the Main Menu and the running view never
  carry two copies of "what does this tile do"). It has no PERSISTENT
  settings panel of its own (a request → clarifying-questions → sheet
  flow has no "settings" to leave open — see `AiSheetDialog`), so
  "toggle the inline surface" for it means "open the SAME dialog the
  toolbar button already opens", which disturbs nothing else (always
  its own Toplevel) but is not literally a persistent panel the owner
  can leave open to inspect later.

**Start/Pause/Stop view semantics** (spec item 4), wired into the
EXISTING handlers — none forked:

| Action | What changes |
|---|---|
| **Start** (`_start_site`) | Unconditionally clears `_inline_kind` (Start hides the launching tool's OWN settings panel — website_gen's is shared by both sites, so EITHER starting hides it) then calls `_sync_running_state()` — auto-enters `"running"` on the first job. |
| **Start** (`_start_tool_from_panel`, GUI rework Phase 13/14, ALL FOUR tools; `_start_ai_check`, Phase 15, the AI checker; `_start_api_image`, Phase 19, API Image GEN — each a DIFFERENT method, same view-tail) | Clears `_inline_kind` AND explicitly re-calls `_apply_running_layout()` (unlike the row above: the panel can ONLY be visible while ALREADY `"running"`, so `_sync_running_state()`'s own view-transition check is always a no-op here). `_start_ai_check` used to have no panel to hide at all (Phase 11–14); Phase 15 gives it `ImageCheckerSettingsPanel`, Phase 19 gives API Image GEN `ApiImageGenPanel` the same way, so both tails now match `_start_tool_from_panel`'s exactly, just written by hand (see **Standalone-tool settings panels**/**API Image Generation** for why neither can share `_launch_tool_worker`). |
| **Pause** (`_toggle_pause_job`) | Unchanged pause/resume bookkeeping, PLUS: pausing `chatgpt`/`gemini`/`api_image` (GUI rework Phase 19) while `_view == "running"` sets `_inline_kind` — `"website_gen"` for the first two, `"api_image_gen"` for the third, via the SAME `PainterGui._tool_panel_key(kind)` bridge the standalone jobs already use below (api_image's `_tool_panels` entry differs from its JOB_ORDER slot, same asymmetry as the AI checker's); pausing ANY of the SIX standalone jobs (bg/crop/upscale/aspect, the AI checker since Phase 15, API Image GEN since Phase 19) sets `_inline_kind` to that SAME `_tool_panel_key(kind)` — identical to `kind` for the four tools, `"image_checker"` for `"aicheck"`, `"api_image_gen"` for `"api_image"` — either way `_apply_running_layout()` re-applies the layout ("Pause returns the settings panel for future tasks", spec item 4), and the revealed panel's OWN Pause/Resume label is kept in sync too (`_tool_panels[panel_key].set_paused`). Resuming never hides it again — only a fresh Start, a Stop (see below), or the owner's own icon click does. A no-op only outside `"running"` (already fully visible there) — no kind is left without a panel to reveal any more. |
| **Stop** (`_stop_site`) | UNCHANGED — signals the stop event; the worker exits on its own next poll and posts `__worker_done__`, which calls `_sync_running_state()` (recolours the icon; the design's "STOP … returns to the main menu" reads as "the Menu click that follows now succeeds", not an auto-jump — see below). Site Stop's own review-before-Close lifecycle is untouched by Phase 14/15. GUI rework Phase 19: API Image GEN's Stop ALSO wires straight to this SAME `_stop_site`, keyed `"api_image"` — its worker lives in `_workers`/`_running` (`_drive_site`'s own tracking), NOT `_tool_workers`, so the row below's `_stop_tool` (keyed off `_tool_workers`) would silently no-op on it; `_stop_site`'s quota-auto-restart branch is simply unreachable for `"api_image"` (its `TerminalState` always carries `retry_after_s=None`, so it never enters `_restart_jobs`) — the SAME generic "if key in self._running: …" branch chatgpt/gemini use is what actually fires. |
| **Stop** (`_stop_tool`, GUI rework Phase 14 — ALL FIVE standalone jobs since Phase 15, closing Phase 13's own flagged gap; NOT API Image GEN, see the row above) | Requests the halt (sets the job's stop event, wins over a pending Pause) — see **Standalone-tool settings panels**' own "Stop" write-up for the FULL "smart stop" sequence (worker finishes the in-flight image/vision call, then `__tool_done__`'s dispatch closes the panel + clears its JobTemp (a no-op for the AI checker — it has none) + calls `_request_menu()`). GUI rework Phase 15 wires the AI checker's OWN settings panel to this SAME method, UNCHANGED (`on_stop=PainterGui._stop_tool`, keyed `"aicheck"`) rather than a new near-duplicate — it never touched `_tool_panels` to begin with, so nothing about it was tool-specific. A DELIBERATE divergence from site Stop's review-then-Close lifecycle — a quick, disk-based (or read-only) job has nothing left worth reviewing once stopped. |
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
  **AI checker**
  (`checker_var`, GUI rework Phase 16, OFF by default — it spends a
  paced Gemini vision call PER SAVED IMAGE, an explicit opt-in cost
  unlike its free neighbours; see **Checker AI — parallel per-item
  check** below), the **New chat** mode,
  its own **Start / Pause / Stop** trio (owner 2026-07-21 adds
  **Pause** between them — a plain neutral `btn_pause` whose LABEL
  alone flips Pause ↔ Resume, wired to the shared `_toggle_pause_job`;
  see **Pause** below), and its own **⚙ Settings gear**
  (owner 2026-07-19). The gear reveals THIS agent's collapsible
  **fine-tune** area (`_finetune_box`, hidden by default): the **pause**
  Spinner range, the **action delay** Spinner range, the **Force
  Aspect Ratio (this site)** block (GUI rework Phase 8 — see below),
  the **Keep every pipeline step (uses more disk)** switch (see
  **Pipeline reorder + per-step backups**), the **Upscale
  gate (this site)** block, and — visible only while **AI checker** is
  on — the **Fixer AI (this site)** block (GUI rework Phase 20: an
  "Auto-fix flagged images" switch plus a via `api`/`website` dropdown;
  see **Fixer AI wiring** below). GUI rework Phase 6 simplified the gate from
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
- **Two-column-dense settings-panel layout** (owner 2026-07-21 layout
  fix, LAYOUT ONLY — Rule #16: the owner's screenshots showed every
  control hugging the LEFT half of a settings panel with the entire
  RIGHT half dead empty). `AgentPanel` is RESPONSIVE to the SAME
  visible-count state Phase 12's show/hide already tracks: its four
  content rows (Background/New-chat, Style, and the two switch rows)
  now live in one grid container (`self._content`) that
  `AgentPanel._apply_dense_columns`/`set_dense_columns` regrid between
  the narrow single-column stack (today's order — correct while BOTH
  sites share the row, each panel already only ~half width) and a
  two-column-dense fill — the switch rows LEFT, the dropdown rows RIGHT
  — used ONLY while a panel is the SOLE visible site (the panel then
  spans the whole controls width). `PainterGui._relayout_agents`
  computes `dense = len(cols) == 1` from `_visible_agent_columns`'s own
  result — the SAME KNOWN visible-count state that already decides
  panel/compact-cluster placement — and calls `panel.set_dense_columns
  (dense)` for every agent right there, so a Show/Hide toggle click, a
  settings restore and `set_run_state`'s own forced re-show all reach
  the new layout the SAME way, with NO `<Configure>` width probe
  (deterministic, not fragile). Start/Pause/Stop + the Settings gear
  stay in their own always-full-width bottom row, unchanged (buttons
  left, gear right already fills the row). The Settings-gear fine-tune
  block (`_build_finetune` — pause/action-delay ranges, Force Aspect
  Ratio, the Upscale gate) is DELIBERATELY untouched by this fix (out
  of the owner's stated scope) — it keeps working (expand/collapse,
  every field) but stays a single narrow column even in a wide panel;
  a real caveat, not a regression.

  The `ToolSettingsPanel` family (`BgSettingsPanel`/`CropSettingsPanel`/
  `UpscaleSettingsPanel`/`AspectSettingsPanel`/
  `ImageCheckerSettingsPanel`) and `ApiImageGenPanel` are ALWAYS
  full-width single panels (they never share a row with a sibling), so
  they use the two-column fill UNCONDITIONALLY, built once in
  `__init__` — no responsive toggle needed. `ToolSettingsPanel.__init__`
  grids a `body` frame with two child frames, `left`/`right`, both
  weight 1: LEFT holds the input picker (Folder…/Files… + the picked-
  path label) and the Filter editor narrowing WHICH images the run
  touches; RIGHT holds the subclass's own primary knobs (`_extra_box`
  — Upscale's min-side spinner, Aspect's target-ratio canvas), the
  Advanced collapsible (when `HAS_ADVANCED`) and the footer note — the
  owner's own illustrative split ("input picker + filter on one side,
  switches/extras on the other"). `ApiImageGenPanel` mirrors this:
  LEFT carries the AgentPanel-like quick controls (description,
  Background/Style, the post-save switches, the pause range, the
  "Check API access" gate row), RIGHT carries the two detailed editor
  blocks (the Force-Aspect canvas, the Upscale gate's FilterEditor).
  Every widget keeps its exact parent ROW frame, variable and command —
  only which FRAME hosts each row, and that row's `grid()`/`pack()`
  call, changed.

  Two new Rule #4 pixel constants, `DENSE_COL_GAP_PX` (16, the gap
  between the two columns — DESIGN.md's 8pt grid, the same 2-unit gap
  `MENU_TILE_GAP_PX` already uses) and `DENSE_COL_WRAP_PX` (320, a
  narrower wraplength for a caption/note now living in ONE column
  instead of the panel's old full width), live in **gui.py's own**
  Rule #4 block (beside `SETTINGS_GLYPH_*`) — NOT `painter/config.py`:
  this project's established split (see [Config](painter/config.md)'s
  own note on `FILTER_ASPECT_EXACT_TOL`) already assigns pure Tk
  pixel-geometry constants with no engine relevance to gui.py's own
  blocks, and painter/config.py only pure/engine-relevant or
  Tk-free-testable data — these two are neither. A real bug surfaced
  and fixed while building this: `ToolSettingsPanel`'s picked-folder-
  path label (`_picked_var`) had NO wraplength — harmless at the old
  full panel width, but an unwrapped long path in the new HALF-width
  LEFT column could force that column wider than its budget and
  squeeze RIGHT's content toward clipping (caught by a real screenshot
  with a long scratch temp path, not by pytest — geometry bugs at
  Tk's actual pixel level rarely are). Fixed by giving the label its
  OWN row (full LEFT-column width to wrap into) with
  `wraplength=DENSE_COL_WRAP_PX`. The same risk existed for every
  other unbounded caption now confined to a half-width column:
  `UpscaleSettingsPanel`'s/`ApiImageGenPanel`'s min-side captions had
  NO wraplength before (now `DENSE_COL_WRAP_PX`, newly added);
  `AspectSettingsPanel`'s/`ImageCheckerSettingsPanel`'s footer notes
  and `ApiImageGenPanel`'s description + gate-status labels already
  had one (the old full-width `JOB_PANEL_BANNER_WRAP_PX` — tightened
  to `DENSE_COL_WRAP_PX` for their new half-width column).

  **Verified:** `python -m pytest tests -q` stays green at 563 passed +
  1 skipped (unchanged — this is geometry only, no test asserted the
  old row/column shape). Real-window screenshots (Day theme, one Night
  confirmation; `settings.json` redirected to a scratch file) for: (1)
  Gemini hidden — the ChatGPT `AgentPanel` alone, now filling the width
  in two columns (directly comparable to the owner's own bug
  screenshot, `phase12_1_gemini_hidden.png`); (2) both sites shown —
  pixel-identical to before, confirming the narrow path is untouched;
  (3) all FIVE `ToolSettingsPanel` subclasses (BG with Advanced
  expanded, Crop with Advanced expanded, Upscale, Aspect, the AI
  checker — the sparsest RIGHT column, footer note only) plus (4)
  `ApiImageGenPanel`, all filling the width with no dead right half and
  no clipped/overflowing left; (5) the Settings-gear fine-tune block
  confirmed still fully functional (expand/collapse, every field) in a
  wide panel, visibly the one deliberately-untouched narrow column.
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
  `_tile_handler` fallthrough) — ONE shared toggle, not five (now six)
  copies (Rule #5). `_tool_panels` is keyed by MENU_TILES id throughout
  (tile id == slot for the four tools, so this is invisible for them);
  `ImageCheckerSettingsPanel`'s own `SLOT`/JOB_ORDER kind is
  `"aicheck"`, predating the tile system (owner 2026-07-20 vs. GUI
  rework Phase 10/11) and never renamed to match its `"image_checker"`
  tile; GUI rework Phase 19's `ApiImageGenPanel` has the SAME asymmetry
  — its own JOB_ORDER kind is `"api_image"`, its `_tool_panels` key
  `"api_image_gen"` (see **API Image Generation** below, right after
  this bullet, for why it does NOT subclass `ToolSettingsPanel` despite
  living in the same dict) — `PainterGui._tool_panel_key(kind)` (backed
  by `config.tile_for_kind`) is the ONE place that bridges a JOB_ORDER
  kind back to its `_tool_panels` key, used by `_toggle_pause_job` and
  the `__worker_done__`/`__tool_done__` dispatch branches (below);
  `_open_tool_panel`/`_select_tile`/`_click_icon_bar_tile` never needed
  it — they already operate purely in tile-id space. Each panel owns:
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
- **API Image Generation (GUI rework Phase 19)** — a THIRD generation
  job, `"api_image"`, alongside chatgpt/gemini: the SAME queued `.md`
  sheets Website GEN drives, generated through the PAID Gemini image
  REST API (`GEMINI_IMAGE_MODEL`, [AI Client & Flows](painter/ai.md)'s
  `generate_image`, Phase 18) instead of a browser tab. Two new
  pieces, plus a widened `_drive_site`:

  * **`ApiImageAdapter`** — a `SiteDriver`-shaped stand-in over
    `ai.generate_image`, proving the binding design doc's own
    "biggest risk-reducer": `run_sheet` only ever calls
    `submit_prompt`/`await_done`/`extract_image` on its driver (plus
    `attach`/`close` in `_drive_site` and `driver.site.name` for the
    report header — see [Run Loop](painter/runner.md)/
    [CDP Driver](painter/driver.md)), so a THIN adapter runs the WHOLE
    proven resume/report/postprocess/quota machinery UNTOUCHED. There
    is no browser tab: `attach()`/`close()`/`await_done()` are no-ops,
    `submit_prompt(prompt)` only REMEMBERS the text — the real call
    happens in `extract_image()` (mirrors the DOM driver's own
    submit-then-await-then-extract shape, so `run_sheet`'s "gen_s"
    SEND→image timing stays meaningful). A free-tier-exhausted 429
    (`ai.PaidFeatureRequired`) is remapped to `driver.TerminalState`
    with `retry_after_s=None` — PERMANENT (no wait ever fixes a zero
    quota, only billing), so unlike a website quota with a KNOWN reset
    time, this job never schedules `_handle_terminal`'s auto-restart
    timer (see **Threading**/**Pause** above for the guard: `_drive_
    site`'s own `if retry is not None:` check never fires for this
    job) — it just logs "site stopped" and posts `__worker_done__`,
    exactly like any other loud, non-retryable driver failure. Any
    OTHER `ai.AiError` (a malformed response, `NoKey`) is deliberately
    NOT remapped — it propagates as-is into `_drive_site`'s generic
    catch-all ("UNEXPECTED ERROR", Rule #1: never silently guessed
    into a friendlier shape it doesn't deserve). `new_chat` is NOT
    implemented on the adapter at all — `_start_api_image` always
    passes `new_chat="off"` (`config.NEW_CHAT_CHOICES`), so `_drive_
    site`/`run_sheet` never call it (there is no chat to open); a
    per-item SAFETY refusal (the DOM driver's `ItemRefused`, which
    powers "safer retry") also has no analogue here — a safety-blocked
    `ai.generate_image` answer raises a plain `AiError`, not something
    `run_sheet` recognizes as a per-item skip, so `_start_api_image`
    passes `safer_retry=False`/`continue_nudge=False` (both dead
    weight for this driver — a documented, deliberate scope boundary,
    not an oversight: a future phase could teach the adapter to raise
    `ItemRefused` on a safety block the same way, but Phase 19 does
    not).

  * **`_drive_site` GENERALIZED, not forked** — the ONE required
    change to the shared site worker: `driver` is now a PARAMETER
    (constructed by the CALLER — `_start_site`'s own `SiteDriver
    (SITES[key], timing, CDP_URL)` for chatgpt/gemini, `_start_api_
    image`'s `ApiImageAdapter` for `"api_image"`) instead of this
    method building a `SiteDriver` internally off `SITES[key]` —
    `"api_image"` is not a browser site and has no `SiteConfig`, so
    that internal construction line COULD NOT have widened in place.
    The method's own BODY never branches on which kind of object it
    was handed: it only ever calls `driver.attach()`, hands `driver`
    to `run_sheet` unchanged, and calls `driver.close()` in `finally`
    — exactly as before, just via a parameter. `_start_site` gained
    ONE new line (the `SiteDriver(...)` construction, moved up one
    level, otherwise byte-identical) and one new positional arg in its
    `_drive_site` thread-args tuple; chatgpt/gemini's own behaviour is
    UNCHANGED end to end (full suite green throughout — see
    **Verified** below).

  * **`ApiImageGenPanel(ttk.Frame)`** — menu-hosted exactly like the
    `ToolSettingsPanel` family (`_tool_panels["api_image_gen"]`,
    reached the SAME `_open_tool_panel`/`_click_icon_bar_tile` toggle
    every standalone job uses) but does NOT subclass
    `ToolSettingsPanel`: its input is the SAME queued Collections list
    Website GEN already drives (`PainterGui._sheets`), never a folder
    of already-existing images, so a "Folder…/Files…" picker would be
    actively WRONG here (root Rule #1 — never build UI that implies a
    capability the job doesn't have). It mirrors `AgentPanel` instead
    — a **Background**/**Style** dropdown pair feeding the SAME
    `config.prompt_suffix` machinery (`SITE_PROMPT_RULES["api_image"]`
    is an EMPTY tuple — no extra forced law yet, no live drift
    evidence for the API model the way there is for Gemini's WEBSITE
    reflections; add one if the owner observes the same pattern), the
    composable post-save switches (**BG removal**/**Crop**/**Force
    Aspect Ratio**/**Upscale**, run in the SAME fixed BG → Crop →
    Aspect → Upscale order via `_compose_post_save` — see **Pipeline
    reorder + per-step backups** below), a **pause** RANGE (no
    action-delay pair — that is `SiteDriver._hesitate()`'s DOM
    concept, meaningless here), and its own Start/Pause/Stop trio. ALL
    FOUR post-save switches default ON — unlike `AgentPanel`'s own
    defaults (BG/Crop/Upscale ON, Force Aspect OFF) — because the paid
    image model cannot render a REAL transparent background
    (UV/prompt.txt item 3: "ne moze TRANSPARENT pa mora BG removal i
    CROP sve redom" — "can't do TRANSPARENT so BG removal and Crop
    must run, in order"), so every generated image needs the FULL
    cleanup pipeline by default; the **Background** dropdown defaults
    to `"white"` (a background the model CAN render, for BG removal
    to key out), not a site's own `default_background` — this panel
    has no `SiteConfig` to read one from.
    `get_settings()`/`apply_settings(stored, conditions=...)` use the
    EXACT SAME shape `ToolSettingsPanel`'s own round-trip already has,
    so `PainterGui._apply_settings`'s existing generic `tool_panels`
    loop persists this panel with ZERO changes there — `conditions`
    carries the panel's ONE `FilterEditor` (the upscale gate, pre-
    seeded with the same aspect-range default `AgentPanel`'s own gate
    uses), the same role `UpscaleSettingsPanel`'s own top-level filter
    already plays under that key.

    **GATING** (owner decision, spec item 5) — the owner's key has
    ZERO free-tier quota for the paid image model TODAY
    (`ai.PaidFeatureRequired`, captured live 2026-07-21, see
    [AI Client & Flows](painter/ai.md)): a **Check API access** button
    makes ONE cheap REAL `ai.generate_image(AI_IMAGE_PROBE_PROMPT, …)`
    call on a background thread (its OWN small private
    `queue.Queue`+`self.after(AI_POLL_MS, …)` poll, mirroring
    `_AiDialog`'s established pattern — duplicated rather than shared
    via a mixin, since this panel's base class (`ttk.Frame`) differs
    from `_AiDialog`'s (`tk.Toplevel`); the codebase already accepts
    this trade-off elsewhere, e.g. `AgentPanel._toggle_settings`/
    `ToolSettingsPanel._toggle_advanced` are two independent near-
    identical collapse implementations for the same reason). A
    `PaidFeatureRequired` result sets `panel.access_gated = True`,
    shows `config.AI_IMAGE_GATE_MESSAGE` ("API image generation needs
    billing enabled — free tier limit is 0; use Website GEN for
    free"), and DISABLES the Start button (`style_action_button`, the
    SAME filled/disabled-outline language every other Start/Stop
    already uses) — a click on a disabled CTk button never fires its
    command, so this is a REAL block, not cosmetic. A clean probe
    result clears the gate and re-enables Start; any OTHER `AiError`
    (`NoKey`, a network failure) is shown but changes NEITHER state —
    inconclusive, never falsely claiming "OK" or wrongly gating. This
    is a CONVENIENCE, not the only guard: `_start_api_image` ALSO
    checks `panel.access_gated` itself before spawning a worker
    (defense in depth — the panel state and the button's disabled
    state could theoretically diverge, e.g. under test), and a run
    started without ever probing is caught the SAME way by
    `ApiImageAdapter.extract_image`'s own `PaidFeatureRequired` ->
    `TerminalState` mapping once the first item actually hits the
    paid endpoint — so the GATED state (Start disabled, the message
    shown) is the CORRECT, fully agent-verifiable shipped state on the
    owner's free key today, exactly as the binding design doc
    predicted.

  * **`_start_api_image`** — the job's OWN spawn method (mirrors
    `_start_site`'s validation shape, trimmed: no per-site pace/
    action-delay/"New chat" concept), NOT routed through `_start_
    tool_from_panel`/`_launch_tool_worker` (this job has no folder/
    `build_func` shape to share with the four tools — it drives the
    global sheet queue via `_drive_site`, not a picked folder of
    images via `_run_tool_job`). Validates the queue/output folder/
    filename-collision exactly like `_start_site`, then the panel's
    OWN gate (`access_gated`) and `_ensure_ai_key()` (same auto-open-
    the-wizard-on-`NoKey` gate `_new_collection_ai` already uses),
    then pace/upscale-gate/force-aspect validation (the SAME messages
    `_start_site` shows, "API Image GEN:" instead of the site's own
    name). No Select-images ticking for this job — `SelectWindow` is
    still per-SITE only (chatgpt/gemini columns); every sheet resumes
    by FILE EXISTENCE, sheet-advised items sit out, exactly like a
    site whose Select window the owner never opened (a documented
    scope boundary — a future phase could add a third column). Reuses
    `self._stop_events`/`self._pause_events`/`self._running`/
    `self._workers` — the SAME dicts chatgpt/gemini use, keyed
    `"api_image"` — and `_compose_post_save("api_image", panel=panel)`
    via that method's own new OPTIONAL `panel` parameter (`panel if
    panel is not None else self.agents[key]` — every existing chatgpt/
    gemini caller passes neither, so their behaviour is BYTE-
    IDENTICAL; only this ONE new caller passes `panel=` explicitly,
    since `ApiImageGenPanel` is not one of `self.agents`). Stop wires
    to `_stop_site` UNCHANGED (see the Start/Pause/Stop table under
    **Running view** for why NOT `_stop_tool`); the `__worker_done__`
    dispatch branch gained ONE guard (`key in self.agents` vs. the
    `_tool_panel_key` bridge — see **Threading** above) since this is
    the first `_drive_site`-driven key that is not one of
    `self.agents`.

  * **JOB_ORDER wiring** (`painter/config.py`, [Config](painter/config.md)
    has the full field list) — `"api_image"` threaded consistently
    through `JOB_ORDER`/`JOB_LABEL`/`JOB_LOGO` (reuses the Gemini
    logo)/`JOB_COLORS` (its own orange pair, the SAME tuple
    `MENU_TILES`'s `api_image_gen` tile reads back — one hue, not two
    literals) — but NOT `JOB_TOOL_KINDS` (it is not a `ToolPanel`) nor
    `JOB_METRIC` (its dashboard panel is a plain `DashPanel`, same as
    chatgpt/gemini — no per-image % column); `GRID_COLS_BY_COUNT`
    gained an `8: 3` entry (one more empty cell in the existing 3×3
    shape 7 already had); `config.dest_for` needed NO change at all —
    it already injects ANY `site_key` string generically
    (`dest_for("assets/badge/rune/Glory.png", "api_image")` ==
    `"badge/api_image/rune/Glory.png"`), so API-generated images land
    in the SAME assets-mirroring tree a finished collection copies
    into DOMY's `assets/` from, just under an `api_image/` folder
    instead of `chatgpt/`/`gemini/`. `MENU_TILES`'s `api_image_gen`
    tile flips `enabled=False` → `True` (the description drops
    "— coming soon") and `TILE_JOB_KINDS["api_image_gen"]` widens from
    `()` to `("api_image",)` — see **Main Menu**/**Running view**
    above for how `MainMenu`/`IconBar` needed ZERO code changes for
    either flip (both were already fully generic over `tile.enabled`/
    `TILE_JOB_KINDS`'s data).

  **NOT wired this phase** (documented scope boundaries, not gaps):
  the parallel per-item Checker AI (`_maybe_spawn_checker` reads
  `self.agents.get(key)` — `None` for `"api_image"`, a clean early
  return, never a crash) and the AI checker's flagged-image re-send
  (`ai.drop_and_site_for` checks `parts[1] in SITES` — `"api_image"`
  is deliberately NOT added to `SITES`, which is a browser-DOM
  concept; adding it there would risk `_open_chrome`/`AgentPanel`
  code that assumes every `SITES` key has a real tab) — a future
  phase could extend either, following `_maybe_spawn_checker`'s own
  "reads `self.agents`, not `JOB_ORDER`" gate as the one thing to
  widen.

  **Verified:** full suite green (563 passed + 1 skipped, up from 540
  — `tests/test_gui_api_image.py`, 18 new tests, PLUS the existing
  suite's small ripple where Phase 10/11's OWN tests hard-coded
  "api_image_gen is the one disabled placeholder", now updated to
  "every tile is live" — `test_config.py`/`test_gui_running_view.py`).
  `ApiImageAdapter`'s three methods proven headless against a
  monkeypatched `ai.generate_image` (`submit_prompt` stores,
  `extract_image` returns the mocked bytes, `PaidFeatureRequired` maps
  to `TerminalState` with `retry_after_s=None`, any OTHER `AiError`
  propagates unmapped); `_drive_site` proven BOTH with a bare fake
  driver (never branches on type — calls `attach()`/`close()`,
  threads the object into `run_sheet` unchanged) AND end-to-end with
  the REAL `ApiImageAdapter` (a real `Sheet` through the real,
  unmodified `run_sheet`, saving the mocked PNG bytes at
  `dest_for(drop, "api_image")`, `driver.site.name` reaching the
  report header) and its PaidFeatureRequired path (job stops, NO
  `__terminal__` event since `retry_after_s` is always None,
  `__worker_done__` still always posts); `_compose_post_save("api_
  image", panel=…)` proven against a REAL `ApiImageGenPanel` — same
  "REMOVE BG, CROP, ASPECT, UPSCALE" ordered action-string contract
  test_gui_pipeline.py already proves for chatgpt/gemini's
  `self.agents[key]` path; the panel's defaults/settings-round-trip/
  gating (`_probe_access` with `threading.Thread` replaced by an
  immediate synchronous call — the SAME "mock the class/thread, never
  wait on real timing" convention this whole suite already applies —
  disables Start on a mocked `PaidFeatureRequired`, re-enables it on a
  mocked success, leaves it untouched on an unrelated `AiError`); and
  `_start_api_image`'s own gating refusal (a duck-typed `FakeGui`,
  `messagebox.showerror` monkeypatched, never a real blocking dialog).
  Real-window screenshot (Day theme, settings.json redirected to a
  scratch file so the owner's real one is never touched, `ai.
  generate_image` MOCKED to raise `PaidFeatureRequired` for a
  deterministic probe result — this IS the correct real state on the
  owner's free key today) confirmed the API Image GEN panel opened
  from its Menu tile, GATED: Start disabled (outline, not filled), the
  `AI_IMAGE_GATE_MESSAGE` shown beside the **Check API access**
  button, every other control (background/style/the four pipeline
  switches, all four defaulting ON/BG/Crop's switches lit/the Force
  Aspect Ratio canvas/the Upscale gate) rendering normally.
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
  upscale-gate filter and all SIX standalone job panels', GUI rework
  Phase 19 adding `ApiImageGenPanel`'s own upscale-gate filter to the
  list), `agents.<site>` (below) and `tool_panels.<tile-id>` — ALL SIX
  standalone jobs' own settings (`{tile_id: panel.get_settings()}`,
  keyed by MENU_TILES id — `"image_checker"` for the AI checker, GUI
  rework Phase 15, its own JOB_ORDER slot `"aicheck"`; `"api_image_gen"`
  for API Image GEN, Phase 19, its own slot `"api_image"`, same
  asymmetry — see **Standalone-tool settings panels**/**API Image
  Generation** for each panel's own field shape: BG/Crop's safety/
  margin/ink-alpha overrides + `advanced_collapsed`; Upscale's
  `up_minside`; Aspect's `ratio`; the AI checker has none of its own;
  `ApiImageGenPanel`'s `background`/`style`/`bg_removal`/`crop`/
  `force_aspect`(+`_w`/`_h`)/`upscale`/`up_minside`/`report`/
  `keep_all_steps`/`pause_min`/`pause_max`, its `conditions` key
  carrying the SAME upscale-gate filter role `UpscaleSettingsPanel`'s
  own top-level filter already plays — reused UNCHANGED by
  `_apply_settings`'s existing generic `tool_panels` loop, no new
  branch there; every panel's `conditions`). GUI rework Phase 14 RETIRED the OLD
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
"is this the right image?" doubt: the viewer opens the image via
`ai_check_image_file`, the same `ai.flag_key` round-trip reversed).
Both `ai_check_doc_md` and `ai_check_image_file` are MODULE-LEVEL
functions (Rule #5) — `ai_check_image_file` was promoted from this
panel's own private `_file_for` in GUI rework Phase 16 so `DashPanel`'s
own report viewer (below) can resolve the identical round-trip; neither
panel keeps a private copy. Two panel actions:

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

### Checker AI — parallel per-item check (GUI rework Phase 16)
The owner's UV/prompt.txt item 1 ("dok generise sledecu sliku
paralelno ona koja je generisana cek jer provjeri ... ako je ukljucen
samo cek jer onda samo dobije pored slike i riport"): while a SITE
generates its NEXT image, the image it just saved gets checked in the
background — no separate job slot, no separate Start button, just a
per-agent `checker_var` switch (see the two AGENT PANELS above) that
makes `DashPanel`'s own rows sprout a check-status column.

**Zero `runner.py` changes** — the binding design doc's key finding:
`run_sheet` already emits `item_progress` (with the `drop_path`) the
INSTANT a saved image's post-save pipeline finishes, well before it,
so `PainterGui._dispatch`'s existing `__event__` branch just calls a
new `_maybe_spawn_checker(slot, event)` right after `panel.handle(event)`,
for EVERY `item_progress` (not `item_done` — deliberately: `item_progress`
fires BEFORE the "our time" pause, so starting the check there
overlaps BOTH the remaining pause AND the whole of the next item's
generation, not just the second half of it).

`_maybe_spawn_checker`:
1. No-ops unless `slot` is a SITE (`self.agents.get(slot)`, so a
   tool/aicheck event is silently ignored) with THAT site's
   `checker_var` ON — read LIVE on every call, not captured once at
   Start, so flipping the switch mid-run takes effect from the next
   saved image.
2. Applies `{"type": "item_checking", "drop_path": ...}` to the site's
   `DashPanel` SYNCHRONOUSLY (already on the main thread, same call
   stack as `panel.handle` right above it in `_dispatch`) — the row's
   Check column reads "checking…" the instant this method returns, no
   queue round-trip needed for that part.
3. Starts a bare `threading.Thread(target=self._run_checker_one, args=(slot,
   drop_path, src, out_base), daemon=True)` — fire-and-forget, no
   `_stop_events`/`_pause_events` entry (a one-shot vision call, not a
   loop with a between-items boundary to poll; Stop/Pause never wait on
   it, and a trailing checker thread from a job the owner already
   Stopped/Closed just posts into a `self.panels.get()` that may by
   then be gone — the SAME defensive `.get()` guard every other late
   event already relies on).

`_run_checker_one` (the thread body) calls `ai.check_one_image(src,
out_base, AI_CHECK_INSTRUCTIONS, log=...)` — the SAME pure driver
`_run_ai_check_job` already uses for the standalone batch checker
(Rule #5, zero new engine code) — and posts exactly one
`{"type": "item_checked", "drop_path": ..., "kind": ..., "defects": ...,
"raw": ..., "rel": ..., "time": ...}` back onto the ordinary
`self._q`/`__event__` channel, routed to the SAME site's `DashPanel`
exactly like any other event. `ai.check_one_image` already turns a
per-image `AiError` (including `NoKey` — a subclass) into a
`kind="error"` result instead of raising, so the row shows `error`
plainly and the run is never touched — the SAME loud-but-never-fatal
contract `AiCheckPanel`'s own batch job already relies on. An outer
`except Exception` around the whole call is the extra safety net for
anything ELSE that could escape (a file vanishing mid-race, a flag-file
write hitting a full disk) — Rule #1: a checker thread can never die
silently, and it can never reach back into the generation run it is
checking.

`DashPanel`'s Collections tree gains an eighth column, **Check**
(`DASH_CHECK_COL_PX` — gui.py's own Rule #4 geometry constant, beside
the `AI_CHECK_*` block it sits next to), blank for a site that never had the
checker on: `item_checking` sets "checking…"; `item_checked` sets
"OK" / `"flagged {n}"` / "error" and tints the row with the SAME
`ai_check_tag(kind)` module-level helper `AiCheckPanel`'s own rows use
(`TOOL_CHANGED_TAG` for flagged — POPS, needs attention; `TOOL_SKIP_TAG`
for OK/error — muted, the wording alone tells them apart). Results land
in `self._check_results: dict[drop_path, event]`, scoped like
`_node_info` (the WHOLE run, cleared only by `reset()`) rather than
like `_child_ids` (reset every `sheet_start` — see **Per-step restore
viewer** above for the identical existing trade-off `refresh_image_row`
already accepts): a checker result for an OLDER, already-rolled-over
collection stays reachable even though its row can no longer be found
by `drop_path` for a LIVE update. A new **Check…** button sits beside
**Show**/**Steps…** in the Collections sub-header — a THIRD separate
surface, never overloaded onto the tree's own double-click —
`DashPanel._show_check` resolves the focused row's `_check_results`
entry and opens the identical `DocWindow`/`ai_check_doc_md`/
`ai_check_image_file` report `AiCheckPanel`'s own double-click shows
(Rule #5: one report renderer, two launch surfaces — proven by
`tests/test_gui_checker.py`'s own side-by-side comparison of both
panels' captured `DocWindow` arguments for the identical checked
image).

**`AiCheckPanel`'s own standalone batch flow is fully independent** —
it never calls into `_maybe_spawn_checker`/`_run_checker_one`, and the
two paths only ever share the SAME append-only `<out>/_state/
ai_flags.json` (`ai.record_flag`/`clear_flag`'s existing load-merge-save
contract, already safe for two independent writers). The owner can run
a Website GEN job with its checker ON and a standalone AI-check batch
at the same time; both calls funnel through `ai.py`'s ONE
`_last_call_t` pacing gate (see **Threading** below), so under load the
parallel checker can trail generation by more than one image — an
expected UX characteristic (Risk #7 in the binding design doc), not a
bug.

### Fixer AI wiring (GUI rework Phase 20)
The owner's UV/prompt.txt item 1 ("dok generise sledecu sliku paralelno
ona koja je generisana cek jer provjeri i ako ustanovi gresku salje
fikseru da ispravi i to u situaciji ako su oba ukljucena") and item 2
("Checker double click na tu stavku daje FULL REPORT ... i gore buttone
za IMAGE FIX i WEBSITE fix ako je procenio gresku — u oba slucaja kreira
PROMPT koji salje uz sliku"). Two INDEPENDENT surfaces share the same
prompt-builder and JobTemp convention: an **AUTO-DISPATCH** half wired
off the parallel checker's own result, and a **MANUAL** half in the
checker report viewer — plus the pre-existing **Send flagged to
generator** stays untouched as a third option. `painter.ai.
build_fix_prompt(defects, raw) -> str` is the ONE shared prompt-builder
(pure, Rule #5): named defects become a bulleted "fix ONLY these"
instruction (`config.AI_FIX_PROMPT_WITH_DEFECTS`), an empty list a
graceful "use your own judgement" fallback
(`AI_FIX_PROMPT_NO_DEFECTS` — never blank, since `edit_image`/
`submit_fix` always need SOME text), and the checker's VERBATIM raw
response — when given — is appended after, as extra grounding context
the parsed bullets can lose (`AI_FIX_PROMPT_RAW_SUFFIX`).

**Auto-dispatch** — `AgentPanel` gains `fixer_var` (default OFF) and
`fixer_mode_var` (`config.FIXER_MODE_API`/`_WEBSITE`, default `api`),
visible ONLY while `checker_var` is on (`_apply_fixer_visibility`, a
`checker_var` trace — same "hidden until its own gate switch is on"
composition `_apply_upscale_gate_visibility` already uses). On every
`item_checked` the parallel checker posts, `PainterGui._dispatch` now
ALSO calls `_maybe_spawn_fixer(key, event)` (beside the EXISTING
`_maybe_spawn_checker` call on `item_progress` — a sibling branch, not
a rewrite). The pure, Tk-free `_fixer_decision(agent, event) -> str`
(headlessly tested — the whole branch table needs no Tk) reads
`fixer_var`/`fixer_mode_var` LIVE, exactly like `_maybe_spawn_checker`
reads `checker_var` live, so a mid-run toggle takes effect from the
NEXT checked image:

- `"none"` — the switch is off, or the image was not flagged.
- `"api"` — `_run_fixer_api` spawns a background `threading.Thread`
  RIGHT NOW: a plain `ai.edit_image` REST call, so it genuinely
  overlaps the site's OWN next-image generation on the SAME browser
  tab — the intended parallel flow. It backs the pre-fix file up via
  THIS site's live `JobTemp` (`PainterGui._job_temps[key]`) under
  `step="fixer"` (`_backup_before_fix` — best-effort: a slot with no
  live JobTemp, e.g. its dashboard panel was already Closed this
  session, skips the backup LOUDLY rather than silently, root Rule #1),
  overwrites the image, then posts a new `item_fixed` event
  `DashPanel.handle` applies — it re-reads the row's resolution/size
  off disk (`refresh_image_row`, the SAME helper the Phase 9 restore
  viewer's own callback uses) and appends "→ fixed" to the Check
  column. A gated (`ai.PaidFeatureRequired`) or failed
  (`ai.AiError`) call is LOUD in the Log and NEVER FATAL — it never
  touches the run this image came from, the same convention
  `_run_checker_one` already established.
- `"website_queue"` — **the documented choice, read this before
  changing it**: the site's browser tab is BUSY generating the NEXT
  image the instant `item_checked` fires (the checker's background
  thread reports well before the run finishes), so
  `_queue_website_fix` NEVER drives `driver.submit_fix` from this
  path — doing so would collide with the in-flight
  `submit_prompt`/`await_done` (one tab, one operation). Instead it
  folds the flagged item into `AiCheckPanel`'s OWN `_flagged`/`_raw`
  bucket via its EXISTING `handle({"type": "item_flagged", ...})` —
  the IDENTICAL append-only state the standalone batch checker already
  fills — and reveals that panel on the dashboard grid (`DashGrid.add`,
  idempotent) so the queued item is IMMEDIATELY VISIBLE as a real row,
  never a silent internal list. The owner's EXISTING **Send flagged to
  generator** button (`AiCheckPanel._do_resend` ->
  `PainterGui._resend_flagged`) is the ONE send path — reused
  VERBATIM, never duplicated — whenever they choose to click it;
  typically once the site is idle again, since `_resend_flagged`'s own
  `_start_site` call already refuses a site that is still
  `self._running`, so a click can never collide with the still-running
  generation even if it happens immediately. (A future "auto-drain the
  moment the tab frees up" was considered and DELIBERATELY not built —
  auto-restarting a site right after the owner's own explicit Stop
  would be surprising; the queued row plus the existing button keeps
  the owner in control of WHEN a website fix actually drives the
  browser.)

**Manual buttons** — the checker's report viewer (`DocWindow`, opened
by BOTH `DashPanel._show_check` and `AiCheckPanel._on_activate` — Rule
#5, one call site: `PainterGui._build_fix_workers(rel, out_base,
defects, raw, jobtemp_slot=None)`) gains **IMAGE FIX** and **WEBSITE
FIX** buttons, shown ONLY when the report actually carries defects
(both callers pass `on_image_fix=None, on_website_fix=None` otherwise —
`DocWindow` then builds no fix-action row at all). `DashPanel` already
knows its own site (`self.slot_key`, passed as `jobtemp_slot`);
`AiCheckPanel` — the standalone checker, with no site of its own —
passes `None`, and `_build_fix_workers` resolves BOTH the site (for
WEBSITE FIX) and the JobTemp slot (for the pre-fix backup) via
`ai.drop_and_site_for(rel)`, the SAME `dest_for` reverse `ai.
plan_resend`'s own re-send already uses. `image_fix_worker` is ALWAYS
offered (`ai.edit_image` needs no site concept — ANY checked image,
regardless of provenance, can be IMAGE-FIXED);
`website_fix_worker` is `None` when no `SITES` entry resolves (an API
Image GEN output — no browser tab at all — or a standalone-checked
image from outside any queued generation).

Each button's zero-arg worker (`PainterGui._run_image_fix` /
`_run_website_fix`) runs on a background thread `DocWindow._run_fix`
spawns (mirrors `ApiImageGenPanel._probe_access`'s own private-queue +
`self.after(AI_POLL_MS, …)` poll shape exactly — Rule #5, the SAME
"background network/browser call never blocks the Tk event loop"
pattern), and returns a `("ok"/"gated"/"error", message)` pair.
`_run_website_fix` — an OWNER-TRIGGERED one-off automation, driving a
FRESH `SiteDriver` (attach -> `submit_fix` -> `await_done` ->
`extract_image` -> `close`), never the running site's own worker
thread — refuses with a transient `"error"` (not a permanent
`"gated"`) while THIS site is `self._running`: the SAME one-tab
collision the auto-dispatch's `_queue_website_fix` avoids, just
surfaced as a clear message instead of silently queuing (a manual
click is the owner's OWN choice of timing, so a retry-able refusal is
enough). Both workers back the pre-fix file up via `_backup_before_fix`
(`step="fixer"`, best-effort) before overwriting — restorable in the
Phase 9 `StepRestoreWindow` filmstrip exactly like a pipeline stage
(`JOBTEMP_STEP_NAMES`/`JOBTEMP_STEP_LABEL` already reserved `"fixer"` /
"Fixer AI" since Phase 7/9 — no config change needed here).

The pure `_fix_result_ui(which, result) -> (status_text, enable_image,
enable_website)` (Tk-free, headlessly tested — no test in this suite
ever constructs a real `tk.Toplevel`, the same "pure helpers get
pytest, real Tk/UI wiring gets a screenshot" split every phase
follows) sits behind `DocWindow._apply_fix_result`, which only ever
APPLIES the mapping to the real buttons: `"ok"` leaves BOTH disabled
(the report is now STALE — a fresh Check… is the honest next step,
never a second blind fix off the same old defects); `"gated"` — a
PERMANENT condition (no billing / no selectors) — leaves the button
that fired disabled but RE-ENABLES the other (a gate on one path
should not block trying the other); `"error"` re-enables both
(transient, retry-able — e.g. "the site is currently generating").
Both buttons disable together the instant either is clicked (never a
double-fix race against the same file).

**Non-regression:** `AiCheckPanel`'s **Send flagged to generator** /
**Clear flags** buttons, the checker report viewer's EXISTING content
(the defects list, the verbatim raw response, the embedded image), the
parallel checker itself (Phase 16), Safer retry / Continue nudge, and
the generation run's own pipeline are all untouched — every Fixer
addition is a NEW, additive surface.

**Verified (0.0.09x):** full suite green (605 passed + 1 skipped, up
from 563) — `painter.ai.build_fix_prompt` (defects -> bulleted
instruction, empty defects -> the non-blank fallback, raw appended/
omitted); `AgentPanel.fixer_var`/`fixer_mode_var` (defaults,
`_PERSIST`/settings round-trip, visibility tied to `checker_var` via
`winfo_manager()` — the shared `tk_root` fixture is withdrawn, so
`winfo_ismapped()` cannot be used); `_fixer_decision`'s full branch
table; `_maybe_spawn_fixer`/`_run_fixer_api`/`_queue_website_fix` run
for REAL through a duck-typed `_FakeGuiForFixer` (mocked
`ai.edit_image`, a REAL `JobTemp` proving the `step="fixer"` backup,
a bounded `Queue.get`/`_wait_for_event` wait for the background
thread's `item_fixed`, and — the core physical-constraint proof —
website mode monkeypatches BOTH `ai.edit_image` and
`driver.SiteDriver` to raise if EVER touched); `_build_fix_workers`'s
site resolution (explicit `jobtemp_slot` vs the `drop_and_site_for`
fallback, `"api_image"` correctly getting no website worker);
`_run_image_fix`/`_run_website_fix`'s gate/success paths (a duck-typed
fake `SiteDriver` proving the attach -> submit_fix -> await_done ->
extract_image -> close call SEQUENCE, and that it is ALWAYS closed,
even on `FixNotConfigured`); `_fix_result_ui`'s mapping; and
`DashPanel`'s new `item_fixed` row handling. Real-window screenshots
(Day theme, `settings.json` redirected to a scratch file, every
ai.py/driver.py call MOCKED — no live quota, no live Chrome):
(1) an isolated `AgentPanel` with AI checker ON and Settings expanded,
showing the new Fixer AI switches; (2) the checker report `DocWindow`
with WEBSITE FIX driven to its GATED/disabled state (the
`FixNotConfigured`-shaped message) while IMAGE FIX stays available;
(3) a `StepRestoreWindow` filmstrip — driven through the REAL
`_run_fixer_api` with a mocked `ai.edit_image` — showing Original ->
Fixer AI -> Current as three distinct stages.

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
checker since Phase 15, plus API Image GEN since Phase 19 (`_stop_
events["api_image"]`, reused by `_stop_site` — see **API Image
Generation** under **The window**), `_stop_tool` — and, owner
2026-07-21, per-KIND pause events, one per `JOB_ORDER` entry, EIGHT
total since Phase 19); each site creates its own
Playwright instance and `SiteDriver` (sync Playwright is
per-thread) and walks the theme queue sequentially — GUI rework Phase
19's API Image GEN worker walks the SAME `_drive_site`/`run_sheet`
loop (`_start_api_image`, its OWN spawn method — not `_start_site`,
which is chatgpt/gemini-only end to end) but with an `ApiImageAdapter`
in place of a `SiteDriver`: no Playwright, no per-thread browser
instance, just a paced `ai.generate_image` REST call per item. The
four TOOLS
add up to four MORE daemon workers (`_run_tool_job`, GUI rework Phase
14 threads a real should_stop into its loop, mirroring `run_sheet`'s
own — see **Pause** below and **Standalone-tool settings panels**
under **The window**), one per kind
(one job per kind — a second click is refused), and the AI CHECKER a
seventh (`_run_ai_check_job`, same `_tool_workers` bookkeeping — GUI
rework Phase 15 threads its OWN real should_stop into its loop the
identical way, closing what was this section's own flagged gap), so up
to EIGHT jobs run
CONCURRENTLY (three generation jobs — chatgpt/gemini/api_image — plus
the four tools plus the AI checker); each tool worker only backs up + processes files under
its own picked folder and its own `JobTemp` subdir (disjoint writes;
the checker writes only the flag file under `<out>/_state/`) — and,
since GUI rework Phase 8, each SITE worker's post-save pipeline backs
up under ITS OWN `JobTemp` subdir the same way (`self._job_temps`,
keyed by site instead of tool kind — see **Pipeline reorder +
per-step backups**). The AI
DIALOGS (`AiKeyWizard`'s Test, `AiSheetDialog`'s two calls) run their
API work on short-lived daemon threads too, feeding a per-dialog queue
polled with `after` (`_AiDialog` — the workers never touch a widget).
The Checker AI (GUI rework Phase 16) adds a DIFFERENT shape again: not
one thread per JOB, but one short-lived daemon thread PER SAVED IMAGE
on a site whose `checker_var` is on (`_maybe_spawn_checker`/
`_run_checker_one`) — UNBOUNDED in count and untracked by
`_stop_events`/`_workers` (a one-shot vision call has no loop to poll a
should_stop on; see **Checker AI — parallel per-item check** above for
why that is fine). It posts its own `item_checked` back onto the SAME
`self._q` the site's OWN worker also feeds, so the two interleave
freely on one queue exactly like any other pair of concurrent workers
here.
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
the worker bookkeeping — GUI rework Phase 19: `key` is no longer always
one of `self.agents` (`"api_image"` isn't — no `SiteConfig`, no
`AgentPanel`), so this branch now GUARDS the run-state update: `key in
self.agents` takes the EXACT old `self.agents[key].set_run_state(...)`
path unchanged, else it resolves `_tool_panel_key(key)` and calls
`set_run_state(running=False)` on THAT `_tool_panels` entry instead
(`ApiImageGenPanel` for `"api_image"`, with no `pending_restart`
concept — see below) — and `('__tool_done__', slot)` does the SAME on
a natural finish — but (GUI rework Phase 14, widened to `"aicheck"` by
Phase 15) instead CLOSES the panel outright (`_close_panel` — same as
a manual Close) and calls `_request_menu()` when this slot's
should_stop event is set (a Stop-triggered finish, see
**Standalone-tool settings panels**' own "Stop" write-up); a quota
`TerminalState` posts its `retry_after_s`
the same way and the main thread schedules the auto-restart via
`root.after` (the panel keeps its countdown, no CLOSE, until the
restart or a Stop) — for `"api_image"` this never actually fires:
`ApiImageAdapter.extract_image` always raises `TerminalState` with
`retry_after_s=None` (the free-tier-zero condition is PERMANENT, no
wait ever fixes it), so `_drive_site`'s own `if retry is not None:`
guard never queues `__terminal__` for this job — it just stops and
posts `__worker_done__` like any other loud failure (see **API Image
Generation** under **The window**).

## Pause (owner 2026-07-21)

A per-JOB Pause toggle — ALL EIGHT `JOB_ORDER` kinds (GUI rework Phase
19 adds `"api_image"`), not just the two gen sites — separate from the
pre-existing pace RANGE that happens to share the word "pause"
(`Timing.pause_min_s`/`pause_max_s`, the random wait between prompts;
see **The window** above). `self._pause_events: dict[str,
threading.Event]` (one per kind) and `self._paused: set[str]` (which
kinds are currently paused) live on `PainterGui`, seeded at `__init__`.
**`_toggle_pause_job(kind)`** is the ONE handler wired to every kind's
`btn_pause` — `AgentPanel`'s own (chatgpt/gemini), `ToolPanel`'s/
`AiCheckPanel`'s own (bg/crop/upscale/aspect/aicheck), and (GUI rework
Phase 19) `ApiImageGenPanel`'s own (api_image — this kind's dashboard
panel, `self.panels["api_image"]`, is a plain `DashPanel` like
chatgpt/gemini's, with NO pause button of its own — same as sites, the
button lives on the SETTINGS panel instead): it flips the kind's
`Event` + membership in `_paused`, then calls `set_paused(is_paused)`
on the AgentPanel (if this kind has one, `kind in self.agents` — False
for api_image, which is NOT one of `self.agents`) AND on
`self.panels[kind]` (every kind has a dashboard panel) AND, via
`_tool_panel_key(kind)`, on that kind's own `_tool_panels` entry when
it has one (all six standalone jobs, including `"api_image_gen"`) —
so the button label and the Dashboard tab's state line always agree,
and logs a one-line `[kind] paused`/`resumed`. None of this method's
OWN code needed to change for Phase 19 — every branch was already
generic over "a kind that happens not to be in `self.agents`"; only
the DATA (`JOB_ORDER`, `TILE_JOB_KINDS`) grew a new entry.

The actual wait lives in [Run Loop](painter/runner.md)'s
`wait_while_paused(should_pause, should_stop, log, emit)` — a public
function, not a `run_sheet`-only helper, so THREE call sites share the
exact same poll-wait (`config.PAUSE_POLL_INTERVAL_S`, no busy spin):

- `_drive_site` passes `should_pause=pause_event.is_set` into
  `run_sheet` alongside the existing `should_stop=stop_event.is_set` —
  checked between sheet items; a Stop always wins over a pending pause
  (`should_stop` is re-checked on every poll tick inside the wait). GUI
  rework Phase 19: this row now ALSO covers `"api_image"` — `_drive_site`
  was WIDENED, not forked, to accept an `ApiImageAdapter` in place of a
  `SiteDriver` (see **API Image Generation** under **The window**), so
  the SAME `run_sheet` call, the SAME pause/stop wiring, runs unchanged.
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
`_start_ai_check` (GUI rework Phase 15) and `_start_api_image` (GUI
rework Phase 19) each their OWN copy of the identical sweep, since
neither shares `_launch_tool_worker` (see **Standalone-tool settings
panels**/**API Image Generation** for why) — and the
`__worker_done__`/`__tool_done__` dispatch handlers ALSO clear it the
moment a job finishes (so an idle/finished panel never shows a stale
"Resume"). `_stop_site` clears it too when actually stopping a running
site OR (Phase 19) API Image GEN — belt-and-suspenders with the
`should_stop` re-check inside the wait, which already lets a PAUSED
run stop promptly either way; `_stop_tool` (GUI rework Phase 14,
reused UNCHANGED for the AI checker since Phase 15) does the exact
same thing for the four tools + the AI checker (NOT API Image GEN,
which goes through `_stop_site` instead — see the Start/Pause/Stop
table under **Running view**).

**Stale-STOP hygiene** (GUI rework Phase 14, the SAME shape as the
pause guard above, one event earlier in the chain): `_launch_tool_
worker` ALSO clears the tool's stop event before spawning the worker
— mirrors `_start_site`'s own `self._stop_events[key].clear()` —
so a job Stopped once and then Started again never begins already
should_stop()-True (which would halt it before a single image runs).
`_start_ai_check` (GUI rework Phase 15) and `_start_api_image` (GUI
rework Phase 19 — mirroring `_start_site`'s OWN copy, since it reuses
the SAME `_stop_events`/`_running` dicts, not `_launch_tool_worker`'s)
each do the identical sweep by hand, for the same reason they have
their own stale-pause copy above. The event is intentionally NOT
cleared right after `_stop_tool`/`_stop_site` requests the halt or
right when `__tool_done__`/`__worker_done__` consumes it (reading
`is_set()` to decide the "smart"/natural-finish branch) — only the
NEXT Start's own sweep clears it, same timing as the pause guard.

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
view**'s Start/Pause/Stop table below. **GUI rework Phase 13/14/15/19**
widens the SAME tail to ALL SIX standalone jobs (bg/crop, Phase 13;
upscale/aspect, Phase 14; the AI checker, Phase 15; API Image GEN,
Phase 19): pausing any of them while the running view is up reveals
ITS OWN settings panel via the `PainterGui._tool_panel_key(kind)`
bridge (identical to `kind` for the four tools, `"image_checker"` for
`"aicheck"`, `"api_image_gen"` for `"api_image"` — see
**Standalone-tool settings panels**' own note on why the checker's and
API Image GEN's JOB_ORDER slots differ from their MENU_TILES ids), and
additionally keeps the revealed panel's own Pause/Resume button label
in sync (`_tool_panels[panel_key].set_paused`) — no kind is left
without a panel to reveal any more; the check is a no-op only outside
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
