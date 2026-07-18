"""The split postprocess steps (owner's #7) — synthetic images.

``remove_background`` and ``crop_transparent`` are separate,
composable, in-place, and never raise for a no-op.
"""

import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from painter.bg_remove import clean_edge_halo, content_bbox
from painter.config import (
    CLEAN_EDGE_ALPHA,
    CROP_INK_ALPHA,
    CROP_MARGIN_PX,
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
    """A red square centered on a pure-white plate (the Gemini case)."""
    rgb = np.full((size, size, 3), 255, dtype=np.uint8)
    rgb[30:70, 30:70] = (200, 30, 30)
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
