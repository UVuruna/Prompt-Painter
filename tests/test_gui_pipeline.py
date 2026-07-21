"""Pipeline reorder + Force Aspect Ratio + per-step backups (GUI rework
Phase 8): BG -> Crop -> Aspect(force) -> Upscale, per-step JobTemp
backups for the two gen SITES (new plumbing — only the four standalone
tools had a JobTemp before this phase), the disk cap fallback, and the
new AgentPanel fields (``force_aspect_var``/``force_aspect_w_var``/
``force_aspect_h_var``/``keep_all_steps_var``).

Four halves:

* ``gui._run_pipeline_steps`` is the pure-ish, Tk-free per-image engine
  behind ``PainterGui._compose_post_save`` — dedup of "original" against
  the first enabled step, drop-on-no-op, the disk cap fallback and the
  per-agent "keep every step" toggle, all tested directly with fake
  ``path -> status`` step functions (no real image processing needed to
  prove the BACKUP bookkeeping).
* ``PainterGui._compose_post_save`` itself is exercised through a small
  duck-typed ``FakeGui`` stand-in (``.agents``/``._job_temps``/``._q`` —
  the only attributes the method touches) carrying a REAL (withdrawn
  Tk root) ``AgentPanel`` — never a full ``PainterGui`` (see
  test_gui_upscale.py's own docstring on why). Proves the ordered
  action string ("REMOVE BG, CROP, ASPECT, UPSCALE") and the CRITICAL
  byte-identical-when-off regression guard.
* one REAL end-to-end test drives the actual engine functions (bg_remove
  /crop/aspect/a MOCKED upscale binary — same ``fake_binary`` pattern as
  test_gui_upscale.py) through the full pipeline and cross-checks the
  result against calling the four engine functions directly in the same
  order, plus the exact backup set under ``__steps__`` and two
  ``restore_to`` round-trips (pristine + a middle stage).
* ``AgentPanel``'s new fields/methods and ``DashPanel``'s new loud,
  PERSISTENT "over_cap" banner (vs the muted, overwritten ``state_var``)
  round out the GUI-facing half.
"""

from __future__ import annotations

import queue
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import gui
import painter.jobtemp as jobtemp_module
import painter.upscale as upscale_mod
from painter import aspect as aspect_module
from painter import postprocess as postprocess_module
from painter.config import (
    ASPECT_DEFAULT_H,
    ASPECT_DEFAULT_W,
    JOBTEMP_CAP_BANNER_TEXT,
    JOBTEMP_KEEP_ALL_STEPS_DEFAULT,
)
from painter.jobtemp import JobTemp, clear_all


@pytest.fixture(autouse=True)
def _sweep_temp():
    """JobTemp's real backup root lives under the PROJECT's own
    .painter_tmp/ (PROJECT_ROOT-relative, not tmp_path-relative — see
    jobtemp.py's TEMP_ROOT) regardless of which folder the live images
    sit in; sweep it after every test, same as test_jobtemp.py."""
    yield
    clear_all()


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(root) -> gui.AgentPanel:
    """A bare AgentPanel, parented directly on the shared root (never
    packed/mapped — same convention test_gui_upscale.py already uses)
    with no-op callbacks — never a full PainterGui."""
    return gui.AgentPanel(
        root, "gemini",
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None,
    )


class FakeGui:
    """A duck-typed stand-in for PainterGui — just enough attribute
    surface for the UNBOUND ``PainterGui._compose_post_save`` to run:
    ``.agents`` (site -> AgentPanel), ``._job_temps`` (site -> JobTemp,
    entries optional) and ``._q`` (a real Queue, so post_save's log/
    emit lambdas have somewhere real to write) — never a full app
    window (see this module's docstring)."""

    def __init__(self, agents: dict, job_temps: dict | None = None):
        self.agents = agents
        self._job_temps = job_temps or {}
        self._q: queue.Queue = queue.Queue()


def compose(panel: gui.AgentPanel, key: str = "gemini", temp=None):
    """Build ONE site's post_save hook exactly like _start_site does
    (JobTemp attached BEFORE compose runs), via the unbound-method call
    (no Tk mainloop / no full PainterGui needed)."""
    job_temps = {key: temp} if temp is not None else {}
    fake = FakeGui({key: panel}, job_temps)
    post_save = gui.PainterGui._compose_post_save(fake, key)
    return post_save, fake


def make_png(path: Path, width: int, height: int) -> None:
    """Any tiny, real, decodable PNG — for tests that only care about
    BACKUP bookkeeping (fake step functions never read pixel content)."""
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    Image.fromarray(arr, mode="RGBA").save(path, "PNG")


def make_white_plate(path: Path, size: int = 100) -> None:
    """Same recipe as test_postprocess.py's own ``make_white_plate`` — a
    red subject filling a pure-white plate with an 8px border: BG
    removal clears ~29% (well under the safety guard) leaving a clean,
    exactly-predictable 84x84 opaque square (content box (8,8,92,92))."""
    rgb = np.full((size, size, 3), 255, dtype=np.uint8)
    rgb[8:size - 8, 8:size - 8] = (200, 30, 30)
    Image.fromarray(rgb, mode="RGB").save(path, "PNG")


@pytest.fixture
def fake_binary(monkeypatch):
    """Same mock as test_gui_upscale.py's own fixture — no real
    Real-ESRGAN ncnn-vulkan binary needed: a deterministic NEAREST
    scale-by-4 stand-in for ``_run_binary``."""
    calls: list[int] = []

    def fake_ensure(log=print):
        return Path("fake-realesrgan.exe")

    def fake_run(exe, src, dst, scale):
        calls.append(scale)
        with Image.open(src) as im:
            im.resize(
                (im.width * scale, im.height * scale), Image.NEAREST
            ).save(dst, "PNG")

    monkeypatch.setattr(upscale_mod, "ensure_binary", fake_ensure)
    monkeypatch.setattr(upscale_mod, "_run_binary", fake_run)
    return calls


# ---------------------------------------------------------------------
# gui._run_pipeline_steps — the per-image engine, Tk-free
# ---------------------------------------------------------------------


def test_run_pipeline_steps_orders_the_action_string_by_steps_order():
    calls = []
    steps = [
        ("REMOVE BG", "bg", lambda p: calls.append("bg") or "done"),
        ("CROP", "crop", lambda p: calls.append("crop") or "nothing"),
    ]
    result = gui._run_pipeline_steps(
        Path("whatever.png"), steps, None, True, lambda: None,
    )
    assert result == "REMOVE BG: done, CROP: nothing"
    assert calls == ["bg", "crop"]  # ran in the given order


def test_run_pipeline_steps_with_no_jobtemp_skips_all_backup_bookkeeping():
    """temp=None (a headless caller, or _compose_post_save without a
    JobTemp attached) still runs every step — only the backup calls are
    skipped; no crash from a non-existent path (fake steps never touch
    the filesystem)."""
    result = gui._run_pipeline_steps(
        Path("does-not-exist.png"),
        [("CROP", "crop", lambda p: "done")],
        None, True, lambda: (_ for _ in ()).throw(AssertionError("never")),
    )
    assert result == "CROP: done"


def test_run_pipeline_steps_dedups_original_against_first_enabled_step(tmp_path):
    """The FIRST enabled step's pre-state is tagged 'original', not its
    own name — writing both would be a byte-identical duplicate of the
    same instant (owner ask, GUI rework Phase 8)."""
    folder = tmp_path / "out"
    folder.mkdir()
    img = folder / "a.png"
    make_png(img, 10, 10)
    temp = JobTemp("dedup-test", folder)

    steps = [
        ("REMOVE BG", "bg", lambda p: "done"),
        ("CROP", "crop", lambda p: "done"),
    ]
    result = gui._run_pipeline_steps(img, steps, temp, True, lambda: None)
    assert result == "REMOVE BG: done, CROP: done"
    # "bg" is ABSENT — its pre-state is captured as "original" instead
    assert temp.steps_for("a.png") == ["original", "crop"]
    assert temp.has_backup("a.png", step="bg") is False


def test_run_pipeline_steps_original_survives_even_when_first_step_is_a_noop(tmp_path):
    """'original' is the restore-ALL target — it is never dropped,
    whatever the first step's own status turns out to be."""
    folder = tmp_path / "out"
    folder.mkdir()
    img = folder / "a.png"
    make_png(img, 10, 10)
    temp = JobTemp("orig-survives-test", folder)

    steps = [("REMOVE BG", "bg", lambda p: "nothing")]
    gui._run_pipeline_steps(img, steps, temp, True, lambda: None)
    assert temp.steps_for("a.png") == ["original"]
    assert temp.has_backup("a.png", step="original") is True


def test_run_pipeline_steps_drops_a_named_backup_on_a_no_op_result(tmp_path):
    """A LATER (non-first) step's own named backup is dropped when that
    step turns out to be a no-op — mirrors the four standalone tools'
    own restore-point hygiene (a no-op has nothing worth restoring)."""
    folder = tmp_path / "out"
    folder.mkdir()
    img = folder / "a.png"
    make_png(img, 10, 10)
    temp = JobTemp("drop-test", folder)

    steps = [
        ("REMOVE BG", "bg", lambda p: "done"),
        ("CROP", "crop", lambda p: "nothing"),   # a no-op
        ("UPSCALE", "upscale", lambda p: "done"),
    ]
    gui._run_pipeline_steps(img, steps, temp, True, lambda: None)
    # "crop" never survives as a backup; "upscale" (a real change) does
    assert temp.steps_for("a.png") == ["original", "upscale"]


def test_run_pipeline_steps_over_cap_stops_new_backups_keeps_original_only(
    tmp_path, monkeypatch,
):
    folder = tmp_path / "out"
    folder.mkdir()
    img1, img2 = folder / "a.png", folder / "b.png"
    make_png(img1, 10, 10)
    make_png(img2, 10, 10)
    size = img1.stat().st_size
    temp = JobTemp("cap-test", folder)

    # the cap sits exactly at 3 backups' worth — image 1 fills it
    # (original + crop + upscale), image 2 must fall back to original-only
    monkeypatch.setattr(jobtemp_module, "JOBTEMP_MAX_BYTES", size * 3)

    def build_steps():
        return [
            ("REMOVE BG", "bg", lambda p: "done"),
            ("CROP", "crop", lambda p: "done"),
            ("UPSCALE", "upscale", lambda p: "done"),
        ]

    cap_hits: list[int] = []
    on_cap = lambda: cap_hits.append(1)

    gui._run_pipeline_steps(img1, build_steps(), temp, True, on_cap)
    assert temp.steps_for("a.png") == ["original", "crop", "upscale"]
    assert cap_hits == []  # image 1 never crosses the cap MID-processing

    gui._run_pipeline_steps(img2, build_steps(), temp, True, on_cap)
    # image 2: "original" is ALWAYS taken (even over cap); crop/upscale
    # are skipped — original-only fallback
    assert temp.steps_for("b.png") == ["original"]
    assert cap_hits == [1, 1]  # on_cap fired once per SKIPPED backup


def test_run_pipeline_steps_keep_all_steps_off_skips_silently_no_banner(tmp_path):
    """The owner's OWN 'keep every step' toggle being OFF is a
    deliberate choice, not a disk emergency — same original-only
    outcome as over_cap, but on_cap() must NEVER fire for it."""
    folder = tmp_path / "out"
    folder.mkdir()
    img = folder / "a.png"
    make_png(img, 10, 10)
    temp = JobTemp("keepoff-test", folder)

    steps = [
        ("REMOVE BG", "bg", lambda p: "done"),
        ("CROP", "crop", lambda p: "done"),
        ("UPSCALE", "upscale", lambda p: "done"),
    ]
    cap_hits: list[int] = []
    gui._run_pipeline_steps(
        img, steps, temp, False, lambda: cap_hits.append(1),
    )
    assert temp.steps_for("a.png") == ["original"]
    assert cap_hits == []


# ---------------------------------------------------------------------
# PainterGui._compose_post_save — ordering + the byte-identical guard
# ---------------------------------------------------------------------


def test_compose_post_save_returns_none_when_every_switch_is_off(root):
    panel = make_panel(root)
    panel.bg_removal_var.set(False)
    panel.crop_var.set(False)
    panel.upscale_var.set(False)
    assert panel.force_aspect_var.get() is False  # default OFF
    post_save, _g = compose(panel)
    assert post_save is None


def test_compose_post_save_all_four_on_orders_bg_crop_aspect_upscale(
    root, monkeypatch,
):
    monkeypatch.setattr(
        postprocess_module, "remove_background", lambda p, log: "done"
    )
    monkeypatch.setattr(
        postprocess_module, "crop_transparent", lambda p, log: "done"
    )
    monkeypatch.setattr(
        aspect_module, "change_aspect", lambda p, w, h, log: "done"
    )
    monkeypatch.setattr(
        gui, "_gate_and_upscale", lambda p, log, conds, params: "done"
    )

    panel = make_panel(root)
    panel.force_aspect_var.set(True)
    post_save, _g = compose(panel)
    assert post_save is not None and not isinstance(post_save, str)
    assert post_save(Path("whatever.png")) == (
        "REMOVE BG: done, CROP: done, ASPECT: done, UPSCALE: done"
    )


def test_compose_post_save_correct_subset_when_some_switches_off(root, monkeypatch):
    monkeypatch.setattr(
        postprocess_module, "remove_background", lambda p, log: "done"
    )
    monkeypatch.setattr(
        aspect_module, "change_aspect", lambda p, w, h, log: "nothing"
    )

    panel = make_panel(root)
    panel.crop_var.set(False)
    panel.upscale_var.set(False)
    panel.force_aspect_var.set(True)
    post_save, _g = compose(panel)
    assert post_save(Path("whatever.png")) == "REMOVE BG: done, ASPECT: nothing"


def test_compose_post_save_byte_identical_output_when_force_aspect_off(
    root, tmp_path,
):
    """CRITICAL non-regression (Phase 8): Force Aspect OFF (the default)
    must produce the SAME final bytes AND the SAME action-string shape
    as a plain BG->Crop sequential call — no JobTemp attached, isolating
    the claim to the step functions/order alone."""
    old_path = tmp_path / "old.png"
    make_white_plate(old_path)
    new_path = tmp_path / "new.png"
    shutil.copy2(old_path, new_path)

    assert postprocess_module.remove_background(old_path, print) == "done"
    assert postprocess_module.crop_transparent(old_path, print) == "done"
    old_bytes = old_path.read_bytes()

    panel = make_panel(root)
    panel.upscale_var.set(False)  # isolate to bg+crop, like the reference above
    assert panel.force_aspect_var.get() is False
    post_save, _g = compose(panel)  # NO JobTemp attached
    action = post_save(new_path)

    assert action == "REMOVE BG: done, CROP: done"  # no "ASPECT:" segment
    assert new_path.read_bytes() == old_bytes


def test_compose_post_save_byte_identical_even_with_a_jobtemp_attached(
    root, tmp_path,
):
    """The NEW per-step JobTemp (Phase 8 plumbing) is purely ADDITIVE —
    attaching one (as _start_site now always does) must never change the
    live file's bytes, only add backup COPIES elsewhere."""
    old_path = tmp_path / "old.png"
    make_white_plate(old_path)
    new_path = tmp_path / "out" / "new.png"
    new_path.parent.mkdir()
    shutil.copy2(old_path, new_path)

    assert postprocess_module.remove_background(old_path, print) == "done"
    assert postprocess_module.crop_transparent(old_path, print) == "done"
    old_bytes = old_path.read_bytes()

    panel = make_panel(root)
    panel.upscale_var.set(False)
    temp = JobTemp("byte-identical-with-temp", new_path.parent)
    post_save, _g = compose(panel, temp=temp)
    action = post_save(new_path)

    assert action == "REMOVE BG: done, CROP: done"
    assert new_path.read_bytes() == old_bytes
    # and the additive part actually happened — backups DO exist
    assert temp.steps_for("new.png") == ["original", "crop"]


def test_compose_post_save_emits_over_cap_event_once_per_run(
    root, tmp_path, monkeypatch,
):
    """The CALLER-level dedup: _compose_post_save's own on_cap wrapper
    (not _run_pipeline_steps itself) fires the '__event__'/over_cap
    message through the queue exactly ONCE, however many times the cap
    is actually hit across many images."""
    monkeypatch.setattr(
        postprocess_module, "remove_background", lambda p, log: "done"
    )
    monkeypatch.setattr(
        postprocess_module, "crop_transparent", lambda p, log: "done"
    )
    monkeypatch.setattr(jobtemp_module, "JOBTEMP_MAX_BYTES", 1)  # over cap immediately

    img1, img2 = tmp_path / "a.png", tmp_path / "b.png"
    make_white_plate(img1)
    shutil.copy2(img1, img2)

    panel = make_panel(root)
    panel.upscale_var.set(False)
    temp = JobTemp("cap-event-test", tmp_path)
    post_save, fake = compose(panel, temp=temp)

    post_save(img1)
    post_save(img2)

    events = []
    while not fake._q.empty():
        events.append(fake._q.get_nowait())
    over_cap_events = [
        e for e in events
        if isinstance(e, tuple) and e[0] == "__event__"
        and e[2].get("type") == "over_cap"
    ]
    assert len(over_cap_events) == 1  # exactly once, not once per image/step


# ---------------------------------------------------------------------
# REAL end-to-end: the actual engine functions, cross-checked against
# calling them directly in the SAME order
# ---------------------------------------------------------------------


def test_end_to_end_pipeline_matches_direct_engine_calls_and_backs_up_every_step(
    root, tmp_path, fake_binary,
):
    rel = "emblem/gemini/mood/Glory.png"
    ref_base = tmp_path / "ref"
    pipe_base = tmp_path / "pipe"
    ref_path = ref_base / rel
    pipe_path = pipe_base / rel
    ref_path.parent.mkdir(parents=True)
    pipe_path.parent.mkdir(parents=True)
    make_white_plate(ref_path)
    shutil.copy2(ref_path, pipe_path)
    pristine_bytes = ref_path.read_bytes()

    # --- reference: the four REAL engine functions, called directly,
    # in the pipeline's OWN order — BG -> Crop -> Aspect -> Upscale —
    # snapshotting each intermediate for the restore_to checks below
    assert postprocess_module.remove_background(ref_path, print) == "done"
    after_bg_bytes = ref_path.read_bytes()
    assert postprocess_module.crop_transparent(ref_path, print) == "done"
    after_crop_bytes = ref_path.read_bytes()
    assert aspect_module.change_aspect(ref_path, 4, 3, print) == "done"
    after_aspect_bytes = ref_path.read_bytes()
    assert upscale_mod.upscale_if_small(
        ref_path, print,
        min_width=200, min_height=200,
        aspect_min=0.0, aspect_max=float("inf"),
    ) == "done"
    reference_bytes = ref_path.read_bytes()

    # --- pipeline: through the REAL GUI orchestration, all four ON,
    # the SAME target ratio and upscale gate as the reference above
    panel = make_panel(root)
    panel.force_aspect_var.set(True)
    panel.force_aspect_w_var.set("4")
    panel.force_aspect_h_var.set("3")
    panel.upscale_filter.set_conditions([])  # no aspect gate, like above
    panel.up_minside_var.set("200")

    temp = JobTemp("gemini-e2e", pipe_base)
    post_save, _g = compose(panel, temp=temp)
    action = post_save(pipe_path)
    assert action == "REMOVE BG: done, CROP: done, ASPECT: done, UPSCALE: done"

    # (a) the final image is BYTE-IDENTICAL to the reference chain
    assert pipe_path.read_bytes() == reference_bytes

    # (b) EXACTLY the expected per-step backups exist under __steps__ —
    # "bg" is absent (deduped into "original", the first enabled step)
    assert temp.steps_for(rel) == ["original", "crop", "aspect", "upscale"]

    # (c) restore_to("original") recovers the RAW pristine bytes
    assert temp.restore_to(rel, step="original") is True
    assert pipe_path.read_bytes() == pristine_bytes

    # (c) restore_to for a MIDDLE step ("crop") recovers the right
    # intermediate — the state right before crop ran, i.e. after BG
    assert temp.restore_to(rel, step="crop") is True
    assert pipe_path.read_bytes() == after_bg_bytes

    # and the other two intermediates are independently confirmed too
    assert temp.restore_to(rel, step="aspect") is True
    assert pipe_path.read_bytes() == after_crop_bytes
    assert temp.restore_to(rel, step="upscale") is True
    assert pipe_path.read_bytes() == after_aspect_bytes


# ---------------------------------------------------------------------
# AgentPanel — force_aspect_var / force_aspect_w_var / force_aspect_h_var
# / keep_all_steps_var
# ---------------------------------------------------------------------


def test_agent_panel_force_aspect_defaults(root):
    panel = make_panel(root)
    assert panel.force_aspect_var.get() is False
    assert panel.force_aspect_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)
    assert panel.keep_all_steps_var.get() is JOBTEMP_KEEP_ALL_STEPS_DEFAULT


def test_agent_panel_force_aspect_ratio_raises_on_bad_value(root):
    panel = make_panel(root)
    panel.force_aspect_w_var.set("not-a-number")
    with pytest.raises(ValueError):
        panel.force_aspect_ratio()


def test_agent_panel_force_aspect_canvas_drag_updates_the_vars(root):
    """Simulates AspectRatioCanvas.on_change (a live drag) — mirrors
    AspectRatioDialog._on_canvas_drag exactly."""
    panel = make_panel(root)
    panel._on_force_aspect_canvas_drag(21, 9)
    assert panel.force_aspect_w_var.get() == "21"
    assert panel.force_aspect_h_var.get() == "9"


def test_agent_panel_force_aspect_typed_reshapes_the_canvas_without_raising(root):
    panel = make_panel(root)
    panel.force_aspect_w_var.set("21")
    panel.force_aspect_h_var.set("9")
    # the trace ran _on_force_aspect_wh_typed -> canvas.set_ratio(21, 9);
    # a wiring bug would surface as an exception propagating out of the
    # trace (AspectRatioCanvas has no public getter to assert against
    # directly, so "no raise" + force_aspect_ratio() below is the proof)
    assert panel.force_aspect_ratio() == (21, 9)


def test_agent_panel_apply_theme_redraws_the_force_aspect_canvas_and_is_registered(
    root,
):
    panel = make_panel(root)
    assert panel in gui.THEME_TOPLEVELS
    panel.apply_theme()  # must not raise


def test_agent_panel_get_settings_round_trips_force_aspect_and_keep_all_steps(root):
    src = make_panel(root)
    src.force_aspect_var.set(True)
    src.force_aspect_w_var.set("4")
    src.force_aspect_h_var.set("3")
    src.keep_all_steps_var.set(False)
    stored = src.get_settings()
    assert stored["force_aspect"] is True
    assert stored["force_aspect_w"] == "4"
    assert stored["force_aspect_h"] == "3"
    assert stored["keep_all_steps"] is False

    dst = make_panel(root)
    dst.apply_settings(stored)
    assert dst.force_aspect_var.get() is True
    assert dst.force_aspect_ratio() == (4, 3)
    assert dst.keep_all_steps_var.get() is False


def test_agent_panel_apply_settings_missing_keys_keep_defaults(root):
    panel = make_panel(root)
    panel.apply_settings({})
    assert panel.force_aspect_var.get() is False
    assert panel.force_aspect_ratio() == (ASPECT_DEFAULT_W, ASPECT_DEFAULT_H)
    assert panel.keep_all_steps_var.get() is JOBTEMP_KEEP_ALL_STEPS_DEFAULT


# ---------------------------------------------------------------------
# DashPanel — the loud, PERSISTENT "over_cap" banner
# ---------------------------------------------------------------------


def test_dash_panel_over_cap_event_shows_a_loud_persistent_banner(root):
    panel = gui.DashPanel(root, "gemini")
    assert panel._cap_banner.winfo_manager() == ""  # hidden at construction

    panel.handle({"type": "over_cap"})
    assert panel._cap_banner.winfo_manager() == "pack"
    assert panel._cap_banner_var.get() == JOBTEMP_CAP_BANNER_TEXT

    # UNLIKE state_var (muted, overwritten by the very next progress
    # event — see JobPanel.set_paused's own docstring), the banner
    # survives further progress events
    panel.handle({"type": "item_retry"})
    assert panel._cap_banner.winfo_manager() == "pack"

    # only a fresh run (reset(), what _start_site calls) hides it again
    panel.reset(active=True, task_total=1, task_themes=1)
    assert panel._cap_banner.winfo_manager() == ""
