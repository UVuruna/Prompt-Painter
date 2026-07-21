"""Upscale gate simplification (GUI rework Phase 6, owner decision
2026-07-21): the old per-agent/standalone four-field gate (min W / min
H / aspect FROM / aspect TO) collapses into ONE min-SIDE spinner plus
an embedded ``FilterEditor``. Three halves:

* ``_upscale_params_from_side_and_filter`` and ``_gate_and_upscale``
  are PURE/Tk-light module-level helpers — no PainterGui, no full app;
* ``_migrate_legacy_upscale_gate`` is a pure dict/number -> dict
  conversion, unit-tested against the owner's REAL shapes (the same
  numbers ``test_settings.py``'s round-trip test carries);
* ``AgentPanel``'s new methods (``upscale_params``/``upscale_
  conditions``/``get_settings``/``apply_settings``) need a real
  (withdrawn) Tk root — same ``tk_root`` fixture ``test_gui_filters.py``
  already established, a small ``AgentPanel`` in a throwaway frame
  (never a full ``PainterGui`` — see that file's own docstring on why
  a SECOND independently created root breaks gui.py's icon cache, and
  the project's "barely Tk-unit-tested by design" convention: a full
  PainterGui construction is verified by screenshot, not pytest).
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import gui
import painter.upscale as upscale_mod
from painter import filters
from painter.config import (
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_KIND_WIDTH,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_MIN_HEIGHT,
    UPSCALE_MIN_SIDE_DEFAULT,
    UPSCALE_MIN_WIDTH,
)


def cond(kind: str, polarity: str, lo: float, hi: float) -> filters.FilterCondition:
    return filters.FilterCondition(kind=kind, polarity=polarity, lo=lo, hi=hi)


# ---------------------------------------------------------------------
# _upscale_params_from_side_and_filter — pure, Tk-free
# ---------------------------------------------------------------------


def test_default_seeded_condition_reproduces_the_old_hardcoded_defaults():
    """The exact regression guard: AgentPanel/UpscaleParamsDialog seed
    ONE Aspect (range) IF condition at [UPSCALE_ASPECT_MIN,
    UPSCALE_ASPECT_MAX] and UPSCALE_MIN_SIDE_DEFAULT — resolving that
    MUST reproduce the byte-identical kwargs the OLD four-field gate's
    shipped defaults produced."""
    seeded = [cond(
        FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF,
        UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX,
    )]
    got = gui._upscale_params_from_side_and_filter(
        UPSCALE_MIN_SIDE_DEFAULT, seeded,
    )
    assert got == {
        "min_width": UPSCALE_MIN_WIDTH,
        "min_height": UPSCALE_MIN_HEIGHT,
        "aspect_min": UPSCALE_ASPECT_MIN,
        "aspect_max": UPSCALE_ASPECT_MAX,
    }


def test_min_side_becomes_both_min_width_and_min_height():
    got = gui._upscale_params_from_side_and_filter(1234, [])
    assert got["min_width"] == 1234
    assert got["min_height"] == 1234


def test_no_aspect_condition_widens_to_zero_inf():
    """The owner removed the aspect row entirely — every ratio
    qualifies for the size gate alone."""
    got = gui._upscale_params_from_side_and_filter(800, [])
    assert got["aspect_min"] == 0.0
    assert got["aspect_max"] == float("inf")


def test_only_non_aspect_conditions_also_widens_to_zero_inf():
    """A stacked Width condition alone (no aspect row) is NOT folded
    into aspect_min/aspect_max — this function only ever resolves the
    aspect band; the Width condition is the CALLER's job to honor via
    filters.matches() (see _gate_and_upscale)."""
    got = gui._upscale_params_from_side_and_filter(
        800, [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100, 5000)],
    )
    assert got["aspect_min"] == 0.0
    assert got["aspect_max"] == float("inf")


def test_if_not_aspect_condition_cannot_be_expressed_so_widens_to_zero_inf():
    """upscale_if_small's aspect_min/aspect_max is a plain [lo, hi]
    containment test with no NOT — an IF-NOT aspect condition cannot be
    folded into it, so this function widens to (0, inf) and leaves
    enforcing the IF-NOT band to the caller's filters.matches() gate
    (never silently applied as if it were IF, root Rule #1)."""
    got = gui._upscale_params_from_side_and_filter(
        800, [cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF_NOT, 0.9, 1.1)],
    )
    assert got["aspect_min"] == 0.0
    assert got["aspect_max"] == float("inf")


def test_aspect_exact_condition_is_honored_same_as_range():
    """filters.py treats Aspect (exact) and Aspect (range) identically
    (a plain lo<=ratio<=hi band) — this function must too."""
    got = gui._upscale_params_from_side_and_filter(
        800, [cond(FILTER_KIND_ASPECT_EXACT, FILTER_POLARITY_IF, 0.98, 1.02)],
    )
    assert got["aspect_min"] == 0.98
    assert got["aspect_max"] == 1.02


def test_first_matching_aspect_condition_wins_when_stacked_with_others():
    """A Width condition BEFORE the aspect one does not stop the aspect
    one from being found; a SECOND aspect condition (an odd but
    possible stack) is ignored — first IF-aspect match wins, documented
    partial behaviour (see the function's own docstring)."""
    got = gui._upscale_params_from_side_and_filter(800, [
        cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100, 5000),
        cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF, 0.7, 0.8),
        cond(FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF, 1.5, 1.6),
    ])
    assert (got["aspect_min"], got["aspect_max"]) == (0.7, 0.8)


# --- cross-check against the REAL engine (painter.upscale) --------------
# proves _upscale_params_from_side_and_filter's kwargs actually drive
# upscale_if_small identically to the old hardcoded-default gate.


def make_png(path: Path, width: int, height: int) -> None:
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    Image.fromarray(arr, mode="RGBA").save(path, "PNG")


@pytest.fixture
def fake_binary(monkeypatch):
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


def test_default_seeded_gate_matches_the_old_default_gate_on_the_real_engine(
    tmp_path, fake_binary,
):
    """test_upscale.py's OWN aspect-tolerance-boundary case (440x400 =
    ratio 1.1, done; 460x400 = ratio 1.15, nothing), re-driven through
    the GUI's new resolution helper instead of upscale_if_small's bare
    defaults — must land on the SAME verdicts."""
    seeded = [cond(
        FILTER_KIND_ASPECT_RANGE, FILTER_POLARITY_IF,
        UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX,
    )]
    params = gui._upscale_params_from_side_and_filter(
        UPSCALE_MIN_SIDE_DEFAULT, seeded,
    )
    inside = tmp_path / "inside.png"
    make_png(inside, 440, 400)
    assert upscale_mod.upscale_if_small(inside, print, **params) == "done"

    outside = tmp_path / "outside.png"
    make_png(outside, 460, 400)
    assert upscale_mod.upscale_if_small(outside, print, **params) == "nothing"


# ---------------------------------------------------------------------
# _gate_and_upscale — the per-image site-pipeline gate (Tk-free)
# ---------------------------------------------------------------------


def test_gate_and_upscale_with_no_conditions_calls_engine_unconditionally(
    tmp_path, monkeypatch,
):
    """Empty conditions = FilterEditor's own 'no filter' contract — no
    extra Image.open, straight through to upscale_if_small."""
    calls = []

    def fake(path, log, **params):
        calls.append((path, params))
        return "done"

    monkeypatch.setattr(upscale_mod, "upscale_if_small", fake)
    img = tmp_path / "x.png"
    make_png(img, 10, 10)
    params = {"min_width": 800, "min_height": 800, "aspect_min": 0, "aspect_max": 1}
    result = gui._gate_and_upscale(img, print, [], params)
    assert result == "done"
    assert calls == [(img, params)]


def test_gate_and_upscale_skips_the_engine_when_filter_fails(tmp_path, monkeypatch):
    """A stacked Width condition the resolved kwargs cannot express —
    the image must be skipped via filters.matches(), upscale_if_small
    NEVER called (root Rule #1: honoring a condition that isn't just
    the aspect one)."""
    calls = []
    monkeypatch.setattr(
        upscale_mod, "upscale_if_small",
        lambda path, log, **params: calls.append(1) or "done",
    )
    img = tmp_path / "narrow.png"
    make_png(img, 50, 50)  # width 50, well under the [500, 5000] band below
    conditions = [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500, 5000)]
    result = gui._gate_and_upscale(img, print, conditions, {})
    assert result == "nothing"
    assert calls == []  # the engine was never reached


def test_gate_and_upscale_runs_the_engine_when_filter_passes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        upscale_mod, "upscale_if_small",
        lambda path, log, **params: calls.append(1) or "done",
    )
    img = tmp_path / "wide.png"
    make_png(img, 1000, 1000)
    conditions = [cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 500, 5000)]
    result = gui._gate_and_upscale(img, print, conditions, {})
    assert result == "done"
    assert calls == [1]


# ---------------------------------------------------------------------
# _migrate_legacy_upscale_gate — pure, Tk-free, the owner's real shapes
# ---------------------------------------------------------------------


def test_migrate_the_owners_real_per_agent_shape():
    """settings.json's real per-agent strings (test_settings.py's own
    fixture data): up_minw="900", up_aspmin="0.85", up_aspmax="1.15"."""
    got = gui._migrate_legacy_upscale_gate("900", "0.85", "1.15")
    assert got == {
        "min_side": 900,
        "conditions": [{
            "kind": FILTER_KIND_ASPECT_RANGE, "polarity": FILTER_POLARITY_IF,
            "lo": 0.85, "hi": 1.15,
        }],
    }


def test_migrate_the_owners_real_standalone_shape():
    """settings.json's real standalone upscale_tool dict (test_settings.py's
    own fixture data): min_width=1000, aspect_min=0.8, aspect_max=1.25
    (min_height=600 is the one intentionally DROPPED value)."""
    got = gui._migrate_legacy_upscale_gate(1000, 0.8, 1.25)
    assert got == {
        "min_side": 1000,
        "conditions": [{
            "kind": FILTER_KIND_ASPECT_RANGE, "polarity": FILTER_POLARITY_IF,
            "lo": 0.8, "hi": 1.25,
        }],
    }
    # and it round-trips through the real deserializer into a condition
    # that reproduces the OLD upscale_if_small(aspect_min=0.8, aspect_max=1.25)
    # gate exactly
    [condition] = [filters.condition_from_dict(d) for d in got["conditions"]]
    resolved = gui._upscale_params_from_side_and_filter(
        got["min_side"], [condition],
    )
    assert resolved == {
        "min_width": 1000, "min_height": 1000,
        "aspect_min": 0.8, "aspect_max": 1.25,
    }


def test_migrate_defaults_are_the_shipped_config_defaults():
    got = gui._migrate_legacy_upscale_gate(
        UPSCALE_MIN_SIDE_DEFAULT, UPSCALE_ASPECT_MIN, UPSCALE_ASPECT_MAX,
    )
    assert got["min_side"] == UPSCALE_MIN_SIDE_DEFAULT
    [d] = got["conditions"]
    assert d["lo"] == UPSCALE_ASPECT_MIN and d["hi"] == UPSCALE_ASPECT_MAX


def test_migrate_unparsable_value_raises_loudly():
    with pytest.raises(ValueError):
        gui._migrate_legacy_upscale_gate("not-a-number", 0.9, 1.1)


def test_migrate_unparsable_aspect_raises_loudly():
    with pytest.raises(ValueError):
        gui._migrate_legacy_upscale_gate(800, "bad", 1.1)


# ---------------------------------------------------------------------
# AgentPanel — real (withdrawn) Tk root, small throwaway parent frame
# ---------------------------------------------------------------------


@pytest.fixture
def root(tk_root):
    return tk_root


def make_panel(root) -> gui.AgentPanel:
    """A bare AgentPanel, parented directly on the shared root (never
    packed/mapped — same convention test_gui_filters.py already uses
    for FilterEditor) with no-op callbacks — never a full PainterGui
    (see this module's docstring)."""
    return gui.AgentPanel(
        root, "gemini",
        on_start=lambda *_a: None, on_stop=lambda *_a: None,
        on_pause=lambda *_a: None,
    )


def test_agent_panel_seeds_the_default_upscale_gate(root):
    panel = make_panel(root)
    assert panel.up_minside_var.get() == str(UPSCALE_MIN_SIDE_DEFAULT)
    [c] = panel.upscale_conditions()
    assert c.kind == FILTER_KIND_ASPECT_RANGE
    assert c.polarity == FILTER_POLARITY_IF
    assert c.lo == UPSCALE_ASPECT_MIN and c.hi == UPSCALE_ASPECT_MAX


def test_agent_panel_upscale_params_matches_old_hardcoded_defaults(root):
    """The REGRESSION guard at the AgentPanel level: a freshly built
    panel's upscale_params() must equal what the OLD four-StringVar
    gate produced by default."""
    panel = make_panel(root)
    assert panel.upscale_params() == {
        "min_width": UPSCALE_MIN_WIDTH,
        "min_height": UPSCALE_MIN_HEIGHT,
        "aspect_min": UPSCALE_ASPECT_MIN,
        "aspect_max": UPSCALE_ASPECT_MAX,
    }


def test_agent_panel_upscale_params_raises_on_bad_min_side(root):
    panel = make_panel(root)
    panel.up_minside_var.set("not-a-number")
    with pytest.raises(ValueError):
        panel.upscale_params()


def test_agent_panel_upscale_params_raises_on_bad_filter_row(root):
    """A row's ValueError (FilterEditor.get_conditions) must propagate
    THROUGH upscale_params() unmodified — Start's try/except relies on
    this to report 'values must be numbers' before spawning a job."""
    panel = make_panel(root)
    panel.upscale_filter._add_default_row()
    panel.upscale_filter._rows[-1].lo_var.set("garbage")
    with pytest.raises(ValueError):
        panel.upscale_params()
    with pytest.raises(ValueError):
        panel.upscale_conditions()


def test_agent_panel_get_settings_carries_min_side_and_conditions(root):
    panel = make_panel(root)
    panel.up_minside_var.set("950")
    data = panel.get_settings()
    assert data["up_minside"] == "950"
    assert data["up_filter_conditions"] == [{
        "kind": FILTER_KIND_ASPECT_RANGE, "polarity": FILTER_POLARITY_IF,
        "lo": UPSCALE_ASPECT_MIN, "hi": UPSCALE_ASPECT_MAX,
    }]


def test_agent_panel_apply_settings_restores_min_side_and_conditions(root):
    src = make_panel(root)
    src.up_minside_var.set("950")
    src.upscale_filter.set_conditions([
        cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100.0, 2000.0),
    ])
    stored = src.get_settings()

    dst = make_panel(root)
    dst.apply_settings(
        stored,
        upscale_conditions=[
            filters.condition_from_dict(d)
            for d in stored["up_filter_conditions"]
        ],
    )
    assert dst.up_minside_var.get() == "950"
    assert dst.upscale_conditions() == [
        cond(FILTER_KIND_WIDTH, FILTER_POLARITY_IF, 100.0, 2000.0),
    ]


def test_agent_panel_apply_settings_with_no_upscale_conditions_keeps_seeded_default(root):
    """Missing/None upscale_conditions (a fresh settings.json, or one
    with nothing usable to migrate) leaves the widget's OWN
    construction-time seeded default untouched — same 'missing key
    keeps the default' contract every other field already has."""
    panel = make_panel(root)
    panel.apply_settings({}, upscale_conditions=None)
    [c] = panel.upscale_conditions()
    assert c.lo == UPSCALE_ASPECT_MIN and c.hi == UPSCALE_ASPECT_MAX
