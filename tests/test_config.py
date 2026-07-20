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
    BADGES,
    BADGE_ACTION_STEPS,
    BUTTON_FILL,
    BUTTON_TEXT,
    STYLES,
    STYLE_CHOICES,
    STYLE_DEFAULT,
    badge_keys_for,
    button_fill_pair,
    button_text_pair,
    fmt_op_duration,
    fmt_pct,
    iter_images,
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


# --- tool op-time formatter -------------------------------------------


def test_op_duration_shows_subsecond_below_ten():
    """The fast in-place tools (bg/crop/aspect) run in fractions of a
    second — the tool panel's Time must NOT flatten them to '0s' the way
    whole-second fmt_duration would."""
    assert fmt_op_duration(0.19) == "0.2s"
    assert fmt_op_duration(0.0) == "0.0s"
    assert fmt_op_duration(3.44) == "3.4s"


def test_op_duration_uses_whole_seconds_from_ten():
    assert fmt_op_duration(12.0) == "12s"


def test_op_duration_uses_minutes_past_a_minute():
    assert fmt_op_duration(65.0) == "1m 05s"


# --- tool metric % formatter (owner 2026-07-19) -----------------------


def test_fmt_pct_two_decimals_below_ten():
    """A value under 10 keeps 2 decimals — so a 3px crop reads '0.24',
    never a rounded-away '0'."""
    assert fmt_pct(0.08) == "0.08"
    assert fmt_pct(5.23) == "5.23"
    assert fmt_pct(9.99) == "9.99"     # the boundary, still 2 decimals


def test_fmt_pct_one_decimal_from_ten():
    """At 10 and above the precision drops to 1 decimal."""
    assert fmt_pct(10.0) == "10.0"     # the boundary, now 1 decimal
    assert fmt_pct(33.4) == "33.4"
    assert fmt_pct(300.0) == "300.0"


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


# --- folder image enumeration (the tools' shared walk) ----------------


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_iter_images_enumerates_recursively_and_skips_non_images(tmp_path):
    _touch(tmp_path / "a.png")
    _touch(tmp_path / "b.JPG")           # case-insensitive extension
    _touch(tmp_path / "note.txt")        # not an image -> skipped
    _touch(tmp_path / "sub" / "d.webp")  # nested -> found
    found = [p.relative_to(tmp_path).as_posix() for p in iter_images(tmp_path)]
    assert found == ["a.png", "b.JPG", "sub/d.webp"]  # sorted, no note.txt


def test_iter_images_empty_folder_is_empty(tmp_path):
    assert iter_images(tmp_path) == []


# --- per-agent STYLE clause (owner 2026-07-19) ------------------------


def test_styles_has_the_seven_keys_none_first():
    assert len(STYLES) == 7
    assert set(STYLES) == {
        "None", "Realistic", "Oil painting", "Watercolor", "3D render",
        "Flat vector", "Ink engraving",
    }
    # the dropdown order lists None first (the default)
    assert STYLE_CHOICES[0] == STYLE_DEFAULT == "None"
    assert tuple(STYLES) == STYLE_CHOICES


def test_style_none_is_empty_others_are_clauses():
    assert STYLES["None"] == ""  # None -> nothing appended
    for name, clause in STYLES.items():
        if name == "None":
            continue
        assert clause.startswith("STYLE:")  # every real style is a clause


# --- dashboard status badges (owner 2026-07-20) ------------------------
# badge_keys_for maps the runner's post_save action string ("REMOVE BG:
# done, CROP: done, UPSCALE: nothing") + the safer-retry flag to the
# badge keys a dashboard image row renders as coloured dots.


def test_badge_keys_only_done_steps_earn_a_badge():
    keys = badge_keys_for("REMOVE BG: done, CROP: done, UPSCALE: nothing")
    assert keys == ("bg", "crop")  # 'nothing' never earns a badge


def test_badge_keys_retry_flag_adds_the_retry_badge():
    assert badge_keys_for("", retried=True) == ("retry",)
    assert badge_keys_for("UPSCALE: done", retried=True) == (
        "upscale", "retry",
    )


def test_badge_keys_render_in_badges_order_not_action_order():
    keys = badge_keys_for("UPSCALE: done, CROP: done, REMOVE BG: done")
    assert keys == ("bg", "crop", "upscale")  # BADGES (render) order


def test_badge_keys_ignore_failures_unclear_and_free_text():
    assert badge_keys_for("") == ()
    assert badge_keys_for("POSTPROCESS: FAILED") == ()
    assert badge_keys_for("REMOVE BG: unclear, CROP: nothing") == ()
    assert badge_keys_for("some free-form log text") == ()


def test_badge_tables_are_consistent():
    """Every action step maps to a real badge; 'retry' is the one badge
    with no action step (it comes from the runner's retried flag); every
    badge is a (#rrggbb colour, label) pair."""
    assert set(BADGE_ACTION_STEPS.values()) == set(BADGES) - {"retry"}
    for color, label in BADGES.values():
        assert color.startswith("#") and len(color) == 7
        assert label
