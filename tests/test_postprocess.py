"""The split postprocess steps (owner's #7) — synthetic images.

``remove_background`` and ``crop_transparent`` are separate,
composable, in-place, and never raise for a no-op.
"""

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from painter.bg_remove import (
    apply_plan,
    clean_edge_halo,
    content_bbox,
    corner_background_color,
    parse_hex_color,
    plan,
    tolerance_to_distance,
)
from painter.config import (
    AUTO_CORNER_AGREE_MAX,
    AUTO_CORNER_PX,
    BG_COLOR_TOLERANCE_PCT,
    BG_MODE_BLACK,
    BG_MODE_COLOR,
    BG_MODE_WHITE,
    BG_REACH_ALL,
    BG_REACH_EDGE,
    CLEAN_EDGE_ALPHA,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
    SAFETY_MAX_REMOVE_FRAC,
)
from painter.postprocess import (
    PostprocessError,
    crop_transparent,
    remove_background,
)

# The real diagnosed image (owner 2026-07-18): ChatGPT delivered it
# ~54% transparent with faint stray pixels (alpha ~8-32) hugging the
# far-left column, which defeated the old single-threshold autocrop.
OLDAGE_PNG = (
    Path(__file__).resolve().parents[1]
    / "out" / "archetype" / "chatgpt" / "life" / "tree" / "OldAge.png"
)


def save_rgba(path: Path, arr: np.ndarray) -> None:
    Image.fromarray(arr, mode="RGBA").save(path, "PNG")


def make_white_plate(path: Path, size: int = 100) -> None:
    """A red subject FILLING a pure-white plate (the Gemini case).

    The subject fills the frame with only a thin white border, so the
    removal clears ~29% (border-connected white) — under the SAFETY
    guard. Real assets are medallions that fill the frame; a tiny
    subject on a huge white plate would (correctly) trip the guard."""
    rgb = np.full((size, size, 3), 255, dtype=np.uint8)
    rgb[8:size - 8, 8:size - 8] = (200, 30, 30)
    Image.fromarray(rgb, mode="RGB").save(path, "PNG")


# --- remove_background ------------------------------------------------


def test_white_background_cleared(tmp_path):
    img = tmp_path / "plate.png"
    make_white_plate(img)
    logs: list[str] = []

    assert remove_background(img, logs.append) == "done"
    with Image.open(img) as out:
        arr = np.asarray(out.convert("RGBA"))
    assert arr[0, 0, 3] == 0  # the white corner went transparent
    assert arr[50, 50, 3] == 255  # the subject stayed opaque
    # split contract: remove_background does NOT crop any more
    assert arr.shape[:2] == (100, 100)


def test_black_bright_subject_on_black_is_cleared(tmp_path):
    """A bright subject FILLING the frame on black: the border-connected
    void is cleared, the subject stays opaque, removal is 'done'."""
    img = tmp_path / "globe.png"
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)  # black background
    rgb[8:92, 8:92] = 200                          # bright subject fills frame
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")

    assert remove_background(img, print) == "done"
    with Image.open(img) as out:
        arr = np.asarray(out.convert("RGBA"))
    assert arr[2, 2, 3] == 0        # the black corner void went transparent
    assert arr[50, 50, 3] == 255    # the subject stayed opaque
    assert arr.shape[:2] == (100, 100)


def test_black_removal_keeps_enclosed_interior_dark_region():
    """BORDER-CONNECTED black removal: the corner void is cleared, but a
    dark region ENCLOSED by the subject (the black leading between glass,
    the dark frame) is NOT border-connected and stays fully OPAQUE —
    the exact bug the fix cures (the old disc ate it)."""
    rgb = np.full((100, 100, 3), 180, dtype=np.uint8)  # bright subject fills frame
    rgb[:12, :12] = 0        # black corner void — CONNECTED to the border
    rgb[45:55, 45:55] = 0    # black interior detail — ENCLOSED by the subject
    # forced black: this plate's border is mostly BRIGHT, so auto would
    # (correctly) call it ambiguous — the mode selector is what reaches
    # the black recipe here
    img = Image.fromarray(rgb, mode="RGB")
    out, removed = apply_plan(img, plan(img, BG_MODE_BLACK))
    alpha = np.asarray(out)[:, :, 3]

    assert alpha[3, 3] == 0            # the corner void is cleared
    assert alpha[50, 50] == 255        # the ENCLOSED interior black is kept opaque
    assert removed < 0.05              # only the tiny corner (~1.4%) is removed


def test_guard_aborts_black_over_removal_and_leaves_untouched(tmp_path):
    """A tiny bright subject on a huge black void: the removal would
    clear >guard of the image (it 'ate the subject'), so remove_background
    ABORTS — returns 'unclear', leaves the original byte-identical, logs."""
    img = tmp_path / "dark.png"
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)  # mostly black void
    rgb[42:58, 42:58] = 220                        # tiny bright subject
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")
    before = img.read_bytes()
    logs: list[str] = []

    assert remove_background(img, logs.append) == "unclear"
    assert img.read_bytes() == before               # ORIGINAL untouched
    # the report NAMES the guard that fired and where to raise it
    assert any("black safety guard" in line for line in logs)


def test_white_guard_passes_legit_large_background(tmp_path):
    """The white guard runs HIGH: a real badge on a white margin clears
    ~54% of CLEAN white background with the subject fully intact — that
    must still be "done", not a false bail. (A shared 0.40 guard would
    have wrongly aborted it; measured real white plates reach ~0.57.)"""
    img = tmp_path / "badge_on_white.png"
    rgb = np.full((100, 100, 3), 255, dtype=np.uint8)  # white plate
    rgb[16:84, 16:84] = (60, 90, 160)                  # subject ~46% -> ~54% bg
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")

    assert remove_background(img, print) == "done"
    with Image.open(img) as out:
        arr = np.asarray(out.convert("RGBA"))
    assert arr[0, 0, 3] == 0        # white corner cleared
    assert arr[50, 50, 3] == 255    # subject intact


def test_guard_aborts_white_over_removal_and_leaves_untouched(tmp_path):
    """The guard is general — the white path also aborts, but only on a
    CATASTROPHIC removal: a tiny dark subject on a huge white plate
    clears ~97% (it ate the image), well over the white guard."""
    img = tmp_path / "tiny_on_white.png"
    rgb = np.full((100, 100, 3), 255, dtype=np.uint8)  # huge white plate
    rgb[46:54, 46:54] = (30, 30, 30)                   # tiny dark subject (~0.6%)
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")
    before = img.read_bytes()
    logs: list[str] = []

    assert remove_background(img, logs.append) == "unclear"
    assert img.read_bytes() == before
    assert any("white safety guard" in line for line in logs)


def test_black_removal_returns_removed_fraction():
    """The remove_* contract is (rgba, removed_frac) — the fraction the
    removal clears, which the guard checks. A clean bright-on-black frame
    clears ~the border ring, well under the guard."""
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    rgb[10:90, 10:90] = 210                       # 80x80 subject, 20px frame gone
    img = Image.fromarray(rgb, mode="RGB")
    out, removed = apply_plan(img, plan(img))
    assert isinstance(removed, float)
    assert abs(removed - 0.36) < 0.02             # (100^2 - 80^2)/100^2 = 0.36
    assert removed < SAFETY_MAX_REMOVE_FRAC        # so it would be saved


def test_already_transparent_is_nothing(tmp_path):
    img = tmp_path / "done.png"
    arr = np.zeros((50, 50, 4), dtype=np.uint8)
    arr[10:40, 10:40] = (90, 120, 200, 255)
    save_rgba(img, arr)
    before = img.read_bytes()

    assert remove_background(img, print) == "nothing"
    assert img.read_bytes() == before  # untouched


def make_corner_gradient(size: int = 60) -> np.ndarray:
    """A frame whose four CORNERS hold four different colours — the
    only thing auto still refuses (owner 2026-07-28)."""
    yy, xx = np.mgrid[0:size, 0:size]
    rgb = np.dstack([
        (xx * 255 // (size - 1)).astype(np.uint8),
        (yy * 255 // (size - 1)).astype(np.uint8),
        np.full((size, size), 90, dtype=np.uint8),
    ])
    rgb[20:40, 20:40] = (250, 250, 40)
    return rgb


def test_ambiguous_background_is_unclear_and_untouched(tmp_path):
    """Auto gives up ONLY when even the corners disagree."""
    img = tmp_path / "gradient.png"
    Image.fromarray(make_corner_gradient(), mode="RGB").save(img, "PNG")
    before = img.read_bytes()
    logs: list[str] = []

    assert remove_background(img, logs.append) == "unclear"
    assert img.read_bytes() == before
    assert any("UNCLEAR" in line for line in logs)
    assert any("corners disagree" in line for line in logs)


def test_safety_override_lets_a_larger_removal_through(tmp_path):
    """GUI rework Phase 13: safety_max_remove_frac is a REAL per-call
    override, not silently ignored — the SAME image the default guard
    aborts on ('unclear') is accepted ('done') once the caller raises
    the ceiling above the measured removal (~0.974 here)."""
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)  # mostly black void
    rgb[42:58, 42:58] = 220                        # tiny bright subject

    img = tmp_path / "dark.png"
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")
    assert remove_background(img, print) == "unclear"  # default guard aborts

    img2 = tmp_path / "dark2.png"
    Image.fromarray(rgb, mode="RGB").save(img2, "PNG")
    assert remove_background(
        img2, print, safety_max_remove_frac=0.995,
    ) == "done"


# --- background MODE + custom colour (owner 2026-07-28) ---------------


def make_disc_on_black(path: Path, size: int = 100, radius: int = 43) -> None:
    """A bright disc CENTRED on a pure-black plate — the owner's
    'pointers' geometry in miniature.

    A disc of radius 43 in a 100x100 frame leaves ~42 % background,
    which is what the real plates measure (41.2–42.2 % over all 17
    files in C:\\Users\\vurun\\Downloads\\pointers, 2026-07-28): the
    subject is intact and the separation is perfectly clean (the mask
    moves < 0.6 pp while the void threshold sweeps 2 -> 20), yet the
    fraction sits just above black's 0.40 guard."""
    yy, xx = np.mgrid[0:size, 0:size]
    centre = (size - 1) / 2.0
    disc = (xx - centre) ** 2 + (yy - centre) ** 2 <= radius ** 2
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    rgb[disc] = (210, 180, 90)
    Image.fromarray(rgb, mode="RGB").save(path, "PNG")


def test_hex_colour_parsing_accepts_the_owner_forms():
    assert parse_hex_color("#FF0000") == (255, 0, 0)
    assert parse_hex_color("ff0000") == (255, 0, 0)
    assert parse_hex_color("#f00") == (255, 0, 0)
    assert parse_hex_color("  #3A5F7D  ") == (58, 95, 125)


def test_a_mistyped_hex_colour_is_loud():
    """Rule #1 — a bad colour never silently becomes some other colour."""
    for bad in ("", "#12345", "not-a-colour", "#GGGGGG"):
        with pytest.raises(ValueError, match="background color"):
            parse_hex_color(bad)


def test_tolerance_matches_the_owners_worked_example():
    """'#FF0000 +- X%' spanning #EE0000..#FF1111 is +-0x11 = 17 levels."""
    assert tolerance_to_distance(6.67) == 17
    assert tolerance_to_distance(0) == 0
    assert tolerance_to_distance(100) == 255
    with pytest.raises(ValueError, match="background tolerance"):
        tolerance_to_distance(101)


def test_custom_colour_clears_a_background_neither_white_nor_black(tmp_path):
    """The owner's question answered: ANY colour, not just black/white."""
    img = tmp_path / "red_bg.png"
    rgb = np.full((100, 100, 3), (255, 0, 0), dtype=np.uint8)
    rgb[20:80, 20:80] = (40, 90, 200)
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")

    assert remove_background(
        img, print, mode=BG_MODE_COLOR, color="#FF0000",
    ) == "done"
    with Image.open(img) as out:
        arr = np.asarray(out.convert("RGBA"))
    assert arr[0, 0, 3] == 0      # the red background went transparent
    assert arr[50, 50, 3] == 255  # the subject stayed opaque


def test_zero_tolerance_keys_exactly_the_stated_colour():
    """Owner 2026-07-28 — "MOZE i 0 TOLERANCE ... tj samo taj HEX".
    At 0 %, a background one level off the target is NOT background."""
    rgb = np.full((60, 60, 3), (255, 0, 0), dtype=np.uint8)
    rgb[20:40, 20:40] = (40, 90, 200)
    exact = Image.fromarray(rgb, mode="RGB")

    _, removed = apply_plan(exact, plan(
        exact, BG_MODE_COLOR, color="#FF0000", tolerance_pct=0.0,
    ))
    assert removed > 0.5                      # the exact colour clears

    rgb_off = rgb.copy()
    rgb_off[rgb_off[:, :, 0] == 255] = (254, 0, 0)   # ONE level off
    off = Image.fromarray(rgb_off, mode="RGB")
    _, removed_off = apply_plan(off, plan(
        off, BG_MODE_COLOR, color="#FF0000", tolerance_pct=0.0,
    ))
    assert removed_off == 0.0                 # nothing matches exactly


# --- AUTO colour: the four-corner vote (owner 2026-07-28) -------------


def test_auto_detects_the_colour_the_four_corners_agree_on(tmp_path):
    """The owner's own rule: if the four corners hold the same colour,
    THAT is the background — no longer a give-up."""
    img = tmp_path / "teal_bg.png"
    rgb = np.full((100, 100, 3), (58, 95, 125), dtype=np.uint8)
    rgb[20:80, 20:80] = (240, 200, 60)
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")
    logs: list[str] = []

    assert remove_background(img, logs.append) == "done"
    with Image.open(img) as out:
        arr = np.asarray(out.convert("RGBA"))
    assert arr[0, 0, 3] == 0
    assert arr[50, 50, 3] == 255
    # an auto-DECIDED colour is never silent — it says which (Rule #1)
    assert any("auto-detected" in line and "#3A5F7D" in line
               for line in logs)


def test_corner_vote_ignores_a_subject_that_touches_an_edge():
    """Why CORNERS and not the border band: a subject running to the
    top edge drags the border median, but leaves all four corners on
    the true background colour."""
    rgb = np.full((100, 100, 3), (58, 95, 125), dtype=np.uint8)
    rgb[0:60, 30:70] = (240, 200, 60)   # touches the TOP edge
    assert corner_background_color(rgb) == (58, 95, 125)


def test_corner_vote_refuses_when_the_corners_disagree():
    assert corner_background_color(make_corner_gradient()) is None


def test_corner_vote_tolerates_slight_corner_noise():
    """Real plates are not mathematically flat — corners within
    AUTO_CORNER_AGREE_MAX still count as agreeing."""
    rgb = np.full((100, 100, 3), 120, dtype=np.uint8)
    rgb[:AUTO_CORNER_PX, :AUTO_CORNER_PX] = 120 + AUTO_CORNER_AGREE_MAX - 1
    assert corner_background_color(rgb) is not None

    rgb[:AUTO_CORNER_PX, :AUTO_CORNER_PX] = 120 + AUTO_CORNER_AGREE_MAX + 1
    assert corner_background_color(rgb) is None


# --- REACH: border-connected vs everywhere (owner 2026-07-28) --------


def make_letter_o(size: int = 100) -> np.ndarray:
    """A ring on a black plate — the 'O' of HOPE in miniature. Its
    COUNTER (the hole) is pure #000000, exactly like the background,
    but enclosed by the stroke."""
    yy, xx = np.mgrid[0:size, 0:size]
    c = (size - 1) / 2.0
    r2 = (xx - c) ** 2 + (yy - c) ** 2
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    rgb[(r2 <= 40 ** 2) & (r2 >= 25 ** 2)] = (200, 200, 255)
    return rgb


def test_edge_reach_keeps_the_black_enclosed_by_a_letter():
    """Why the counters of HOPE / SALVATION survive: the flood fill
    walks INWARD FROM THE FRAME, and the hole is not reachable through
    the stroke — same colour, not connected."""
    img = Image.fromarray(make_letter_o(), mode="RGB")
    out, _ = apply_plan(img, plan(img, BG_MODE_BLACK), BG_REACH_EDGE)
    alpha = np.asarray(out)[:, :, 3]

    assert alpha[2, 2] == 0        # outer void cleared
    assert alpha[50, 50] == 255    # the COUNTER stays fully opaque
    assert alpha[50, 18] == 255    # the stroke stays


def test_all_reach_removes_the_same_colour_wherever_it_sits():
    """The owner's added option: no connectivity test, so the counter
    goes too and the letter is left as an outline."""
    img = Image.fromarray(make_letter_o(), mode="RGB")
    out, _ = apply_plan(img, plan(img, BG_MODE_BLACK), BG_REACH_ALL)
    alpha = np.asarray(out)[:, :, 3]

    assert alpha[2, 2] == 0        # outer void cleared
    assert alpha[50, 50] == 0      # the COUNTER cleared too
    assert alpha[50, 18] == 255    # the stroke still stands


def test_all_reach_removes_at_least_as_much_as_edge_reach():
    img = Image.fromarray(make_letter_o(), mode="RGB")
    removal = plan(img, BG_MODE_BLACK)
    _, edge = apply_plan(img, removal, BG_REACH_EDGE)
    _, everywhere = apply_plan(img, removal, BG_REACH_ALL)
    assert everywhere > edge


def test_reach_reaches_the_engine_through_remove_background(tmp_path):
    img = tmp_path / "o.png"
    Image.fromarray(make_letter_o(), mode="RGB").save(img, "PNG")
    # "everywhere" clears MORE by construction, so it meets the guard
    # sooner — a deliberate choice the guard cannot distinguish from an
    # eaten subject, so it is the owner's to raise (the abort message
    # names it). Here the plate is 70 % background.
    assert remove_background(
        img, print, mode=BG_MODE_BLACK, reach=BG_REACH_ALL,
        safety_max_remove_frac=0.80,
    ) == "done"
    with Image.open(img) as out:
        assert np.asarray(out.convert("RGBA"))[50, 50, 3] == 0


def test_reach_all_meeting_the_guard_is_reported_not_silent(tmp_path):
    """Rule #1 — switching to 'everywhere' can push a normal plate over
    the guard; that must be a named report, never a silent no-op."""
    img = tmp_path / "o.png"
    Image.fromarray(make_letter_o(), mode="RGB").save(img, "PNG")
    logs: list[str] = []

    assert remove_background(
        img, logs.append, mode=BG_MODE_BLACK, reach=BG_REACH_ALL,
    ) == "unclear"
    assert any("black safety guard" in line for line in logs)


def test_auto_colour_never_overrides_the_white_or_black_sniff(tmp_path):
    """The corner vote is strictly a FALLBACK — everything white/black
    detection already recognised keeps its own recipe (and its own
    guard), so the pointers plates still take the black path."""
    img = tmp_path / "disc.png"
    make_disc_on_black(img)
    with Image.open(img) as im:
        assert plan(im).action == BG_MODE_BLACK


def test_custom_colour_tolerance_bounds_what_counts_as_background():
    """+- X % is a per-channel box around the target: #EE0000 is inside
    #FF0000 +- 6.67 % and outside +- 1 %."""
    rgb = np.full((60, 60, 3), (238, 0, 0), dtype=np.uint8)  # #EE0000
    rgb[20:40, 20:40] = (40, 90, 200)
    img = Image.fromarray(rgb, mode="RGB")

    wide = plan(img, BG_MODE_COLOR, color="#FF0000", tolerance_pct=6.67)
    _, removed_wide = apply_plan(img, wide)
    assert removed_wide > 0.5          # the #EE0000 plate IS background

    tight = plan(img, BG_MODE_COLOR, color="#FF0000", tolerance_pct=1.0)
    _, removed_tight = apply_plan(img, tight)
    assert removed_tight == 0.0        # 17 levels away — out of the box


def test_forced_mode_skips_the_border_sniff(tmp_path):
    """Auto is a GUESS the owner can now overrule: a plate whose border
    is mostly bright reads 'ambiguous' in auto, and clears in forced
    black."""
    rgb = np.full((100, 100, 3), 180, dtype=np.uint8)
    rgb[:12, :12] = 0                      # a black corner only
    img = Image.fromarray(rgb, mode="RGB")

    assert plan(img).action == "skip-ambiguous"
    assert plan(img, BG_MODE_BLACK).action == BG_MODE_BLACK
    assert plan(img, BG_MODE_WHITE).action == BG_MODE_WHITE


def test_already_transparent_is_skipped_in_every_mode(tmp_path):
    """Re-running a folder stays safe even with a forced mode — an
    existing alpha channel is never overwritten by a colour key."""
    img = tmp_path / "done.png"
    arr = np.zeros((50, 50, 4), dtype=np.uint8)
    arr[10:40, 10:40] = (90, 120, 200, 255)
    save_rgba(img, arr)
    before = img.read_bytes()

    for mode in (BG_MODE_BLACK, BG_MODE_WHITE, BG_MODE_COLOR):
        assert remove_background(img, print, mode=mode) == "nothing"
        assert img.read_bytes() == before


def test_unclear_report_names_the_sniffed_border_colour(tmp_path):
    """Rule #1 — the report must be ACTIONABLE: it names the colour it
    saw, not just 'I gave up'."""
    img = tmp_path / "gradient.png"
    Image.fromarray(make_corner_gradient(), mode="RGB").save(img, "PNG")
    logs: list[str] = []

    assert remove_background(img, logs.append) == "unclear"
    assert any("border ≈ #" in line for line in logs)


def test_a_mistyped_colour_stops_the_run_before_the_image_is_read(tmp_path):
    missing = tmp_path / "not-even-there.png"
    with pytest.raises(ValueError, match="background color"):
        remove_background(missing, print, mode=BG_MODE_COLOR, color="nope")


def test_pointers_regression_black_guard_bails_custom_colour_succeeds(tmp_path):
    """REGRESSION (owner 2026-07-28, the 'pointers' folder). A disc on a
    pure-black plate whose LEGITIMATE background is ~42 %: black's 0.40
    guard — tuned for medallions that FILL the frame — bails on it even
    though the separation is perfect. Stating the colour is the way
    through, and the abort message must say WHICH guard fired so the
    owner can find the knob."""
    img = tmp_path / "disc.png"
    make_disc_on_black(img)
    shutil.copy(img, tmp_path / "disc2.png")
    before = img.read_bytes()
    logs: list[str] = []

    # auto -> black path -> ~42 % > 0.40 -> bail, ORIGINAL untouched
    assert remove_background(img, logs.append) == "unclear"
    assert img.read_bytes() == before
    assert any("black safety guard" in line for line in logs)
    assert any("40%" in line for line in logs)

    # the owner states the colour: the custom guard (0.85) lets the
    # SAME clean removal through
    assert remove_background(
        tmp_path / "disc2.png", print, mode=BG_MODE_COLOR, color="#000000",
    ) == "done"
    with Image.open(tmp_path / "disc2.png") as out:
        arr = np.asarray(out.convert("RGBA"))
    assert arr[0, 0, 3] == 0        # the black corner went transparent
    assert arr[50, 50, 3] == 255    # the disc stayed opaque


def test_black_default_tolerance_matches_the_black_recipe():
    """A custom removal at #000000 IS a tunable black removal — which
    is why the black path needs no tolerance knob of its own (Rule
    #19). At the tolerance that reproduces BLACK_VOID_MAX they agree."""
    rgb = np.zeros((80, 80, 3), dtype=np.uint8)
    rgb[10:70, 10:70] = 200
    img = Image.fromarray(rgb, mode="RGB")

    black = plan(img, BG_MODE_BLACK)
    same = plan(
        img, BG_MODE_COLOR, color="#000000",
        tolerance_pct=black.dist_edge / 255.0 * 100.0,
    )
    assert same.dist_edge == black.dist_edge
    assert np.array_equal(
        np.asarray(apply_plan(img, same)[0]),
        np.asarray(apply_plan(img, black)[0]),
    )


def test_default_tolerance_is_a_usable_black_key():
    """The shipped default (BG_COLOR_TOLERANCE_PCT) must actually key a
    pure-black background, not sit below its anti-alias tail."""
    assert tolerance_to_distance(BG_COLOR_TOLERANCE_PCT) >= 14


def test_real_errors_are_loud(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"this is not a png")
    with pytest.raises(PostprocessError):
        remove_background(broken, print)
    with pytest.raises(PostprocessError):
        crop_transparent(broken, print)


# --- crop_transparent -------------------------------------------------


def test_crop_shrinks_to_the_content_box_plus_margin(tmp_path):
    img = tmp_path / "sparse.png"
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[40:60, 40:60] = (255, 0, 0, 255)  # 20x20 content island
    save_rgba(img, arr)

    assert crop_transparent(img, print) == "done"
    with Image.open(img) as out:
        # 20px content + the safety margin on each side
        expected = 20 + 2 * CROP_MARGIN_PX
        assert out.size == (expected, expected)
        assert np.asarray(out)[:, :, 3].max() == 255  # content kept

    # a second pass finds it already tight
    assert crop_transparent(img, print) == "nothing"


def test_crop_zero_px_change_is_nothing_byte_unchanged(tmp_path):
    """SKIPPED iff the output resolution EQUALS the input (owner
    2026-07-19). A content box whose +margin lands exactly on the full
    frame is a 0px change: "nothing", file byte-unchanged (no rewrite,
    no restore point)."""
    img = tmp_path / "full.png"
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    # content (2,2,98,98) + the 4px margin clamps to (0,0,100,100) = the
    # whole frame -> output size == input size -> no crop.
    arr[2:98, 2:98] = (200, 50, 50, 255)
    save_rgba(img, arr)
    before = img.read_bytes()
    assert crop_transparent(img, print) == "nothing"
    assert img.read_bytes() == before  # a 0px change is never written


def test_crop_one_px_change_is_done(tmp_path):
    """CHANGED iff ANY dimension differs by >= 1px (owner 2026-07-19,
    reverses the old <=2px slop skip). A box + margin that trims exactly
    ONE pixel off one side IS a crop -> "done", output 1px smaller."""
    img = tmp_path / "onepx.png"
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    # content columns 5..99 over all rows: ink box (5,0,100,100), + the
    # 4px margin -> (1,0,100,100) -> exactly 1px off the LEFT, nothing
    # else -> 99x100.
    arr[:, 5:100] = (200, 50, 50, 255)
    save_rgba(img, arr)
    assert crop_transparent(img, print) == "done"
    with Image.open(img) as out:
        assert out.size == (99, 100)  # exactly 1px trimmed


def test_crop_meaningful_trim_still_done(tmp_path):
    """A multi-pixel trim on every side is, of course, a real crop."""
    img = tmp_path / "real.png"
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[30:70, 30:70] = (200, 50, 50, 255)  # 40x40 -> trims ~26px/side
    save_rgba(img, arr)
    assert crop_transparent(img, print) == "done"
    with Image.open(img) as out:
        assert out.size == (40 + 2 * CROP_MARGIN_PX, 40 + 2 * CROP_MARGIN_PX)


def test_crop_on_opaque_image_is_nothing(tmp_path):
    img = tmp_path / "opaque.png"
    arr = np.full((40, 40, 4), 255, dtype=np.uint8)
    save_rgba(img, arr)
    before = img.read_bytes()
    assert crop_transparent(img, print) == "nothing"
    assert img.read_bytes() == before


def test_crop_on_fully_transparent_image_is_nothing(tmp_path):
    img = tmp_path / "empty.png"
    save_rgba(img, np.zeros((40, 40, 4), dtype=np.uint8))
    assert crop_transparent(img, print) == "nothing"


def test_margin_clamps_at_the_image_edge(tmp_path):
    img = tmp_path / "corner.png"
    arr = np.zeros((50, 50, 4), dtype=np.uint8)
    arr[0:10, 0:10] = (0, 255, 0, 255)  # content touching the corner
    save_rgba(img, arr)
    assert crop_transparent(img, print) == "done"
    with Image.open(img) as out:
        assert out.size == (10 + CROP_MARGIN_PX, 10 + CROP_MARGIN_PX)


def test_crop_margin_px_override_changes_the_output_size(tmp_path):
    """GUI rework Phase 13: crop_margin_px is a REAL per-call override
    — the same content box crops tighter with margin=0 than with the
    config default."""
    img = tmp_path / "margin0.png"
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[40:70, 40:70] = (200, 30, 30, 255)  # 30x30 solid content
    save_rgba(img, arr)
    assert crop_transparent(img, print, crop_margin_px=0) == "done"
    with Image.open(img) as out:
        assert out.size == (30, 30)  # exactly the content box, no margin


def test_crop_clean_edge_enable_false_keeps_a_border_faint_pixel(tmp_path):
    """GUI rework Phase 13: clean_edge_enable=False is a REAL override
    — a border-connected FAINT (sub-ink) pixel sitting just inside the
    eventual crop box survives at its original alpha when disabled,
    but is zeroed by the default (True). The pixel is deliberately
    below CROP_INK_ALPHA so content_bbox's own box is IDENTICAL either
    way — only the SAVED PIXELS differ."""
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[40:70, 40:70] = (200, 30, 30, 255)   # solid 30x30 subject
    faint = CLEAN_EDGE_ALPHA - 10
    # just inside the eventual crop box's top-left corner: content box
    # (40,40,70,70) + CROP_MARGIN_PX(4) margin -> (36,36,74,74)
    arr[36, 36, 3] = faint

    on = tmp_path / "halo_on.png"
    save_rgba(on, arr)
    assert crop_transparent(on, print) == "done"
    with Image.open(on) as out:
        assert np.asarray(out)[0, 0, 3] == 0  # cleaned by the default

    off = tmp_path / "halo_off.png"
    save_rgba(off, arr)
    assert crop_transparent(off, print, clean_edge_enable=False) == "done"
    with Image.open(off) as out2:
        assert np.asarray(out2)[0, 0, 3] == faint  # survives, override honored


# --- ink-based bbox + border-halo cleanup (the OldAge.png fix) --------


def test_ink_bbox_ignores_a_faint_stray_border_line():
    """A faint 1px stray line must NOT extend the content box."""
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[40:60, 40:60, 3] = 255                 # solid 20x20 subject
    arr[:, 0, 3] = CROP_INK_ALPHA - 20         # faint far-left line
    box = content_bbox(Image.fromarray(arr, "RGBA"))
    assert box == (40, 40, 60, 60)             # the sparse faint line is ignored


def test_edge_cleanup_zeroes_border_line_keeps_interior_soft_edge():
    """Border-connected faint pixels are erased; interior soft edges
    (enclosed by the solid subject) are preserved."""
    faint = CLEAN_EDGE_ALPHA - 15
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[30:70, 30:70, 3] = 255                 # solid subject body
    arr[45:55, 45:55, 3] = faint               # interior faint blob (enclosed)
    arr[:, 0, 3] = faint                       # faint far-left border line
    cleaned, n = clean_edge_halo(Image.fromarray(arr, "RGBA"))
    out = np.asarray(cleaned)[:, :, 3]
    assert (out[:, 0] == 0).all()              # the border line is erased
    assert (out[45:55, 45:55] == faint).all()  # interior soft edge preserved
    assert n == 100                            # exactly the 100 line pixels


def test_crop_ignores_faint_line_and_tightens_to_the_subject(tmp_path):
    """crop_transparent: the faint stray line neither defeats the crop
    nor survives it — the box tightens to the real subject."""
    img = tmp_path / "stray.png"
    arr = np.zeros((120, 120, 4), dtype=np.uint8)
    arr[50:70, 50:70] = (200, 30, 30, 255)     # solid 20x20 subject
    arr[:, 0, 3] = CROP_INK_ALPHA - 20         # faint far-left stray line
    save_rgba(img, arr)

    assert crop_transparent(img, print) == "done"
    with Image.open(img) as out:
        # tight to the subject + margin, NOT dragged out to the x=0 line
        expected = 20 + 2 * CROP_MARGIN_PX
        assert out.size == (expected, expected)


def test_crop_halo_only_no_dimensional_crop_is_nothing_byte_unchanged(tmp_path):
    """The SUN_ECLIPSE case (owner 2026-07-19): a subject whose content
    fills the frame carries a faint border halo, so ``clean_edge_halo``
    zeroes some pixels — but the content box + margin still lands on the
    FULL frame (0px change). The dimensional rule wins: "nothing", file
    BYTE-UNCHANGED (the halo cleanup is discarded, never written)."""
    img = tmp_path / "halo.png"
    arr = np.zeros((30, 30, 4), dtype=np.uint8)
    arr[:, :, 3] = 255                         # opaque subject FILLS the frame
    arr[0, :, 3] = CLEAN_EDGE_ALPHA - 10       # faint halo row, border-connected
    save_rgba(img, arr)
    before = img.read_bytes()
    # content fills the frame -> box + margin == full frame -> 0px change
    assert crop_transparent(img, print) == "nothing"
    assert img.read_bytes() == before          # halo cleanup discarded, untouched


def test_ink_crop_noop_returns_nothing(tmp_path):
    """Already margin-tight, no faint pixels to clean -> "nothing"."""
    img = tmp_path / "tight.png"
    arr = np.zeros((28, 28, 4), dtype=np.uint8)
    arr[CROP_MARGIN_PX:-CROP_MARGIN_PX,
        CROP_MARGIN_PX:-CROP_MARGIN_PX] = (10, 200, 10, 255)
    save_rgba(img, arr)
    before = img.read_bytes()
    assert crop_transparent(img, print) == "nothing"
    assert img.read_bytes() == before          # untouched


@pytest.mark.skipif(not OLDAGE_PNG.exists(),
                    reason="the real OldAge.png is not present")
def test_oldage_real_image_crops_to_the_real_box(tmp_path):
    """Integration: on a COPY of the real OldAge.png (NEVER the source
    under out/), the crop tightens to the real subject box and the
    far-left faint line is gone. Measured real box: ink (174,66,849,
    1312) -> margins L174/R175/T66/B224; crop 1024x1536 -> 683x1254."""
    copy = tmp_path / "OldAge.png"
    shutil.copy2(OLDAGE_PNG, copy)             # operate only on the copy

    with Image.open(copy) as im:
        rgba = im.convert("RGBA")
    orig_w, orig_h = rgba.size
    assert (orig_w, orig_h) == (1024, 1536)

    # the far-left column carried faint stray pixels (alpha < ink)
    col5 = np.asarray(rgba)[:, 5, 3]
    assert 0 < col5.max() < CROP_INK_ALPHA

    # the ink box already ignores the faint line
    box = content_bbox(rgba)
    tol = 12
    assert abs(box[0] - 174) <= tol   # left starts at the subject, not x=5
    assert abs(box[1] - 66) <= tol
    assert abs(box[2] - 849) <= tol
    assert abs(box[3] - 1312) <= tol

    # the wired crop tightens the whole image and erases the line
    assert crop_transparent(copy, print) == "done"
    with Image.open(copy) as out:
        out_w, out_h = out.size
    assert abs(out_w - 683) <= 2 * tol
    assert abs(out_h - 1254) <= 2 * tol
    assert out_w < orig_w and out_h < orig_h  # genuinely tightened
