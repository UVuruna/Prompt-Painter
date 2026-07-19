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
    clean_edge_halo,
    content_bbox,
    remove_black_background,
)
from painter.config import (
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
    out, removed = remove_black_background(Image.fromarray(rgb, mode="RGB"))
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
    assert any("too risky" in line for line in logs)


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
    assert any("too risky" in line for line in logs)


def test_black_removal_returns_removed_fraction():
    """The remove_* contract is (rgba, removed_frac) — the fraction the
    removal clears, which the guard checks. A clean bright-on-black frame
    clears ~the border ring, well under the guard."""
    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    rgb[10:90, 10:90] = 210                       # 80x80 subject, 20px frame gone
    out, removed = remove_black_background(Image.fromarray(rgb, mode="RGB"))
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


def test_ambiguous_background_is_unclear_and_untouched(tmp_path):
    img = tmp_path / "gradient.png"
    rgb = np.full((60, 60, 3), 128, dtype=np.uint8)  # mid-gray border
    rgb[20:40, 20:40] = (250, 250, 40)
    Image.fromarray(rgb, mode="RGB").save(img, "PNG")
    before = img.read_bytes()
    logs: list[str] = []

    assert remove_background(img, logs.append) == "unclear"
    assert img.read_bytes() == before
    assert any("UNCLEAR" in line for line in logs)


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


def test_crop_cleans_halo_even_when_box_is_already_tight(tmp_path):
    """A tight subject with a faint border halo still returns "done"
    (the halo was cleaned) rather than "nothing"."""
    img = tmp_path / "halo.png"
    arr = np.zeros((30, 30, 4), dtype=np.uint8)
    arr[:, :, 3] = 255                         # fully opaque subject
    arr[0, :, 3] = 0                           # top row transparent (border)
    arr[1, :, 3] = CLEAN_EDGE_ALPHA - 10       # faint halo row, border-connected
    save_rgba(img, arr)
    assert crop_transparent(img, print) == "done"
    with Image.open(img) as out:
        top = np.asarray(out.convert("RGBA"))[1, :, 3]
    assert (top == 0).all()                    # the faint halo row was zeroed


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
