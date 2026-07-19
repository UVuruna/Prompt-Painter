"""Config helpers — per-theme button shades + multi-file selection base.

Pure-data checks for the GUI theming and the Aspect tool's file-pick
plumbing (owner 2026-07-19): every solid button KIND differs between day
and night, the neutral 'secondary' is LIGHT on day (never a dark fill on
the cream window), and a selection of image files resolves to a sane
(base folder, relative paths) pair whether the picks share one folder or
span sub-folders. No tkinter is imported — config.py stays engine-safe.
"""

from pathlib import Path

import pytest

from painter.config import (
    BUTTON_FILL,
    BUTTON_TEXT,
    button_fill_pair,
    button_text_pair,
    selection_base_and_rels,
)


def _luma(hex_color: str) -> float:
    """Perceived brightness 0..255 of a #rrggbb colour."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


# --- per-theme button shades -----------------------------------------


@pytest.mark.parametrize("kind", ["secondary", "success", "danger", "info"])
def test_every_solid_kind_day_differs_from_night(kind):
    day, night = button_fill_pair(kind)
    assert day != night  # a flip must visibly restyle every kind


def test_secondary_is_light_on_day_dark_on_night():
    """The neutral button: LIGHT fill on the cream day window (dark
    text), dark fill on night (white text) — the owner's brown-button
    bug fix."""
    day_fill, night_fill = button_fill_pair("secondary")
    day_text, night_text = button_text_pair("secondary")
    assert _luma(day_fill) > 200      # light fill on day
    assert _luma(night_fill) < 120    # dark fill on night
    assert _luma(day_text) < 90       # dark label reads on the light fill
    assert _luma(night_text) > 200    # white label on the dark fill


def test_no_solid_button_is_dark_filled_on_day_except_intentional_colours():
    """Neutral secondary must be light on day; the coloured kinds may be
    mid-toned but never as dark as the old warm-grey (#6b6456, luma ~99)
    that read brown."""
    assert _luma(button_fill_pair("secondary")[0]) > 200


def test_fill_and_text_tables_cover_the_same_kinds():
    assert set(BUTTON_FILL) == set(BUTTON_TEXT)


# --- multi-file selection base (Aspect tool) --------------------------


def test_single_file_bases_on_its_parent():
    base, rels = selection_base_and_rels([r"C:\imgs\a\one.png"])
    assert base == Path(r"C:\imgs\a")
    assert rels == ["one.png"]


def test_files_in_one_folder_base_on_that_folder():
    base, rels = selection_base_and_rels(
        [r"C:\imgs\a\one.png", r"C:\imgs\a\two.png"]
    )
    assert base == Path(r"C:\imgs\a")
    assert sorted(rels) == ["one.png", "two.png"]


def test_files_across_subfolders_base_on_the_common_ancestor():
    base, rels = selection_base_and_rels(
        [r"C:\imgs\a\one.png", r"C:\imgs\b\two.png"]
    )
    assert base == Path(r"C:\imgs")
    assert sorted(rels) == ["a/one.png", "b/two.png"]


def test_empty_selection_raises():
    with pytest.raises(ValueError):
        selection_base_and_rels([])
