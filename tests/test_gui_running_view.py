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
  ``_request_menu``/``_click_icon_bar_tile``/``_tile_handler``) run for
  REAL through a small duck-typed ``FakeGui`` — the SAME convention
  test_gui_pipeline.py's own ``FakeGui`` uses for ``_compose_post_save``
  (never a full ``PainterGui``: a heavy ``__init__``, and every other
  phase's tests avoid it too). ``IconBar`` itself is a real, cheap-to-
  construct widget: button count/ids, the one permanently-disabled
  placeholder, and ``set_active``'s filled/outline recolouring.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

import gui
from painter.config import JOB_ORDER, MENU_TILES


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
    _toggle_pause_job = gui.PainterGui._toggle_pause_job

    def __init__(self, root):
        self._running: set[str] = set()
        self._tool_workers: dict[str, object] = {}
        self._view = "menu"
        self._inline_kind: str | None = None
        self.status_var = tk.StringVar(value="idle")
        self.view_log: list[str] = []  # every _go_view request, in order

        self._controls_box = ttk.Frame(root)
        self._compact_box = ttk.Frame(root)
        self.notebook = ttk.Notebook(root)
        self.notebook.add(ttk.Frame(self.notebook), text="Dashboard")
        self.notebook.add(ttk.Frame(self.notebook), text="Log")
        self.notebook.pack(fill="both", expand=True)
        self._scroll = SimpleNamespace(refresh=lambda: None)
        self._icon_bar = gui.IconBar(
            root, on_select=lambda *_a: None, on_menu=lambda: None,
        )

        self.new_collection_calls = 0
        self.start_ai_check_calls = 0
        self.start_tool_calls: list[str] = []

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

    def _start_ai_check(self) -> None:
        self.start_ai_check_calls += 1

    def _start_tool(self, slot: str) -> None:
        self.start_tool_calls.append(slot)

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


def test_apply_running_layout_packs_icon_bar_always_controls_box_never_by_default(
    root,
):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._apply_running_layout(fake)
    assert fake._icon_bar.winfo_manager() == "pack"
    assert fake._controls_box.winfo_manager() == ""
    assert fake._compact_box.winfo_manager() == ""


def test_apply_running_layout_shows_controls_box_only_while_website_gen_inline(
    root,
):
    fake = FakeGui(root)
    fake._view = "running"
    fake._inline_kind = "website_gen"
    gui.PainterGui._apply_running_layout(fake)
    assert fake._controls_box.winfo_manager() == "pack"

    fake._inline_kind = None
    gui.PainterGui._apply_running_layout(fake)
    assert fake._controls_box.winfo_manager() == ""


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


def test_click_icon_bar_tile_on_a_running_kind_just_focuses_the_dashboard(
    root,
):
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    fake.notebook.select(1)  # currently on "Log"
    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")
    assert fake.notebook.index("current") == 0  # jumped to Dashboard
    assert fake._inline_kind is None  # untouched — not a settings toggle


def test_click_icon_bar_tile_website_gen_toggles_the_inline_panel(root):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")
    assert fake._inline_kind == "website_gen"
    assert fake._controls_box.winfo_manager() == "pack"

    gui.PainterGui._click_icon_bar_tile(fake, "website_gen")
    assert fake._inline_kind is None
    assert fake._controls_box.winfo_manager() == ""


def test_click_icon_bar_tile_a_not_running_tool_invokes_its_existing_handler(
    root,
):
    """bg/crop/upscale/aspect have no persistent panel yet (Phase
    13-15) — clicking still launches through the SAME handler the Main
    Menu itself uses (_tile_handler), undisturbed by some OTHER job
    that keeps running."""
    fake = FakeGui(root)
    fake._view = "running"
    fake._running = {"chatgpt"}
    gui.PainterGui._click_icon_bar_tile(fake, "bg")
    assert fake.start_tool_calls == ["bg"]
    assert fake._inline_kind is None  # website_gen panel never touched


def test_click_icon_bar_tile_ai_sheet_gen_always_opens_its_dialog(root):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._click_icon_bar_tile(fake, "ai_sheet_gen")
    assert fake.new_collection_calls == 1


def test_click_icon_bar_tile_image_checker_not_running_starts_it(root):
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._click_icon_bar_tile(fake, "image_checker")
    assert fake.start_ai_check_calls == 1


def test_tile_handler_website_gen_and_the_disabled_tile_have_no_handler(root):
    fake = FakeGui(root)
    assert gui.PainterGui._tile_handler(fake, "website_gen") is None
    assert gui.PainterGui._tile_handler(fake, "api_image_gen") is None


def test_tile_handler_covers_every_menu_tile_id_without_raising(root):
    fake = FakeGui(root)
    for tile in MENU_TILES:
        gui.PainterGui._tile_handler(fake, tile.id)  # must not KeyError


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


def test_toggle_pause_job_on_a_tool_never_touches_the_inline_panel(root):
    """bg/crop/upscale/aspect/aicheck have no persistent settings panel
    yet (Phase 13-15) — pausing one is a no-op beyond its own existing
    Pause/Resume toggle (already reflected via panels[kind].set_paused)."""
    fake = FakeGui(root)
    fake._view = "running"
    gui.PainterGui._toggle_pause_job(fake, "bg")
    assert "bg" in fake._paused
    assert fake.panels["bg"].paused_calls == [True]
    assert "bg" not in fake.agents  # tools have no AgentPanel entry
    assert fake._inline_kind is None


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


def test_icon_bar_only_the_disabled_tile_starts_disabled(root):
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    disabled = {
        tile_id for tile_id, btn in bar._buttons.items()
        if btn.cget("state") == "disabled"
    }
    assert disabled == {"api_image_gen"}


def test_icon_bar_click_calls_on_select_with_the_tile_id(root):
    clicked = []
    bar = gui.IconBar(
        root, on_select=lambda tile_id: clicked.append(tile_id),
        on_menu=lambda: None,
    )
    bar._buttons["bg"].invoke()
    assert clicked == ["bg"]


def test_icon_bar_menu_button_calls_on_menu(root):
    calls = []
    bar = gui.IconBar(
        root, on_select=lambda *_a: None, on_menu=lambda: calls.append(1),
    )
    # the Menu button is the one packed widget NOT keyed in _buttons
    menu_btn = [
        w for w in bar.winfo_children()
        if w not in bar._buttons.values()
    ]
    assert len(menu_btn) == 1
    menu_btn[0].invoke()
    assert calls == [1]


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


def test_icon_bar_set_active_never_touches_the_disabled_placeholder(root):
    bar = gui.IconBar(root, on_select=lambda *_a: None, on_menu=lambda: None)
    before = bar._buttons["api_image_gen"].cget("state")
    bar.set_active({"api_image_gen"})  # nonsensical input, must be a no-op
    assert bar._buttons["api_image_gen"].cget("state") == before
