"""API Image Generation job — adapter + panel + gating (GUI rework
Phase 19). The design doc's own "biggest risk-reducer": ``run_sheet``
only ever calls ``submit_prompt``/``await_done``/``extract_image`` on
its driver (plus ``attach``/``close`` in ``_drive_site`` and
``driver.site.name`` for the report header) — so a thin
``ApiImageAdapter`` over ``ai.generate_image`` runs the WHOLE proven
resume/report/postprocess/quota machinery untouched.

NO real quota is ever spent here — every test monkeypatches
``painter.ai.generate_image``. Four halves, matching gui.py's own
"pure helpers get pytest, real Tk/UI wiring gets a screenshot" split:

* ``ApiImageAdapter`` alone — pure Python, no Tk: ``submit_prompt``
  stores, ``extract_image`` returns the mocked bytes, and a
  ``PaidFeatureRequired`` from ``ai.generate_image`` maps to
  ``driver.TerminalState`` with ``retry_after_s=None`` (permanent, no
  auto-restart timer).
* ``PainterGui._drive_site`` GENERALIZED — proven with a bare fake
  driver (never branches on type) AND, end-to-end, with a REAL
  ``ApiImageAdapter``: a real ``Sheet`` runs through the REAL,
  unmodified ``run_sheet``, saving the mocked bytes at
  ``dest_for(drop, "api_image")`` under the out base — the same proof
  test_runner.py's own ``FakeDriver`` tests give chatgpt/gemini, just
  with the real adapter substituted for a fake SiteDriver. A second
  case drives the SAME path through a PaidFeatureRequired 429 and
  confirms the job stops quietly (no ``__terminal__`` event — the
  condition is permanent, never a timed auto-restart) while
  ``__worker_done__`` still always posts.
* ``PainterGui._compose_post_save(key, panel=...)`` — the new optional
  ``panel`` parameter, proven with a REAL (withdrawn-root)
  ``ApiImageGenPanel`` instead of ``self.agents[key]``, same ordered
  action-string contract test_gui_pipeline.py already proves for
  chatgpt/gemini.
* ``ApiImageGenPanel`` itself — defaults (BG/Crop/Force-Aspect/Upscale
  all ON, background "white" — spec item 3: no native transparency),
  the settings round-trip, and GATING: ``_probe_access`` (threading
  made synchronous for a deterministic test — the SAME "mock the
  class/thread, never wait on real timing" convention this whole
  suite already applies) disabling Start on a mocked
  ``PaidFeatureRequired`` and re-enabling it on a mocked success;
  ``PainterGui._start_api_image`` itself refuses (loud messagebox, no
  worker) when the panel is already gated.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import gui
from painter import ai as ai_module
from painter import filters
from painter.config import (
    AI_IMAGE_GATE_MESSAGE,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_POLARITY_IF,
    MODELS_SETTING,
    TIMING,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MIN_SIDE_DEFAULT,
    dest_for,
)
from painter.driver import TerminalState
from painter.jobtemp import clear_all
from painter.sheet_parser import PromptItem, Sheet

# a real 1x1 PNG so sniff_format/the report see real PNG bytes (same
# fixture bytes as test_runner.py/test_ai.py)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)


@pytest.fixture(autouse=True)
def _sweep_temp():
    """JobTemp's real backup root is PROJECT-relative (jobtemp.py's
    TEMP_ROOT), not tmp_path-relative — sweep it after every test, same
    as test_gui_pipeline.py/test_jobtemp.py."""
    yield
    clear_all()


@pytest.fixture
def root(tk_root):
    return tk_root


def make_sheet(tmp_path: Path, drop: str = "assets/badge/rune/Glory.png") -> Sheet:
    """One item, direct construction — mirrors test_runner.py's own
    ``make_sheet`` (bypassing markdown parsing entirely; the parser
    itself is untouched by this phase and already has its own
    coverage)."""
    source = tmp_path / "sheets" / "fake_api_image.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# Fake Theme\n", encoding="utf-8")
    items = (PromptItem("Glory", drop, "a stained-glass rondel", 3),)
    return Sheet("Fake Theme", source, items, (), ())


# ---------------------------------------------------------------------
# ApiImageAdapter — pure Python, no Tk
# ---------------------------------------------------------------------


def test_submit_prompt_stores_the_prompt():
    adapter = gui.ApiImageAdapter()
    adapter.submit_prompt("a stained-glass rondel")
    assert adapter._prompt == "a stained-glass rondel"


def test_attach_returns_a_title_and_close_and_await_done_are_noops():
    adapter = gui.ApiImageAdapter()
    title = adapter.attach()
    assert isinstance(title, str) and title  # a non-empty log-friendly string
    adapter.await_done()          # must not raise, no args required
    adapter.await_done(log=print)  # run_sheet's generate_one calls it this way
    adapter.close()               # must not raise


def test_site_name_is_set_for_the_run_reports_header():
    adapter = gui.ApiImageAdapter()
    assert adapter.site.name  # run_sheet reads driver.site.name when report=True


def test_extract_image_calls_generate_image_with_the_stored_prompt(monkeypatch):
    captured = {}

    def fake_generate_image(prompt, *, image_path=None, key=None, model=None, log=print):
        captured["prompt"] = prompt
        captured["image_path"] = image_path
        captured["model"] = model
        return PNG_1PX

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    adapter = gui.ApiImageAdapter()
    adapter.submit_prompt("a badge of glory")
    result = adapter.extract_image()
    assert result == PNG_1PX
    assert captured["prompt"] == "a badge of glory"
    assert captured["image_path"] is None  # a plain submit carries no attach
    # F5: the adapter no longer force-passes a model — generate_image
    # resolves it itself via model_for("image") (see test_ai.py's own
    # model_for tests), so the fake sees exactly what was passed: None
    assert captured["model"] is None


def test_extract_image_maps_paid_feature_required_to_terminal_state(monkeypatch):
    def fake_generate_image(prompt, *, image_path=None, key=None, model=None, log=print):
        raise ai_module.PaidFeatureRequired("gemini-2.5-flash-image: paid feature required")

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    adapter = gui.ApiImageAdapter()
    adapter.submit_prompt("x")
    with pytest.raises(TerminalState) as excinfo:
        adapter.extract_image()
    # PERMANENT — no wait ever fixes a zero free-tier quota, so unlike a
    # website quota with a parsed reset time, this never auto-restarts
    assert excinfo.value.retry_after_s is None
    assert "paid feature required" in str(excinfo.value)


def test_extract_image_lets_other_ai_errors_propagate_unmapped(monkeypatch):
    """Only PaidFeatureRequired is remapped (per the design doc's own
    wording) — a plain AiError (e.g. a malformed response) is NOT
    silently turned into a TerminalState; it propagates as-is so
    _drive_site's generic catch-all reports it loudly (Rule #1)."""
    def fake_generate_image(prompt, *, image_path=None, key=None, model=None, log=print):
        raise ai_module.AiError("some other failure")

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    adapter = gui.ApiImageAdapter()
    with pytest.raises(ai_module.AiError):
        adapter.extract_image()


# --- submit_with_image (F5, owner D3 — the audited image-attach gap) ---


def test_submit_with_image_stores_both_prompt_and_path(tmp_path):
    ref = tmp_path / "photo.png"
    ref.write_bytes(PNG_1PX)
    adapter = gui.ApiImageAdapter()
    adapter.submit_with_image(ref, "put this figure into the scene")
    assert adapter._prompt == "put this figure into the scene"
    assert adapter._image_path == ref


def test_extract_image_passes_the_stored_image_path_and_clears_it(
    monkeypatch, tmp_path,
):
    ref = tmp_path / "photo.png"
    ref.write_bytes(PNG_1PX)
    captured = []

    def fake_generate_image(prompt, *, image_path=None, key=None, model=None, log=print):
        captured.append((prompt, image_path))
        return PNG_1PX

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    adapter = gui.ApiImageAdapter()
    adapter.submit_with_image(ref, "put this figure into the scene")
    result = adapter.extract_image()
    assert result == PNG_1PX
    assert captured == [("put this figure into the scene", ref)]
    # cleared after the read — a FOLLOW-UP plain submit_prompt/extract
    # never leaks the same attach into an unrelated later item
    assert adapter._image_path is None
    captured.clear()
    adapter.submit_prompt("a different, plain item")
    adapter.extract_image()
    assert captured == [("a different, plain item", None)]


def test_submit_with_image_list_keeps_attach_order(monkeypatch, tmp_path):
    """MULTI-ATTACH (faza 2): a dual plate's two ← refs arrive as a
    list and reach generate_image in the same order — its inlineData
    parts are "the FIRST/SECOND attached image"."""
    a = tmp_path / "Vader.png"
    b = tmp_path / "Luke.png"
    a.write_bytes(PNG_1PX)
    b.write_bytes(PNG_1PX)
    captured = []

    def fake_generate_image(prompt, *, image_path=None, key=None, model=None, log=print):
        captured.append(image_path)
        return PNG_1PX

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    adapter = gui.ApiImageAdapter()
    adapter.submit_with_image([str(a), str(b)], "two refs")
    adapter.extract_image()
    assert captured == [[a, b]]


def test_submit_with_image_single_item_list_stays_a_bare_path(tmp_path):
    """A one-element list normalizes to the long-proven single form."""
    ref = tmp_path / "photo.png"
    ref.write_bytes(PNG_1PX)
    adapter = gui.ApiImageAdapter()
    adapter.submit_with_image([str(ref)], "p")
    assert adapter._image_path == ref


def test_submit_prompt_clears_a_previous_attach(monkeypatch, tmp_path):
    """A driver-shaped adapter is reused across MANY items in one run
    (run_sheet's queue loop) — without clearing, a PREVIOUS item's
    submit_with_image would leak its reference image into the NEXT
    plain-text item's extract_image call."""
    ref = tmp_path / "photo.png"
    ref.write_bytes(PNG_1PX)
    captured = []

    def fake_generate_image(prompt, *, image_path=None, key=None, model=None, log=print):
        captured.append(image_path)
        return PNG_1PX

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    adapter = gui.ApiImageAdapter()
    adapter.submit_with_image(ref, "with a reference")
    adapter.submit_prompt("plain, no reference")
    adapter.extract_image()
    assert captured == [None]


# ---------------------------------------------------------------------
# PainterGui._drive_site — generalized, not forked
# ---------------------------------------------------------------------


class _FakeAttachableDriver:
    """A driver-shaped object that is NOT a SiteDriver (no SiteConfig,
    no Playwright) — proves _drive_site never branches on the type it
    is handed, only calls attach()/close() and passes it to run_sheet,
    exactly like the real ApiImageAdapter/SiteDriver."""

    def __init__(self):
        self.site = SimpleNamespace(name="Fake Driver")
        self.attached = False
        self.closed = False
        self.submitted: list[str] = []

    def attach(self):
        self.attached = True
        return "fake tab"

    def close(self):
        self.closed = True

    def submit_prompt(self, prompt, log=print):
        self.submitted.append(prompt)

    def await_done(self, log=print):
        pass

    def extract_image(self):
        return PNG_1PX


def _drain(q: queue.Queue) -> list:
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def test_drive_site_accepts_a_non_sitedriver_and_calls_attach_then_close(
    tmp_path,
):
    sheet = make_sheet(tmp_path)
    driver = _FakeAttachableDriver()
    fake_self = SimpleNamespace(_q=queue.Queue())

    gui.PainterGui._drive_site(
        fake_self, "api_image", [sheet], tmp_path / "out", TIMING, driver,
        None, "", None, False, {str(sheet.source): None}, False, False,
        "off", threading.Event(), threading.Event(),
    )

    assert driver.attached is True
    assert driver.closed is True
    assert driver.submitted == ["a stained-glass rondel"]
    msgs = _drain(fake_self._q)
    assert ("__worker_done__", "api_image") in msgs
    assert not any(isinstance(m, tuple) and m[0] == "__terminal__" for m in msgs)


def test_drive_site_with_a_real_api_image_adapter_saves_the_generated_bytes(
    tmp_path, monkeypatch,
):
    """End-to-end proof of the design doc's "biggest risk-reducer":
    the REAL ApiImageAdapter, driven by the REAL (unmodified)
    run_sheet via the REAL (widened) _drive_site, saves the mocked
    bytes at the assets-mirroring dest_for path — report=True also
    proves driver.site.name reaches the report header."""
    monkeypatch.setattr(ai_module, "generate_image", lambda *a, **k: PNG_1PX)
    sheet = make_sheet(tmp_path, drop="assets/badge/rune/Glory.png")
    out_base = tmp_path / "out"
    driver = gui.ApiImageAdapter()
    fake_self = SimpleNamespace(_q=queue.Queue())

    gui.PainterGui._drive_site(
        fake_self, "api_image", [sheet], out_base, TIMING, driver,
        None, "", None, True, {str(sheet.source): None}, False, False,
        "off", threading.Event(), threading.Event(),
    )

    dest = out_base / dest_for("assets/badge/rune/Glory.png", "api_image")
    assert dest == out_base / "badge" / "rune" / "Glory_api.png"
    assert dest.read_bytes() == PNG_1PX
    report = out_base / "_state" / "api_image" / "fake_api_image_report.txt"
    assert report.is_file()
    assert "[API Image GEN]" in report.read_text(encoding="utf-8")
    msgs = _drain(fake_self._q)
    assert ("__worker_done__", "api_image") in msgs


def test_drive_site_with_paid_feature_required_stops_quietly(
    tmp_path, monkeypatch,
):
    """The free-tier-zero condition is PERMANENT: _drive_site's own
    "except TerminalState" branch only queues __terminal__ (the
    auto-restart countdown) when retry_after_s is not None — since
    ApiImageAdapter always raises it with retry_after_s=None, this job
    stops loudly but NEVER schedules an auto-restart timer, unlike a
    website quota with a parsed reset time."""
    def fake_generate_image(*a, **k):
        raise ai_module.PaidFeatureRequired("free_tier limit: 0")

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    sheet = make_sheet(tmp_path)
    out_base = tmp_path / "out"
    driver = gui.ApiImageAdapter()
    fake_self = SimpleNamespace(_q=queue.Queue())

    gui.PainterGui._drive_site(
        fake_self, "api_image", [sheet], out_base, TIMING, driver,
        None, "", None, False, {str(sheet.source): None}, False, False,
        "off", threading.Event(), threading.Event(),
    )

    assert not (out_base / dest_for(sheet.items[0].drop_path, "api_image")).exists()
    msgs = _drain(fake_self._q)
    assert ("__worker_done__", "api_image") in msgs
    assert not any(isinstance(m, tuple) and m[0] == "__terminal__" for m in msgs)
    log_lines = [m for m in msgs if isinstance(m, str)]
    assert any("TERMINAL STATE" in line for line in log_lines)


# ---------------------------------------------------------------------
# PainterGui._compose_post_save(key, panel=...) — the new optional panel
# ---------------------------------------------------------------------


class _FakeGuiForCompose:
    """Just enough surface for the UNBOUND _compose_post_save to run —
    same minimal convention test_gui_pipeline.py's own FakeGui uses."""

    def __init__(self):
        self.agents: dict = {}
        self._job_temps: dict = {}
        self._q: queue.Queue = queue.Queue()


def make_panel(root) -> "gui.ApiImageGenPanel":
    return gui.ApiImageGenPanel(
        root, on_start=lambda: None, on_pause=lambda *_a: None,
        on_stop=lambda *_a: None,
    )


def test_compose_post_save_with_explicit_panel_orders_bg_crop_aspect_upscale(
    root, tmp_path,
):
    """ApiImageGenPanel's own defaults (all four ON) reused UNCHANGED
    by _compose_post_save via the new panel= param — same ordered
    action-string contract test_gui_pipeline.py proves for chatgpt/
    gemini's self.agents[key] path."""
    import numpy as np
    from PIL import Image

    panel = make_panel(root)
    assert panel.bg_removal_var.get() is True
    assert panel.crop_var.get() is True
    assert panel.force_aspect_var.get() is True
    assert panel.upscale_var.get() is True

    fake = _FakeGuiForCompose()
    post_save = gui.PainterGui._compose_post_save(fake, "api_image", panel=panel)
    assert callable(post_save)

    # a real, tiny, near-square white plate — small enough that Upscale
    # (min side default 800) also fires, so all four steps show "done"
    img = tmp_path / "plate.png"
    arr = np.full((100, 100, 3), 255, dtype=np.uint8)
    arr[8:92, 8:92] = (200, 30, 30)
    Image.fromarray(arr, mode="RGB").save(img, "PNG")

    action = post_save(img)
    steps_in_order = [seg.split(":")[0].strip() for seg in action.split(",")]
    assert steps_in_order == ["REMOVE BG", "CROP", "ASPECT", "UPSCALE"]


# ---------------------------------------------------------------------
# ApiImageGenPanel — defaults + settings round-trip
# ---------------------------------------------------------------------


def test_panel_defaults_match_spec_item_3_no_native_transparency(root):
    panel = make_panel(root)
    assert panel.background_var.get() == "white"
    assert panel.bg_removal_var.get() is True
    assert panel.crop_var.get() is True
    assert panel.force_aspect_var.get() is True
    assert panel.upscale_var.get() is True
    assert panel.report_var.get() is True
    assert panel.access_gated is False


def test_panel_settings_round_trip(root):
    panel = make_panel(root)
    panel.background_var.set("transparent")
    panel.crop_var.set(False)
    panel.upscale_var.set(False)
    panel.force_aspect_w_var.set("4")
    panel.force_aspect_h_var.set("3")
    panel.up_minside_var.set("640")
    stored = panel.get_settings()

    fresh = make_panel(root)
    conditions = [
        filters.condition_from_dict(d) for d in stored["conditions"]
    ]
    fresh.apply_settings(stored, conditions=conditions)
    assert fresh.background_var.get() == "transparent"
    assert fresh.crop_var.get() is False
    assert fresh.upscale_var.get() is False
    assert fresh.force_aspect_w_var.get() == "4"
    assert fresh.force_aspect_h_var.get() == "3"
    assert fresh.up_minside_var.get() == "640"
    assert fresh.upscale_filter.get_conditions() == panel.upscale_filter.get_conditions()


def test_panel_upscale_params_match_the_shared_resolver(root):
    panel = make_panel(root)
    params = panel.upscale_params()
    assert params["min_width"] == params["min_height"] == UPSCALE_MIN_SIDE_DEFAULT
    assert params["aspect_min"] == UPSCALE_ASPECT_MIN
    assert params["aspect_max"] == UPSCALE_ASPECT_MAX
    conditions = panel.upscale_conditions()
    assert conditions == [
        filters.FilterCondition(
            kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
            lo=UPSCALE_ASPECT_MIN, hi=UPSCALE_ASPECT_MAX,
        )
    ]


def test_panel_set_run_state_and_set_paused(root):
    panel = make_panel(root)
    panel.set_run_state(running=True)
    assert panel.btn_start.cget("state") == "disabled"
    assert panel.btn_stop.cget("state") == "normal"
    panel.set_run_state(running=False)
    assert panel.btn_start.cget("state") == "normal"
    assert panel.btn_stop.cget("state") == "disabled"

    panel.set_paused(True)
    assert panel.btn_pause.cget("text") == "Resume"
    panel.set_paused(False)
    assert panel.btn_pause.cget("text") == "Pause"


# ---------------------------------------------------------------------
# Gating — "Check API access" (spec item 5)
# ---------------------------------------------------------------------


class _ImmediateThread:
    """Runs ``target`` synchronously instead of on a real OS thread —
    deterministic tests for _probe_access's fire-and-poll shape without
    depending on real timing (this whole suite's convention: mock the
    class/thread, never wait on real timing)."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)


def _run_probe_synchronously(monkeypatch, panel) -> None:
    """Fire panel._probe_access() with the worker thread replaced by an
    immediate call, then apply its ONE queued result directly (the same
    _poll_probe the real self.after(...) loop would eventually call) —
    bypasses Tk's event loop entirely for a fast, deterministic test."""
    monkeypatch.setattr(gui.threading, "Thread", _ImmediateThread)
    panel._probe_access()
    msg = panel._probe_q.get_nowait()
    panel._apply_probe_result(msg)


def test_probe_access_gated_disables_start_with_the_gate_message(
    root, monkeypatch,
):
    def fake_generate_image(*a, **k):
        raise ai_module.PaidFeatureRequired(
            "gemini-2.5-flash-image: paid feature required — the free"
            " tier has zero quota for this model"
        )

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    panel = make_panel(root)
    assert panel.access_gated is False

    _run_probe_synchronously(monkeypatch, panel)

    assert panel.access_gated is True
    assert panel._gate_var.get() == AI_IMAGE_GATE_MESSAGE
    assert panel.btn_start.cget("state") == "disabled"


def test_probe_access_ok_clears_a_previous_gate(root, monkeypatch):
    panel = make_panel(root)
    panel.access_gated = True  # simulate a previous gated probe

    monkeypatch.setattr(ai_module, "generate_image", lambda *a, **k: PNG_1PX)
    _run_probe_synchronously(monkeypatch, panel)

    assert panel.access_gated is False
    assert panel.btn_start.cget("state") == "normal"


def test_probe_access_other_ai_error_is_shown_but_leaves_the_gate_unchanged(
    root, monkeypatch,
):
    """NoKey (or any non-PaidFeatureRequired AiError) is inconclusive —
    it must not falsely claim 'access OK' NOR wrongly gate Start."""
    def fake_generate_image(*a, **k):
        raise ai_module.NoKey("no Gemini API key in settings.json")

    monkeypatch.setattr(ai_module, "generate_image", fake_generate_image)
    panel = make_panel(root)

    _run_probe_synchronously(monkeypatch, panel)

    assert panel.access_gated is False
    assert "inconclusive" in panel._gate_var.get().lower()
    assert panel.btn_start.cget("state") == "normal"


# ---------------------------------------------------------------------
# "Models…" discovery + per-purpose picks (F5, owner D1/D2/D4)
# ---------------------------------------------------------------------

FAKE_DISCOVERED_MODELS = [
    {
        "name": "gemini-2.5-flash-image", "methods": ("generateContent",),
        "display": "Flash Image",
    },
    {
        "name": "gemini-flash-latest", "methods": ("generateContent",),
        "display": "Flash",
    },
    {
        "name": "gemini-3.1-pro", "methods": ("generateContent",),
        "display": "Pro",
    },
    {
        "name": "text-embedding-004", "methods": ("embedContent",),
        "display": "Embedding",
    },
]


def _run_refresh_models_synchronously(monkeypatch, panel) -> None:
    """Same convention as ``_run_probe_synchronously`` above: the
    worker thread runs immediately and its ONE queued result is
    applied directly, bypassing Tk's event loop for a fast,
    deterministic test."""
    monkeypatch.setattr(gui.threading, "Thread", _ImmediateThread)
    panel._refresh_models()
    msg = panel._models_q.get_nowait()
    panel._apply_models_result(msg)


def test_refresh_models_populates_the_image_only_dropdown(
    root, monkeypatch,
):
    """Faza 3 (owner UV tačka 5, P3=A): the API panel carries ONLY the
    Image-generation dropdown — the Vision/Text picks move to the
    panels that USE them (AI Check / New Collection, faza 4) — and the
    list holds image-CAPABLE models only, never all 58."""
    from painter import settings as settings_module

    monkeypatch.setattr(ai_module, "list_models", lambda **k: FAKE_DISCOVERED_MODELS)
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    panel = make_panel(root)

    _run_refresh_models_synchronously(monkeypatch, panel)

    assert panel._discovered_models == FAKE_DISCOVERED_MODELS
    assert set(panel._model_combos) == {"image"}   # no vision/text here
    assert panel._model_combos["image"].cget("values") == [
        "gemini-2.5-flash-image"
    ]
    assert panel.model_image_var.get() == "gemini-2.5-flash-image"
    # the curated hint follows the selection (config.model_hint)
    assert "Flash image" in panel._model_hint_var.get()


def test_show_all_debug_switch_widens_the_list_to_everything(
    root, monkeypatch,
):
    from painter import settings as settings_module

    monkeypatch.setattr(ai_module, "list_models", lambda **k: FAKE_DISCOVERED_MODELS)
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    panel = make_panel(root)
    _run_refresh_models_synchronously(monkeypatch, panel)

    panel.model_show_all_var.set(True)  # the trace repopulates
    assert panel._model_combos["image"].cget("values") == [
        m["name"] for m in FAKE_DISCOVERED_MODELS
    ]
    panel.model_show_all_var.set(False)
    assert panel._model_combos["image"].cget("values") == [
        "gemini-2.5-flash-image"
    ]


def test_unknown_model_gets_the_honest_unverified_hint(root, monkeypatch):
    from painter.config import MODEL_HINT_UNKNOWN

    panel = make_panel(root)
    panel._update_model_hint("some-future-model")
    assert panel._model_hint_var.get() == MODEL_HINT_UNKNOWN


def test_refresh_models_preselects_the_stored_override_over_the_recommendation(
    root, monkeypatch,
):
    from painter import settings as settings_module

    monkeypatch.setattr(ai_module, "list_models", lambda **k: FAKE_DISCOVERED_MODELS)
    monkeypatch.setattr(
        settings_module, "load_settings",
        lambda: {MODELS_SETTING: {"image": "gemini-2.5-flash-image"}},
    )
    panel = make_panel(root)

    _run_refresh_models_synchronously(monkeypatch, panel)

    assert panel.model_image_var.get() == "gemini-2.5-flash-image"  # the override


def test_refresh_models_nokey_shows_the_key_gate_message(root, monkeypatch):
    """A NoKey (or any AiError) surfaces its OWN message verbatim —
    NoKey's text already IS the key-gate pattern used elsewhere (spec
    item 4), so there is no separate copy to keep in sync."""
    def boom(**k):
        raise ai_module.NoKey(
            "no Gemini API key in settings.json — run the 'AI key…' wizard"
        )

    monkeypatch.setattr(ai_module, "list_models", boom)
    panel = make_panel(root)

    _run_refresh_models_synchronously(monkeypatch, panel)

    assert "no Gemini API key" in panel._models_status_var.get()
    assert panel._discovered_models == []


def test_on_model_pick_writes_settings_immediately(root, monkeypatch):
    from painter import settings as settings_module

    saved: dict = {}
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    monkeypatch.setattr(
        settings_module, "save_settings", lambda d: saved.update(d),
    )
    panel = make_panel(root)

    panel._on_model_pick("image", "gemini-3.1-flash-image")

    assert saved[MODELS_SETTING] == {"image": "gemini-3.1-flash-image"}


def test_on_model_pick_merges_with_existing_overrides(root, monkeypatch):
    from painter import settings as settings_module

    monkeypatch.setattr(
        settings_module, "load_settings",
        lambda: {MODELS_SETTING: {"text": "gemini-flash-latest"}},
    )
    saved: dict = {}
    monkeypatch.setattr(
        settings_module, "save_settings", lambda d: saved.update(d),
    )
    panel = make_panel(root)

    panel._on_model_pick("image", "gemini-2.5-flash-image")

    assert saved[MODELS_SETTING] == {
        "text": "gemini-flash-latest", "image": "gemini-2.5-flash-image",
    }


def test_populating_the_dropdown_via_refresh_never_writes_settings(
    root, monkeypatch,
):
    """``combo.set()`` (the preselect) must NOT go through
    ``_on_model_pick`` — only a GENUINE dropdown click (the combo's own
    ``command=``) may persist an override; merely displaying the
    current override/recommendation must never write."""
    from painter import settings as settings_module

    monkeypatch.setattr(ai_module, "list_models", lambda **k: FAKE_DISCOVERED_MODELS)
    monkeypatch.setattr(settings_module, "load_settings", lambda: {})
    save_calls: list = []
    monkeypatch.setattr(
        settings_module, "save_settings", lambda d: save_calls.append(d),
    )
    panel = make_panel(root)

    _run_refresh_models_synchronously(monkeypatch, panel)

    assert save_calls == []


# ---------------------------------------------------------------------
# PainterGui._start_api_image — refuses to start while gated
# ---------------------------------------------------------------------


class _FakeGuiForStartApiImage:
    """Just enough surface to reach _start_api_image's gating check
    (BEFORE any worker/thread/JobTemp machinery) — same duck-typed
    convention as _FakeGuiForCompose/test_gui_tool_panels.py's own
    FakeGuiForPanel."""

    _start_api_image = gui.PainterGui._start_api_image
    _out_base = gui.PainterGui._out_base

    def __init__(self, sheet: Sheet, panel, out_dir: Path):
        self._sheets = [sheet.source]
        self._sheet = sheet
        self._tool_panels = {"api_image_gen": panel}
        self.out_var = SimpleNamespace(get=lambda: str(out_dir))
        self._running: set[str] = set()
        self.log_lines: list[str] = []

    def _parse_all(self):
        return [self._sheet]

    def _log(self, msg: str) -> None:
        self.log_lines.append(msg)


def test_start_api_image_refuses_while_gated(root, tmp_path, monkeypatch):
    errors: list = []
    monkeypatch.setattr(
        gui.messagebox, "showerror", lambda *a, **k: errors.append(a)
    )
    panel = make_panel(root)
    panel.access_gated = True
    sheet = make_sheet(tmp_path)
    fake = _FakeGuiForStartApiImage(sheet, panel, tmp_path / "out")

    gui.PainterGui._start_api_image(fake)

    assert errors
    assert any(AI_IMAGE_GATE_MESSAGE in str(arg) for call in errors for arg in call)
    assert "api_image" not in fake._running
