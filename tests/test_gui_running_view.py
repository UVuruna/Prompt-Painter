"""Running view: icon bar + Start/Pause/Stop view semantics (GUI rework
Phase 11).

Two halves, matching gui.py's own "pure helpers get pytest, real Tk/UI
wiring gets a screenshot" split (___tests.md):

* ``gui._next_view`` is the pure, Tk-free view-transition decision
  behind the running view — every rule from the binding design doc
  (auto-enter "running" on the first job start; "running" persists
  through every Stop, all the way down to zero active jobs; "menu" is
  reachable again ONLY on an explicit Menu click once nothing is
  active any more) tested directly, no GUI construction at all.
* the ``PainterGui`` methods that consume it (``_active_kinds``/
  ``_active_tile_ids``/``_sync_running_state``/``_apply_running_layout``/
  ``_request_menu``/``_click_icon_bar_tile``/``_tile_handler``/
  ``_open_tool_panel``) run for REAL through a small duck-typed
  ``FakeGui`` — the SAME convention test_gui_pipeline.py's own
  ``FakeGui`` uses for ``_compose_post_save`` (never a full
  ``PainterGui``: a heavy ``__init__``, and every other phase's tests
  avoid it too). ``IconBar`` itself is a real, cheap-to-construct
  widget: button count/ids and ``set_active``'s filled/outline
  recolouring (GUI rework Phase 19 wires up the LAST tile that used to
  start permanently disabled, "api_image_gen" — every tile is now a
  real, clickable button; see test_gui_api_image.py for its OWN
  gating, which disables Start on ITS panel instead, live).

GUI rework Phase 13 adds ``_tool_panels`` (BG/Crop's own persistent
``ToolSettingsPanel`` — a REAL ``ttk.Frame`` stand-in here,
``_RecordingToolPanel``, so ``_apply_running_layout``'s pack/
pack_forget is exercised for real, same as ``_controls_box``/
``_compact_box`` already are) and ``_open_tool_panel`` (the shared
toggle both ``_select_tile`` and ``_click_icon_bar_tile`` now route
bg/crop through instead of the old ``_start_tool`` modal). GUI rework
Phase 14 widens ``_tool_panels`` to all FOUR standalone tools
(upscale/aspect join bg/crop, both old modal dialogs deleted) — same
mechanism, no new branch in either caller, so the upscale-specific
tests below just prove the dict now covers it too. GUI rework Phase
15 adds the AI checker as a FIFTH entry, keyed by its MENU_TILES id
"image_checker" — its own JOB_ORDER slot is "aicheck" (it predates the
tile system, GUI rework Phase 11), so ``_tool_panel_key`` (aliased
onto ``FakeGui`` alongside the other unbound methods below) is the one
new bridge ``_toggle_pause_job`` needs; ``_select_tile``/
``_click_icon_bar_tile``/``_open_tool_panel`` need NONE — they already
operate purely in tile-id space.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

import gui
from painter.config import JOB_ORDER, MENU_TILES, SITES


# ---------------------------------------------------------------------
# gui._next_view — pure, no Tk
# ---------------------------------------------------------------------


@pytest.mark.parametrize("current", ["menu", "main"])
def test_next_view_auto_enters_running_on_first_job_start(current):
    assert gui._next_view(current, active_count=1) == "running"


def test_next_view_stays_running_while_any_job_active():
    for count in (1, 2, 6, 7):
        assert gui._next_view("running", active_count=count) == "running"


def test_next_view_stop_of_the_last_job_alone_never_auto_navigates():
    """Reaching zero active jobs WITHOUT a Menu click stays put — only
    an explicit Menu click (menu_requested=True) may leave "running"."""
    assert gui._next_view("running", active_count=0) == "running"


def test_next_view_menu_click_returns_to_menu_only_once_idle():
    assert (
        gui._next_view("running", active_count=0, menu_requested=True)
        == "menu"
    )


def test_next_view_menu_click_refused_while_anything_is_active():
    for count in (1, 3):
        assert (
            gui._next_view(
                "running", active_count=count, menu_requested=True,
            )
            == "running"
        )


def test_next_view_idle_menu_and_main_are_left_alone():
    assert gui._next_view("menu", active_count=0) == "menu"
    assert gui._next_view("main", active_count=0) == "main"


def test_next_view_menu_click_from_main_when_idle_still_works():
    """The pre-Phase-11 pinned top-strip Menu button's own path — never
    blocked from "main" since a real job always forces "running" first
    (active_count is always 0 while genuinely on "main")."""
    assert (
        gui._next_view("main", active_count=0, menu_requested=True) == "menu"
    )


# ---------------------------------------------------------------------
# gui.menu_min_size — pure, no Tk (owner 2026-08-03, UI rework tačka 1:
# the FIXED 4x2 Main Menu grid; the window's computed minsize replaces
# the retired responsive column reflow — the Tk-facing half,
# BuildMixin._apply_min_size, is proven by a real-window screenshot,
# matching gui.py's "pure helpers get pytest" convention)
# ---------------------------------------------------------------------


def test_menu_min_size_width_covers_the_full_fixed_grid_plus_chrome():
    """8 tiles at MENU_TILE_COLS=4 → the minimum width is exactly four
    per-column footprints plus the caller-measured chrome."""
    w, _h = gui.menu_min_size(8, chrome_w_px=64, chrome_h_px=0)
    assert w == gui.MENU_TILE_COLS * gui.MENU_TILE_CELL_MIN_PX + 64


def test_menu_min_size_height_covers_every_row_plus_chrome():
    """8 tiles at 4 columns = 2 rows of (tile height + gap), plus the
    measured chrome height."""
    _w, h = gui.menu_min_size(8, chrome_w_px=0, chrome_h_px=120)
    assert h == 2 * (gui.MENU_TILE_H + gui.MENU_TILE_GAP_PX) + 120


def test_menu_min_size_a_ninth_tile_would_grow_a_third_row():
    """The math follows the tile count — a future 9th functionality
    raises the height floor by exactly one row."""
    _w, h8 = gui.menu_min_size(8, 0, 0)
    _w, h9 = gui.menu_min_size(9, 0, 0)
    assert h9 - h8 == gui.MENU_TILE_H + gui.MENU_TILE_GAP_PX


def test_menu_min_size_never_below_one_column_and_row():
    """tile_count 0 still returns a sane one-cell floor, never 0x0."""
    w, h = gui.menu_min_size(0, 0, 0)
    assert w == gui.MENU_TILE_CELL_MIN_PX
    assert h == gui.MENU_TILE_H + gui.MENU_TILE_GAP_PX


def test_menu_min_size_agrees_with_the_grids_own_minsize_floor():
    """menu_min_size's per-column footprint and MainMenu's fixed-grid
    column ``minsize`` MUST use the SAME constant — a stricter grid
    floor than the minsize math assumed would still clip the grid's
    right edge at the computed minimum width."""
    assert gui.MENU_TILE_CELL_MIN_PX > gui.MENU_TILE_W + gui.MENU_TILE_GAP_PX


# ---------------------------------------------------------------------
# PainterGui running-view methods — via a duck-typed FakeGui
# ---------------------------------------------------------------------


@pytest.fixture
def root(tk_root):
    return tk_root


class FakeGui:
    """Duck-typed ``PainterGui`` stand-in — just enough attribute
    surface for the UNBOUND running-view methods to run for real
    (never a full ``PainterGui`` window; see this module's docstring).

    ``_sync_running_state``/``_click_icon_bar_tile``/``_request_menu``
    call ``self._active_kinds()``/``self._active_tile_ids()``/
    ``self._tile_handler(...)`` INTERNALLY — a plain unbound call
    (``gui.PainterGui._sync_running_state(fake)``) still resolves
    those through normal attribute lookup on ``self``, so the SAME
    real, unmodified functions are aliased in here as class attributes
    rather than reimplemented (Rule #5 — one body, not two)."""

    _active_kinds = gui.PainterGui._active_kinds
    _active_tile_ids = gui.PainterGui._active_tile_ids
    _tile_handler = gui.PainterGui._tile_handler
    _apply_running_layout = gui.PainterGui._apply_running_layout
    # the ONE packer _apply_running_layout delegates its whole layout to
    # (owner 2026-08-03) — aliased like every other real body here, so
    # these tests still exercise the PRODUCTION packing, not a copy
    _pack_main_stack = gui.PainterGui._pack_main_stack
    _toggle_pause_job = gui.PainterGui._toggle_pause_job
    _tool_panel_key = gui.PainterGui._tool_panel_key
    _open_tool_panel = gui.PainterGui._open_tool_panel
    _select_tile = gui.PainterGui._select_tile

    def __init__(self, root):
        self._running: set[str] = set()
        self._tool_workers: dict[str, object] = {}
        self._view = "menu"
        self._inline_kind: str | None = None
        # _pack_main_stack's other two inputs: the setup screen's
        # controls/compact choice, and whether any job has ever run (the
        # dashboard's own visibility gate — no dashboard before the
        # first job, owner 2026-07-29)
        self._collapsed = False
        self._dashgrid = SimpleNamespace(active=lambda: [])
        self.status_var = tk.StringVar(value="idle")
        self.view_log: list[str] = []  # every _go_view request, in order

        self._controls_box = ttk.Frame(root)
        self._compact_box = ttk.Frame(root)
        # ALL SEVEN persistent settings-panel stand-ins (bg/crop, GUI
        # rework Phase 13; upscale/aspect, Phase 14; the AI checker,
        # Phase 15; API Image GEN, Phase 19; New Collection (AI),
        # faza 4 — its popup retired) — real ttk.Frames so
        # _apply_running_layout's pack/pack_forget is exercised for real
        # (see this module's own docstring). Keyed by MENU_TILES id,
        # exactly like the real PainterGui._tool_panels — "image_checker"
        # NOT "aicheck", "api_image_gen" NOT "api_image" (their own
        # JOB_ORDER slots): _tool_panel_key is the bridge tested below.
        self._tool_panels: dict[str, _RecordingToolPanel] = {
            "bg": _RecordingToolPanel(root), "crop": _RecordingToolPanel(root),
            "upscale": _RecordingToolPanel(root),
            "aspect": _RecordingToolPanel(root),
            "image_checker": _RecordingToolPanel(root),
            "api_image_gen": _RecordingToolPanel(root),
            "ai_sheet_gen": _RecordingToolPanel(root),
        }
        self.notebook = ttk.Notebook(root)
        self.notebook.add(ttk.Frame(self.notebook), text="Dashboard")
        self.notebook.add(ttk.Frame(self.notebook), text="Log")
        self.notebook.pack(fill="both", expand=True)
        self._scroll = SimpleNamespace(refresh=lambda: None)
        self._icon_bar = gui.IconBar(
            root, on_select=lambda *_a: None, on_menu=lambda: None,
        )

        self.new_collection_calls = 0

        # _toggle_pause_job's own attribute surface (Start/Pause/Stop
        # view semantics, spec item 4) — plain recorders, never a real
        # AgentPanel/ToolPanel
        self._paused: set[str] = set()
        self._pause_events = {kind: threading.Event() for kind in JOB_ORDER}
        self.agents = {
            kind: _RecordingPanel() for kind in ("chatgpt", "gemini")
        }
        self.panels = {kind: _RecordingPanel() for kind in JOB_ORDER}
        self.log_lines: list[str] = []

    # the ONLY methods _sync_running_state/_request_menu/_toggle_pause_job
    # call on self besides plain attribute reads — recorded, never a
    # real swap/panel/log sink
    def _go_view(self, view: str) -> None:
        self.view_log.append(view)
        self._view = view

    def _new_collection_ai(self) -> None:
        self.new_collection_calls += 1

    def _log(self, msg: str) -> None:
        self.log_lines.append(msg)


class _RecordingPanel:
    """Stands in for an AgentPanel/ToolPanel/DashPanel entry in
    ``FakeGui.agents``/``FakeGui.panels`` — ``_toggle_pause_job`` only
    ever calls ``set_paused`` on these."""

    def __init__(self):
        self.paused_calls: list[bool] = []

    def set_paused(self, is_paused: bool) -> None:
        self.paused_calls.append(is_paused)


class _RecordingToolPanel(ttk.Frame):
    """Stands in for a BgSettingsPanel/CropSettingsPanel entry in
    ``FakeGui._tool_panels`` (GUI rework Phase 13) — a REAL
    ``ttk.Frame`` (so ``_apply_running_layout``'s pack/pack_forget is
    exercised for real) plus a recorded ``set_paused``, the only other
    thing ``_toggle_pause_job`` calls on it."""

    def __init__(self, master):
        super().__init__(master)
        self.paused_calls: list[bool] = []

    def set_paused(self, is_paused: bool) -> None:
        self.paused_calls.append(is_paused)


def test_active_kinds_unions_running_and_tool_workers(root):
    fake = FakeGui(root)
    fake._running = {"chatgpt"}
    fake._tool_workers = {"bg": object(), "aicheck": object()}
    assert gui.PainterGui._active_kinds(fake) == {"chatgpt", "bg", "aicheck"}


def test_active_tile_ids_maps_kinds_back_to_their_tile(root):
    fake = FakeGui(root)
    fake._running = {"gemini"}
    fake._tool_workers = {"crop": object()}
    assert gui.PainterGui._active_tile_ids(fake) == {"website_gen", "crop"}


def test_sync_running_state_enters_running_on_first_job(root):
    fake = FakeGui(root)
    fake._running = {"chatgpt"}
    gui.PainterGui._sync_running_state(fake)
    assert fake._view == "running"
    assert fake.view_log == ["running"]
    assert fake._icon_bar._buttons["website_gen"].cget("border_width") == 0


def test_sync_running_state_never_leaves_running_on_its_own(root):
    """A job finishing (active_count back to 0) does NOT navigate — only
    _request_menu (an explicit Menu click) ever does."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = set()
    fake._tool_workers = {}
    gui.PainterGui._sync_running_state(fake)
    assert fake._view == "running"
    assert fake.view_log == []  # _go_view never even called


def test_sync_running_state_recolours_the_icon_bar_while_running(root):
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    gui.PainterGui._sync_running_state(fake)
    assert fake._icon_bar._buttons["website_gen"].cget("border_width") == 0
    assert fake._icon_bar._buttons["bg"].cget("border_width") == 1  # idle


def test_apply_running_layout_default_is_dashboard_only(root):
    """Owner 2026-07-29 ("posle Starta samo DASHBOARD"): right after
    any Start (``_inline_kind is None``) the running view shows the
    icon strip and the dashboard — NO settings surface of any kind."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._apply_running_layout(fake)
    assert fake._icon_bar.winfo_manager() == "pack"
    assert fake._controls_box.winfo_manager() == ""
    assert fake._compact_box.winfo_manager() == ""


def test_apply_running_layout_controls_box_only_for_website_gen(root):
    """``_controls_box`` packs ONLY while the owner explicitly opened
    it (``_inline_kind == "website_gen"`` — the icon click); ``None``
    (post-Start) shows the dashboard alone (owner 2026-07-29)."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._inline_kind = "website_gen"
    gui.PainterGui._apply_running_layout(fake)
    assert fake._controls_box.winfo_manager() == "pack"

    fake._inline_kind = None
    gui.PainterGui._apply_running_layout(fake)
    assert fake._controls_box.winfo_manager() == ""


def test_apply_running_layout_shows_a_tool_panel_only_while_its_inline(root):
    """GUI rework Phase 13: _inline_kind also keys into _tool_panels
    (BG/Crop) — AT MOST ONE inline surface (website_gen's controls_box
    OR one tool panel) shows at a time."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._inline_kind = "bg"
    gui.PainterGui._apply_running_layout(fake)
    assert fake._tool_panels["bg"].winfo_manager() == "pack"
    assert fake._tool_panels["crop"].winfo_manager() == ""
    assert fake._controls_box.winfo_manager() == ""

    fake._inline_kind = "crop"
    gui.PainterGui._apply_running_layout(fake)
    assert fake._tool_panels["bg"].winfo_manager() == ""
    assert fake._tool_panels["crop"].winfo_manager() == "pack"

    fake._inline_kind = None
    gui.PainterGui._apply_running_layout(fake)
    assert fake._tool_panels["bg"].winfo_manager() == ""
    assert fake._tool_panels["crop"].winfo_manager() == ""


def test_apply_running_layout_hides_a_stale_compact_box(root):
    """Phase 10's collapsed strip is meaningless during "running" — the
    IconBar owns this whole region instead, even if the app was
    collapsed right before the job that entered "running" started."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._compact_box.pack(fill="x")  # simulate a stale pre-running pack
    gui.PainterGui._apply_running_layout(fake)
    assert fake._compact_box.winfo_manager() == ""


def test_request_menu_navigates_when_idle(root):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._request_menu(fake)
    assert fake.view_log == ["menu"]


def test_request_menu_refused_while_a_job_is_active_and_sets_a_status_hint(
    root,
):
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    gui.PainterGui._request_menu(fake)
    assert fake.view_log == []
    assert "Stop" in fake.status_var.get()


def test_request_menu_from_main_when_idle_still_works(root):
    """The pre-Phase-11 pinned Menu button's own path."""
    fake = FakeGui(root)
    fake._view = "main"
    gui.PainterGui._request_menu(fake)
    assert fake.view_log == ["menu"]


def test_click_icon_bar_tile_on_a_running_tool_just_focuses_the_dashboard(
    root,
):
    """A STANDALONE TOOL tile (never website_gen — see the dead-end
    regression test below) whose kind is currently active just focuses
    the Dashboard tab, undisturbed — that job's own panel stays exactly
    as hidden as before; this rule is unchanged by the 2026-07-21
    workflow fix, only website_gen's own handling changed."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._tool_workers = {"bg": object()}
    fake.notebook.select(1)  # currently on "Log"
    gui.PainterGui._click_icon_bar_tile(fake, "bg")
    assert fake.notebook.index("current") == 0  # jumped to Dashboard
    assert fake._inline_kind is None  # untouched — not a settings toggle


def test_click_icon_bar_tile_website_gen_toggles_controls_box(root):
    """Owner 2026-07-29: the Website GEN icon is THE way to bring the
    site settings back over the dashboard — first click shows them,
    second click dismisses them back to the dashboard alone."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")
    assert fake._inline_kind == "website_gen"
    assert fake._controls_box.winfo_manager() == "pack"

    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")
    assert fake._inline_kind is None
    assert fake._controls_box.winfo_manager() == ""  # dashboard only


def test_click_icon_bar_tile_website_gen_never_dead_ends_while_a_site_runs(
    root,
):
    """THE regression test for the diagnosed workflow bug: clicking
    "website_gen" while a site is ACTIVE used to fall through to the
    generic "already active -> just focus the Dashboard" branch (since
    website_gen's own TILE_JOB_KINDS were themselves active), leaving
    ``_inline_kind`` untouched — a dead end if some OTHER inline surface
    (a tool's own settings panel) happened to be showing at the time,
    since nothing ever brought ``_controls_box`` back. website_gen is
    now checked FIRST, unconditionally, so it ALWAYS supersedes
    whatever tool panel was open and restores the site controls —
    including the OTHER site's own Start button."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt", "gemini"}
    fake._inline_kind = "bg"  # some tool panel happens to be open
    gui.PainterGui._apply_running_layout(fake)
    assert fake._tool_panels["bg"].winfo_manager() == "pack"
    assert fake._controls_box.winfo_manager() == ""  # superseded

    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")

    assert fake._inline_kind == "website_gen"
    assert fake._controls_box.winfo_manager() == "pack"  # back — no dead end
    assert fake._tool_panels["bg"].winfo_manager() == ""  # superseded back


def test_click_icon_bar_tile_image_checker_not_running_opens_its_inline_panel(
    root,
):
    """The AI checker now ALSO has a persistent settings panel (GUI
    rework Phase 15, same family as bg/crop/upscale/aspect) — clicking
    while not running toggles it inline (via _tile_handler's
    _open_tool_panel entry), undisturbed by some OTHER job that keeps
    running. Keyed by its MENU_TILES id "image_checker" in
    _tool_panels, NOT its "aicheck" JOB_ORDER slot — _click_icon_bar_
    tile/_open_tool_panel/_inline_kind all operate in tile-id space,
    same as every other tile."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    gui.PainterGui._click_icon_bar_tile(fake, "image_checker")
    assert fake._inline_kind == "image_checker"
    assert fake._tool_panels["image_checker"].winfo_manager() == "pack"

    gui.PainterGui._click_icon_bar_tile(fake, "image_checker")  # click again
    assert fake._inline_kind is None
    assert fake._tool_panels["image_checker"].winfo_manager() == ""


def test_click_icon_bar_tile_bg_not_running_opens_its_inline_panel(root):
    """bg/crop DO have a persistent settings panel now (GUI rework
    Phase 13) — clicking while not running toggles it inline (via
    _tile_handler's _open_tool_panel entry), exactly like website_gen's
    own toggle, instead of the old _start_tool modal."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    gui.PainterGui._click_icon_bar_tile(fake, "bg")
    assert fake._inline_kind == "bg"
    assert fake._tool_panels["bg"].winfo_manager() == "pack"

    gui.PainterGui._click_icon_bar_tile(fake, "bg")  # click again -> hides
    assert fake._inline_kind is None
    assert fake._tool_panels["bg"].winfo_manager() == ""


def test_click_icon_bar_tile_upscale_not_running_opens_its_inline_panel(
    root,
):
    """GUI rework Phase 14: upscale/aspect now behave exactly like
    bg/crop above — the old UpscaleParamsDialog/AspectRatioDialog
    modal is gone, _tile_handler routes both through _open_tool_panel
    the same generic way (no per-slot branch in either caller)."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    gui.PainterGui._click_icon_bar_tile(fake, "upscale")
    assert fake._inline_kind == "upscale"
    assert fake._tool_panels["upscale"].winfo_manager() == "pack"

    gui.PainterGui._click_icon_bar_tile(fake, "aspect")  # a DIFFERENT slot
    assert fake._inline_kind == "aspect"
    assert fake._tool_panels["upscale"].winfo_manager() == ""
    assert fake._tool_panels["aspect"].winfo_manager() == "pack"


def test_click_icon_bar_tile_ai_sheet_gen_toggles_its_panel(root):
    """Faza 4 (owner UV tačka 4): the AiSheetDialog popup is retired —
    ai_sheet_gen now toggles its OWN persistent panel exactly like
    every other tile (the wizard SheetGenPanel)."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._click_icon_bar_tile(fake, "ai_sheet_gen")
    assert fake._inline_kind == "ai_sheet_gen"
    assert fake._tool_panels["ai_sheet_gen"].winfo_manager() == "pack"
    assert fake.new_collection_calls == 0  # no dialog launch anywhere


def test_tile_handler_website_gen_has_no_single_handler(root):
    """website_gen is the ONE tile with no single handler — the owner
    drives the now-visible queue + per-site Start buttons instead (see
    _select_tile's own docstring). Every other tile, including
    "api_image_gen" since GUI rework Phase 19, resolves to a real
    callable — see test_tile_handler_covers_every_menu_tile_id_without_
    raising below and test_select_tile_bg_from_menu_skips_main_and_
    opens_the_panel_in_running's own sibling coverage."""
    fake = FakeGui(root)
    assert gui.PainterGui._tile_handler(fake, "website_gen") is None


def test_tile_handler_api_image_gen_opens_its_own_panel(root):
    """GUI rework Phase 19: api_image_gen now resolves to the SAME
    _open_tool_panel toggle bg/crop/upscale/aspect/image_checker
    already use — no more disabled placeholder. Proven by calling the
    returned handler and observing the SAME toggle those tiles'
    own tests check (Rule #5 — no partial-internals introspection)."""
    fake = FakeGui(root)
    fake._view = "running"
    handler = gui.PainterGui._tile_handler(fake, "api_image_gen")
    assert handler is not None
    handler()
    assert fake._inline_kind == "api_image_gen"
    assert fake._tool_panels["api_image_gen"].winfo_manager() == "pack"


def test_tile_handler_covers_every_menu_tile_id_without_raising(root):
    fake = FakeGui(root)
    for tile in MENU_TILES:
        gui.PainterGui._tile_handler(fake, tile.id)  # must not KeyError


# ---------------------------------------------------------------------
# _select_tile — the Main Menu path (GUI rework Phase 13's bg/crop
# shortcut around the usual "main" hop)
# ---------------------------------------------------------------------


def test_select_tile_bg_from_menu_skips_main_and_opens_the_panel_in_running(
    root,
):
    """Every OTHER tile goes menu -> "main" -> its handler; bg/crop
    skip straight to "running" with their panel shown, avoiding a
    reveal-then-immediately-hide of the old controls box."""
    fake = FakeGui(root)
    fake._view = "menu"
    gui.PainterGui._select_tile(fake, "bg")
    assert fake.view_log == ["running"]  # never visited "main"
    assert fake._view == "running"
    assert fake._inline_kind == "bg"
    assert fake._tool_panels["bg"].winfo_manager() == "pack"


def test_select_tile_website_gen_still_goes_through_main_unmodified(root):
    fake = FakeGui(root)
    fake._view = "menu"
    gui.PainterGui._select_tile(fake, "website_gen")
    assert fake.view_log == ["main"]
    assert fake._inline_kind is None  # controls_box shows via "main" itself


def test_select_tile_upscale_skips_main_and_opens_the_panel_in_running(
    root,
):
    """GUI rework Phase 14: upscale (like aspect) now takes the SAME
    bg/crop shortcut straight to "running" with its own panel shown —
    the old modal dialog's "main" hop is gone."""
    fake = FakeGui(root)
    fake._view = "menu"
    gui.PainterGui._select_tile(fake, "upscale")
    assert fake.view_log == ["running"]  # never visited "main"
    assert fake._view == "running"
    assert fake._inline_kind == "upscale"
    assert fake._tool_panels["upscale"].winfo_manager() == "pack"


def test_select_tile_image_checker_skips_main_and_opens_the_panel_in_running(
    root,
):
    """GUI rework Phase 15: the AI checker takes the SAME bg/crop/
    upscale/aspect shortcut straight to "running" with its own panel
    shown — the old askdirectory+confirm launch is gone. _inline_kind
    lands on the MENU_TILES id "image_checker", not the "aicheck"
    JOB_ORDER slot _select_tile was called with — _tool_panels itself
    is keyed by tile id, exactly like every sibling tool."""
    fake = FakeGui(root)
    fake._view = "menu"
    gui.PainterGui._select_tile(fake, "image_checker")
    assert fake.view_log == ["running"]  # never visited "main"
    assert fake._view == "running"
    assert fake._inline_kind == "image_checker"
    assert fake._tool_panels["image_checker"].winfo_manager() == "pack"


# ---------------------------------------------------------------------
# _toggle_pause_job — Pause "returns the settings panel" (spec item 4)
# ---------------------------------------------------------------------


def test_toggle_pause_job_on_a_site_reveals_the_website_gen_panel_while_running(
    root,
):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._toggle_pause_job(fake, "chatgpt")
    assert "chatgpt" in fake._paused
    assert fake._pause_events["chatgpt"].is_set()
    assert fake.agents["chatgpt"].paused_calls == [True]
    assert fake.panels["chatgpt"].paused_calls == [True]
    assert fake._inline_kind == "website_gen"
    assert fake._controls_box.winfo_manager() == "pack"


def test_toggle_pause_job_on_the_ai_checker_reveals_its_own_inline_panel(
    root,
):
    """The AI checker now ALSO has a persistent settings panel (GUI
    rework Phase 15) — pausing "aicheck" reveals it inline exactly
    like bg/crop/upscale/aspect below, EXCEPT _inline_kind lands on
    its MENU_TILES id "image_checker" (via _tool_panel_key), not the
    "aicheck" kind _toggle_pause_job was called with — the one job
    kind whose tile id differs from its slot."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._toggle_pause_job(fake, "aicheck")
    assert "aicheck" in fake._paused
    assert fake.panels["aicheck"].paused_calls == [True]
    assert "aicheck" not in fake.agents  # tools have no AgentPanel entry
    assert fake._tool_panels["image_checker"].paused_calls == [True]
    assert fake._inline_kind == "image_checker"
    assert fake._tool_panels["image_checker"].winfo_manager() == "pack"

    gui.PainterGui._toggle_pause_job(fake, "aicheck")  # resume
    assert fake._tool_panels["image_checker"].paused_calls == [True, False]
    assert fake._inline_kind == "image_checker"  # still there


def test_toggle_pause_job_on_bg_reveals_its_own_inline_panel(root):
    """bg/crop DO have a persistent settings panel now (GUI rework
    Phase 13) — pausing one reveals it inline, mirroring website_gen's
    own reveal, and keeps the panel's OWN Pause/Resume label in sync."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._toggle_pause_job(fake, "bg")
    assert "bg" in fake._paused
    assert fake.panels["bg"].paused_calls == [True]
    assert fake._tool_panels["bg"].paused_calls == [True]
    assert fake._inline_kind == "bg"
    assert fake._tool_panels["bg"].winfo_manager() == "pack"

    gui.PainterGui._toggle_pause_job(fake, "bg")  # resume
    assert fake._tool_panels["bg"].paused_calls == [True, False]
    assert fake._inline_kind == "bg"  # still there — only Start hides it
    assert fake._tool_panels["bg"].winfo_manager() == "pack"


def test_toggle_pause_job_on_upscale_reveals_its_own_inline_panel(root):
    """GUI rework Phase 14: upscale/aspect now behave exactly like
    bg/crop above — the SAME generic ``kind in self._tool_panels``
    check in ``_toggle_pause_job``, no per-slot branch."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._toggle_pause_job(fake, "upscale")
    assert "upscale" in fake._paused
    assert fake.panels["upscale"].paused_calls == [True]
    assert fake._tool_panels["upscale"].paused_calls == [True]
    assert fake._inline_kind == "upscale"
    assert fake._tool_panels["upscale"].winfo_manager() == "pack"


def test_toggle_pause_job_outside_running_view_never_touches_the_layout(root):
    """Pausing while on "main" (the panel is ALREADY fully visible
    there) must not set _inline_kind — nothing here is Tk-packed by
    _apply_running_layout outside "running" anyway."""
    fake = FakeGui(root)
    fake._view = "main"
    gui.PainterGui._toggle_pause_job(fake, "chatgpt")
    assert fake._inline_kind is None


def test_toggle_pause_job_resume_does_not_hide_the_panel_again(root):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._toggle_pause_job(fake, "gemini")  # pause -> reveals it
    assert fake._inline_kind == "website_gen"
    gui.PainterGui._toggle_pause_job(fake, "gemini")  # resume
    assert fake.agents["gemini"].paused_calls == [True, False]
    assert fake._inline_kind == "website_gen"  # still there — only Start hides it
    assert fake._controls_box.winfo_manager() == "pack"


# ---------------------------------------------------------------------
# IconBar — a real widget
# ---------------------------------------------------------------------


def test_icon_bar_has_one_button_per_menu_tile(root):
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    assert set(bar._buttons) == {tile.id for tile in MENU_TILES}


def test_icon_bar_no_tile_starts_disabled(root):
    """GUI rework Phase 19 wires up the last placeholder
    ("api_image_gen") — every IconBar button is now live."""
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    disabled = {
        tile_id for tile_id, btn in bar._buttons.items()
        if btn.cget("state") == "disabled"
    }
    assert disabled == set()


def test_icon_bar_click_calls_on_select_with_the_tile_id(root):
    clicked = []
    bar = gui.IconBar(
        root, on_select=lambda tile_id: clicked.append(tile_id),
        on_menu=lambda: None,
    )
    bar._buttons["bg"].invoke()
    assert clicked == ["bg"]


def test_icon_bar_api_image_gen_click_now_calls_on_select_too(root):
    """The one button that used to be permanently disabled (command=
    None) now fires on_select with its tile id like any other."""
    clicked = []
    bar = gui.IconBar(
        root, on_select=lambda tile_id: clicked.append(tile_id),
        on_menu=lambda: None,
    )
    bar._buttons["api_image_gen"].invoke()
    assert clicked == ["api_image_gen"]


def test_icon_bar_home_button_calls_on_menu(root):
    """owner 2026-08-03 (UI rework tačka 2): the old right-side text
    "Menu" button is gone — the HOME icon button (leftmost, the one
    packed widget NOT keyed in _buttons) is the Menu affordance."""
    calls = []
    bar = gui.IconBar(
        root, on_select=lambda *_a: None, on_menu=lambda: calls.append(1),
    )
    extra = [
        w for w in bar.winfo_children()
        if w not in bar._buttons.values()
    ]
    assert extra == [bar._home]
    bar._home.invoke()
    assert calls == [1]


def test_icon_bar_home_button_is_icon_only_and_packed_first(root):
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    assert bar._home.cget("text") == ""
    assert bar.pack_slaves()[0] is bar._home


def test_icon_bar_icon_only_mode_drops_every_label_and_restores_all(root):
    """owner 2026-08-03 (UI rework tačka 2): too narrow → EVERY tile
    button drops its label at once (uniform, never a mixed strip);
    wide again → every label returns."""
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    bar._set_icon_only(True)
    assert all(btn.cget("text") == "" for btn in bar._buttons.values())
    bar._set_icon_only(False)
    for tile in MENU_TILES:
        assert bar._buttons[tile.id].cget("text") == tile.label


def test_icon_bar_restoring_labels_invalidates_the_measured_width(root):
    """Coming back to text mode clears the cached full-text width so
    the next <Configure> re-measures at the CURRENT font zoom."""
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    bar._full_w = 500
    bar._set_icon_only(True)
    assert bar._full_w == 500  # entering icon-only keeps the baseline
    bar._set_icon_only(False)
    assert bar._full_w == 0


def test_icon_bar_refresh_measure_clears_the_cached_width(root):
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    bar._full_w = 400
    bar.refresh_measure()
    assert bar._full_w == 0


def test_icon_bar_set_active_fills_active_tiles_and_outlines_the_rest(root):
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    bar.set_active({"bg", "website_gen"})
    assert bar._buttons["bg"].cget("border_width") == 0
    assert bar._buttons["website_gen"].cget("border_width") == 0
    assert bar._buttons["crop"].cget("border_width") == 1

    bar.set_active(set())  # every enabled tile back to an idle outline
    for tile in MENU_TILES:
        if tile.enabled:
            assert bar._buttons[tile.id].cget("border_width") == 1


def test_icon_bar_set_active_fills_api_image_gen_like_any_other_tile(root):
    """GUI rework Phase 19: "api_image_gen" used to be the one
    permanently-disabled placeholder set_active skipped outright; now
    it participates in the SAME live-status recolouring as every other
    enabled tile (no special case left in IconBar/set_active)."""
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    bar.set_active({"api_image_gen"})
    assert bar._buttons["api_image_gen"].cget("border_width") == 0
    assert bar._buttons["bg"].cget("border_width") == 1


# ---------------------------------------------------------------------
# End-to-end workflow regression (owner 2026-07-21 workflow fix): REAL
# AgentPanel widgets for both sites, proving the ACTUAL controls an
# owner would see — not just _inline_kind bookkeeping — stay correctly
# wired when one site starts while the other is idle. Real on-screen
# visibility (winfo_ismapped) needs a genuinely mapped window, which
# the suite's shared WITHDRAWN tk_root deliberately never is (see
# conftest.py) — winfo_ismapped() is 0 for every descendant of a
# withdrawn toplevel regardless of pack state, confirmed by hand, so
# "reachable" is proven here via winfo_manager() (packed by its own
# parent — the same technique every OTHER assertion in this file
# already uses), with genuine on-screen pixel proof left to the real,
# non-withdrawn-window screenshots (see gui.md's own "Verified" note
# for this session).
# ---------------------------------------------------------------------


class FakeGuiWithRealAgents(FakeGui):
    """``FakeGui`` (above), except ``self.agents`` holds REAL
    ``AgentPanel`` widgets — parented on ``_controls_box`` itself, the
    SAME parent production uses — instead of ``_RecordingPanel`` stand-
    ins, so button ``cget("state")``/``winfo_manager()`` reflect the
    real widget tree an owner would actually see. The SAME bare-
    ``AgentPanel`` ``make_panel`` convention test_gui_agent_visibility.
    py/test_gui_upscale.py/test_gui_pipeline.py already established.

    ``_go_view`` is overridden (the base ``FakeGui`` version is a plain
    recorder — correct for THAT file's own tests, which drive
    ``_apply_running_layout`` directly rather than through a real view
    transition) to ALSO call the REAL ``_apply_running_layout`` on
    entering "running", mirroring the one line of ``PainterGui.
    _set_view`` this workflow test actually depends on — proving the
    real cascade (Start -> ``_sync_running_state`` -> a genuine "main"
    -> "running" transition -> the controls actually get packed),
    which is exactly the connection the diagnosed bug broke."""

    def __init__(self, root):
        super().__init__(root)
        self.agents = {
            key: gui.AgentPanel(
                self._controls_box, key,
                on_start=lambda *_a: None, on_stop=lambda *_a: None,
                on_pause=lambda *_a: None,
            )
            for key in sorted(SITES)
        }
        for panel in self.agents.values():
            panel.pack(side="left", fill="both", expand=True)

    def _go_view(self, view: str) -> None:
        self.view_log.append(view)
        self._view = view
        if view == "running":
            gui.PainterGui._apply_running_layout(self)


def _simulate_start_site_tail(fake, key: str) -> None:
    """Mirrors ``PainterGui._start_site``'s OWN documented tail — the
    parts this fix touches — WITHOUT its heavy sheet-parsing/
    validation/thread-spawn prefix (already covered elsewhere, e.g.
    test_gui_tool_panels.py's ``FakeGuiForPanel`` convention for the
    tool-Start equivalent): mark the site running, style its own
    panel, unconditionally clear ``_inline_kind``, then reconcile the
    view exactly like the real method's last two lines."""
    fake._running.add(key)
    fake.agents[key].set_run_state(running=True)
    fake._inline_kind = None
    gui.PainterGui._sync_running_state(fake)


def test_workflow_starting_chatgpt_leaves_gemini_startable_and_visible(
    root,
):
    """THE literal corrected workflow, end to end, over REAL
    AgentPanel widgets: Start ChatGPT -> ChatGPT's Pause/Stop become
    the active controls, Gemini's OWN Start stays enabled AND packed
    (reachable), and ``_controls_box`` (holding BOTH panels) never
    disappears — the exact opposite of the diagnosed bug, where
    Starting either site hid the whole controls area, stranding the
    owner with no way to Start the other site or reach either one's
    Pause/Stop.

    Starts from "main" (the owner already clicked the Website GEN
    tile), NOT "running" — ``_sync_running_state``'s own view-
    transition check is a genuine no-op once ALREADY "running" (see
    ``test_sync_running_state_never_leaves_running_on_its_own`` above),
    so the FIRST site's Start must be the thing that actually DRIVES
    "main" -> "running" for ``_apply_running_layout`` to run at all —
    exactly the real ``PainterGui._start_site`` call site."""
    fake = FakeGuiWithRealAgents(root)
    fake._view = "main"

    _simulate_start_site_tail(fake, "chatgpt")

    # owner 2026-07-29: after Start the screen is the DASHBOARD alone
    assert fake._controls_box.winfo_manager() == ""
    assert fake._icon_bar.winfo_manager() == "pack"
    # ONE icon click brings the settings back — and with them the
    # OTHER site's fully reachable Start
    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")
    assert fake._controls_box.winfo_manager() == "pack"
    assert fake.agents["chatgpt"].winfo_manager() == "pack"
    assert fake.agents["gemini"].winfo_manager() == "pack"
    assert fake.agents["chatgpt"].btn_start.cget("state") == "disabled"
    assert fake.agents["chatgpt"].btn_stop.cget("state") == "normal"
    assert fake.agents["gemini"].btn_start.cget("state") == "normal"
    assert fake.agents["gemini"].btn_start.winfo_manager() == "pack"

    # Gemini starts too -> back to the dashboard; both jobs live
    _simulate_start_site_tail(fake, "gemini")

    assert fake._running == {"chatgpt", "gemini"}
    assert fake._controls_box.winfo_manager() == ""  # dashboard again
    assert fake.agents["chatgpt"].btn_stop.cget("state") == "normal"
    assert fake.agents["gemini"].btn_stop.cget("state") == "normal"
