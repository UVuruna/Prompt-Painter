"""The split postprocess steps (owner's #7) — synthetic images.

``remove_background`` and ``crop_transparent`` are separate,
composable, in-place, and never raise for a no-op.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from painter.config import CROP_MARGIN_PX
from painter.postprocess import (
    PostprocessError,
    crop_transparent,
    remove_background,
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
