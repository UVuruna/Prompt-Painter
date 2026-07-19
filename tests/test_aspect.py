"""Change-aspect batch deform (owner's standalone tool, 2026-07-19).

The rule NEVER shrinks either dimension: the result is the smallest
box of the target ratio that still CONTAINS the original, so exactly
one axis grows. These tests pin the four ratios the owner verified by
hand, the already-at-ratio no-op (file byte-unchanged), portrait /
landscape growth, alpha/mode preservation and the loud rejections.
Everything runs on synthetic images in tmp_path — nothing under out/
or DOMY is touched.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from painter.aspect import AspectError, change_aspect
from painter.config import (
    ASPECT_FILTER_IF,
    ASPECT_FILTER_IF_NOT,
    ASPECT_FILTER_OFF,
)


def make_png(path: Path, width: int, height: int, mode: str = "RGBA") -> None:
    """A test image with a solid centre; RGBA gets transparent corners."""
    if mode == "RGBA":
        arr = np.zeros((height, width, 4), dtype=np.uint8)
        arr[height // 4: 3 * height // 4, width // 4: 3 * width // 4] = (
            180, 60, 60, 255,
        )
        Image.fromarray(arr, mode="RGBA").save(path, "PNG")
    else:
        arr = np.full((height, width, 3), 200, dtype=np.uint8)
        Image.fromarray(arr, mode="RGB").save(path, "PNG")


# the FOUR sizes the owner verified by hand — must reproduce EXACTLY
@pytest.mark.parametrize(
    "src_w, src_h, ratio_w, ratio_h, out_w, out_h",
    [
        (1024, 1024, 16, 9, 1820, 1024),
        (1536, 1024, 16, 9, 1820, 1024),
        (1024, 1536, 9, 16, 1024, 1820),
        (1024, 1024, 1, 2, 1024, 2048),
    ],
)
def test_verified_example_sizes(
    tmp_path, src_w, src_h, ratio_w, ratio_h, out_w, out_h
):
    img = tmp_path / "plate.png"
    make_png(img, src_w, src_h)
    assert change_aspect(img, ratio_w, ratio_h, print) == "done"
    with Image.open(img) as out:
        assert out.size == (out_w, out_h)


def test_already_at_ratio_is_nothing_and_byte_unchanged(tmp_path):
    img = tmp_path / "wide.png"
    make_png(img, 1600, 900)  # exactly 16:9
    before = img.read_bytes()
    logs: list[str] = []
    assert change_aspect(img, 16, 9, logs.append) == "nothing"
    assert img.read_bytes() == before  # not rewritten at all
    assert logs == []  # a no-op stays quiet


def test_within_tolerance_is_nothing(tmp_path):
    # 1778x1000 = 1.778 — within ASPECT_TOL (0.001) of 16/9 = 1.77778
    img = tmp_path / "near.png"
    make_png(img, 1778, 1000)
    before = img.read_bytes()
    assert change_aspect(img, 16, 9, print) == "nothing"
    assert img.read_bytes() == before


def test_landscape_growth_keeps_height(tmp_path):
    img = tmp_path / "square.png"
    make_png(img, 1000, 1000)
    assert change_aspect(img, 3, 2, print) == "done"  # target 1.5 > 1.0
    with Image.open(img) as out:
        assert out.size == (1500, 1000)  # width grew, height kept


def test_portrait_growth_keeps_width(tmp_path):
    img = tmp_path / "square.png"
    make_png(img, 1000, 1000)
    assert change_aspect(img, 2, 3, print) == "done"  # target 0.667 < 1.0
    with Image.open(img) as out:
        assert out.size == (1000, 1500)  # height grew, width kept


def test_rgba_alpha_preserved(tmp_path):
    img = tmp_path / "badge.png"
    make_png(img, 1024, 1024)  # transparent corners
    assert change_aspect(img, 16, 9, print) == "done"
    with Image.open(img) as out:
        assert out.mode == "RGBA"
        data = np.asarray(out)
        assert data[0, 0, 3] == 0             # corner stayed transparent
        assert data.shape[:2] == (1024, 1820)  # (h, w) after the stretch
        assert int(data[..., 3].max()) == 255  # the solid centre survived


def test_rgb_mode_preserved(tmp_path):
    img = tmp_path / "opaque.png"
    make_png(img, 1024, 1024, mode="RGB")
    assert change_aspect(img, 16, 9, print) == "done"
    with Image.open(img) as out:
        assert out.mode == "RGB"
        assert out.size == (1820, 1024)


@pytest.mark.parametrize("ratio_w, ratio_h", [(0, 9), (16, 0), (-16, 9), (16, -9)])
def test_invalid_ratio_raises_loudly(tmp_path, ratio_w, ratio_h):
    img = tmp_path / "plate.png"
    make_png(img, 1024, 1024)
    before = img.read_bytes()
    with pytest.raises(AspectError):
        change_aspect(img, ratio_w, ratio_h, print)
    assert img.read_bytes() == before  # rejected before any write


def test_real_image_error_is_loud(tmp_path):
    bad = tmp_path / "not_an_image.png"
    bad.write_text("this is not a PNG")
    with pytest.raises(AspectError):
        change_aspect(bad, 16, 9, print)


# --- optional input filter on the CURRENT ratio (owner 2026-07-19) ----
# ~square band 0.9-1.1: a 1000x1000 image (W/H = 1.0) is IN it, a
# 2000x1000 image (W/H = 2.0) is OUT of it.


def test_filter_if_processes_only_in_range(tmp_path):
    """IF keeps ONLY in-range images; an out-of-range image is skipped
    byte-unchanged."""
    square = tmp_path / "square.png"
    make_png(square, 1000, 1000)          # W/H = 1.0, in 0.9-1.1
    wide = tmp_path / "wide.png"
    make_png(wide, 2000, 1000)            # W/H = 2.0, out of range
    wide_before = wide.read_bytes()
    assert change_aspect(
        square, 16, 9, print,
        filter_from=0.9, filter_to=1.1, filter_mode=ASPECT_FILTER_IF,
    ) == "done"
    assert change_aspect(
        wide, 16, 9, print,
        filter_from=0.9, filter_to=1.1, filter_mode=ASPECT_FILTER_IF,
    ) == "nothing"
    assert wide.read_bytes() == wide_before  # left untouched


def test_filter_if_not_skips_in_range(tmp_path):
    """IF NOT skips in-range images and processes the rest."""
    square = tmp_path / "square.png"
    make_png(square, 1000, 1000)          # in range -> skipped
    wide = tmp_path / "wide.png"
    make_png(wide, 2000, 1000)            # out of range -> processed
    square_before = square.read_bytes()
    assert change_aspect(
        square, 16, 9, print,
        filter_from=0.9, filter_to=1.1, filter_mode=ASPECT_FILTER_IF_NOT,
    ) == "nothing"
    assert square.read_bytes() == square_before
    assert change_aspect(
        wide, 16, 9, print,
        filter_from=0.9, filter_to=1.1, filter_mode=ASPECT_FILTER_IF_NOT,
    ) == "done"


def test_filter_off_processes_all(tmp_path):
    """off (the default) ignores the range and processes every image."""
    square = tmp_path / "square.png"
    make_png(square, 1000, 1000)
    assert change_aspect(
        square, 16, 9, print,
        filter_from=0.9, filter_to=1.1, filter_mode=ASPECT_FILTER_OFF,
    ) == "done"
    # and with no filter args at all (the plain call) it still processes
    other = tmp_path / "other.png"
    make_png(other, 1000, 1000)
    assert change_aspect(other, 16, 9, print) == "done"
