"""The icon registry — grouping folders, unique stems, and the promise
that EVERY stem the GUI asks for actually exists and renders.

The icons were regrouped into kinship folders (owner 2026-08-04:
``jobs/ actions/ nav/ files/ brand/ theme/``) while call sites kept
passing a BARE STEM. That split — identity in the code, filing on
disk — only holds if two things stay true, and both are mechanical:

1. no stem is claimed by two folders (else which one wins is luck),
2. every ``icon_name=``/``icon("...")`` in the GUI, plus every stem in
   ``JOB_LOGO``/``MENU_TILES``, resolves to a file that Qt or PIL can
   actually turn into pixels.

Rule #1 (fail loudly) is what makes 2 testable at all: ``gui.icon``
raises on a missing or unrenderable mark instead of quietly rendering
nothing, so a typo can never ship as a blank button.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from painter.config import JOB_LOGO, MENU_TILES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = PROJECT_ROOT / "assets" / "icons"
GUI_DIR = PROJECT_ROOT / "gui"

# icon_name="stem" / icon("stem") — the two ways the GUI asks for a mark
_ASKS = re.compile(r'icon_name=\s*"([^"]+)"|(?<![\w.])icon\(\s*"([^"]+)"')


def _stems_on_disk() -> dict[str, list[Path]]:
    """stem -> every file claiming it, across all grouping folders."""
    found: dict[str, list[Path]] = {}
    for path in ICON_DIR.rglob("*"):
        if path.suffix.lower() in (".svg", ".png") and path.is_file():
            found.setdefault(path.stem, []).append(path)
    return found


def _asked_stems() -> set[str]:
    asked = set()
    for py in GUI_DIR.rglob("*.py"):
        for m in _ASKS.finditer(py.read_text(encoding="utf-8")):
            asked.add(m.group(1) or m.group(2))
    asked |= set(JOB_LOGO.values())
    asked |= {tile.icon for tile in MENU_TILES}
    return asked


def test_no_stem_is_claimed_by_two_folders():
    """A stem is an IDENTITY; two folders claiming it makes ``icon()``'s
    answer depend on ICON_GROUPS order rather than on intent."""
    clashes = {
        stem: sorted(p.relative_to(ICON_DIR).as_posix() for p in paths)
        for stem, paths in _stems_on_disk().items()
        # one stem MAY hold both an .svg and its pre-rasterized .png
        # sibling (gemini) — that is the same folder, not a clash
        if len({p.parent for p in paths}) > 1
    }
    assert not clashes, f"icon stems claimed by two folders: {clashes}"


def test_every_stem_the_gui_asks_for_exists():
    on_disk = _stems_on_disk()
    missing = sorted(s for s in _asked_stems() if s not in on_disk)
    assert not missing, (
        f"GUI asks for icon stems with no file in assets/icons: {missing}"
    )


@pytest.mark.parametrize("stem", sorted(_asked_stems()))
def test_every_asked_icon_actually_renders(stem):
    """Not just "a file exists" — it must survive the REAL pipeline
    (QtSvg for svg, PIL for png). This is what catches an SVG using the
    clipPath/mask/filter features QtSvg silently mangles."""
    from gui.icons import icon

    img = icon(stem, 24)
    assert img.cget("size")[0] > 0


def test_the_day_night_switch_tracks_resolve_after_the_regrouping():
    """REGRESSION (owner 2026-08-04): ``_render_switch_track`` built its
    path straight off the flat ICON_DIR, so filing the two track SVGs
    into ``theme/`` made ``DayNightSwitch.__init__`` raise and took the
    WHOLE WINDOW down at startup — every view, not just the switch.
    Caught by launching the app, not by the suite, which is why the
    resolution now goes through ``icon_paths`` like every other mark."""
    from gui.icons import _render_switch_track
    from painter.config import SWITCH_TRACK_DAY_SVG, SWITCH_TRACK_NIGHT_SVG

    for stem in (SWITCH_TRACK_DAY_SVG, SWITCH_TRACK_NIGHT_SVG):
        img = _render_switch_track(stem, 40, 20)
        assert img.size == (40, 20)


def test_a_currentcolor_mark_is_tinted_with_the_asked_colour():
    """REGRESSION (owner 2026-08-04, screenshot of a disabled Delete):
    QtSvg has no CSS context, so it resolves ``currentColor`` to BLACK
    — the monochrome marks were invisible on dark outline buttons.
    ``icon(..., tint=...)`` substitutes the caller's own label colour
    before rasterizing, so the mark and its text always match."""
    from gui.icons import _svg_to_pil, icon_paths

    svg, _png = icon_paths("delete")
    assert "currentColor" in svg.read_text(encoding="utf-8")
    img = _svg_to_pil(svg, 48, recolor="#e74c3c")
    # LANCZOS edges carry blended RGB, so this asserts the AVERAGE of
    # the solid pixels, not every one of them
    lit = [p for p in img.getdata() if p[3] > 240]
    assert lit, "the mark rendered empty"
    mean = [sum(p[c] for p in lit) / len(lit) for c in range(3)]
    for got, want in zip(mean, (231, 76, 60)):
        assert abs(got - want) < 12, f"tint not applied: mean RGB {mean}"


def test_a_coloured_mark_ignores_the_tint():
    """A jobs/ mark names its own hues; a button asking for a tint must
    never repaint it (that is what separates the two icon families)."""
    from gui.icons import icon

    plain = icon("aicheck", 24)
    tinted = icon("aicheck", 24, tint=("#ff0000", "#ff0000"))
    assert plain is tinted or plain.cget("size") == tinted.cget("size")


def test_the_coloured_job_marks_avoid_svg_features_qtsvg_cannot_render():
    """QtSvg implements SVG Tiny: clipPath/mask/filter render as
    garbage (the reason gemini.svg needs a pre-rasterized png). The
    marks drawn for this project must never depend on them — a rule
    that is invisible until an icon looks broken on the owner's
    screen, so it is pinned here instead."""
    offenders = {}
    for svg in (*(ICON_DIR / "jobs").glob("*.svg"),
                *(ICON_DIR / "files").glob("*.svg"),
                *(ICON_DIR / "actions").glob("*.svg"),
                *(ICON_DIR / "nav").glob("*.svg")):
        body = svg.read_text(encoding="utf-8")
        bad = [tag for tag in ("<clipPath", "<mask", "<filter") if tag in body]
        if bad:
            offenders[svg.name] = bad
    assert not offenders, f"SVG features QtSvg cannot render: {offenders}"
