"""Upscale gating (owner's #13, gate locked 2026-07-18).

The gating logic runs against a MOCKED binary (the ncnn exe is a
download); the last test drives the REAL binary and is skipped when
it is not on disk.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import painter.upscale as upscale_mod
from painter.config import UPSCALE_DIR, UPSCALE_EXE_NAME
from painter.upscale import upscale_if_small


def make_png(path: Path, width: int, height: int) -> None:
    """A small RGBA test image with real transparency at the corners."""
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[height // 4: 3 * height // 4, width // 4: 3 * width // 4] = (
        180, 60, 60, 255,
    )
    Image.fromarray(arr, mode="RGBA").save(path, "PNG")


@pytest.fixture
def fake_binary(monkeypatch):
    """Replace the exe with a NEAREST resize; record the calls."""
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


def test_non_square_is_nothing(tmp_path, fake_binary):
    img = tmp_path / "lancet.png"
    make_png(img, 400, 1000)  # tall lancet — not the badge class
    assert upscale_if_small(img, print) == "nothing"
    assert fake_binary == []  # the binary is never touched


def test_big_enough_is_nothing(tmp_path, fake_binary):
    img = tmp_path / "big.png"
    make_png(img, 1024, 1024)
    assert upscale_if_small(img, print) == "nothing"
    assert fake_binary == []


def test_aspect_tolerance_boundary(tmp_path, fake_binary):
    inside = tmp_path / "inside.png"
    make_png(inside, 440, 400)  # W/H = 1.1 — inside the gate
    assert upscale_if_small(inside, print) == "done"

    outside = tmp_path / "outside.png"
    make_png(outside, 460, 400)  # W/H = 1.15 — outside
    assert upscale_if_small(outside, print) == "nothing"


def test_small_square_upscales_to_the_exact_minimum(tmp_path, fake_binary):
    img = tmp_path / "rondel.png"
    make_png(img, 400, 400)
    assert upscale_if_small(img, print) == "done"
    # ALWAYS the model's native 4x (non-native scales corrupt the
    # output — verified live); LANCZOS brings it to the target
    assert fake_binary == [4]
    with Image.open(img) as out:
        assert out.size == (800, 800)
        assert np.asarray(out)[:, :, 3][0, 0] == 0  # alpha survived


def test_overshoot_is_lanczos_corrected_to_the_exact_target(
    tmp_path, fake_binary
):
    img = tmp_path / "near.png"
    make_png(img, 500, 520)
    assert upscale_if_small(img, print) == "done"
    assert fake_binary == [4]
    with Image.open(img) as out:
        # min dimension lands EXACTLY on the target, aspect kept
        assert min(out.size) == 800
        assert out.size == (800, 832)


def test_tiny_image_stays_below_but_still_done(tmp_path, fake_binary):
    img = tmp_path / "tiny.png"
    make_png(img, 150, 150)
    logs: list[str] = []
    assert upscale_if_small(img, logs.append) == "done"
    assert fake_binary == [4]  # 4x is all the model has
    with Image.open(img) as out:
        assert out.size == (600, 600)  # honest: still below 800
    assert any("below 800" in line for line in logs)


# --- the four configurable gate params (owner 2026-07-19) -------------

def test_configurable_aspect_bounds(tmp_path, fake_binary):
    """A wide W/H=1.5 image is rejected by the default 0.9–1.1 gate but
    qualifies once the aspect bounds are widened to cover it."""
    img = tmp_path / "wide.png"
    make_png(img, 600, 400)  # W/H = 1.5
    assert (
        upscale_if_small(img, print, aspect_min=0.9, aspect_max=1.1)
        == "nothing"
    )
    assert fake_binary == []  # the default gate never touched the binary
    assert (
        upscale_if_small(img, print, aspect_min=1.4, aspect_max=1.6)
        == "done"
    )
    assert fake_binary == [4]
    with Image.open(img) as out:
        # 4x=(2400,1600); scaled so both hit the 800 defaults, aspect kept
        assert out.size == (1200, 800)


def test_configurable_min_width_and_height_targets(tmp_path, fake_binary):
    """Separate min WIDTH and min HEIGHT: the binding axis (here width,
    needing 1000) lands on its target and the other clears its own."""
    img = tmp_path / "sq.png"
    make_png(img, 300, 300)
    assert (
        upscale_if_small(img, print, min_width=1000, min_height=600)
        == "done"
    )
    assert fake_binary == [4]
    with Image.open(img) as out:
        assert out.width >= 1000 and out.height >= 600
        assert out.size == (1000, 1000)  # 4x=(1200,1200) * (1000/1200)


def test_qualifies_when_only_one_dimension_is_under_its_min(
    tmp_path, fake_binary
):
    """The gate is an OR: W under min_width qualifies even when H already
    clears min_height, and the result grows so BOTH minimums are met."""
    img = tmp_path / "tall_badge.png"
    make_png(img, 760, 820)  # ratio ~0.927 (in gate); W<800, H>=800
    assert upscale_if_small(img, print) == "done"
    assert fake_binary == [4]
    with Image.open(img) as out:
        assert out.width >= 800 and out.height >= 800


def test_non_qualifying_small_but_wrong_aspect_returns_nothing(
    tmp_path, fake_binary
):
    """Small on both axes but aspect outside the (custom) gate -> nothing,
    binary untouched."""
    img = tmp_path / "portrait.png"
    make_png(img, 500, 900)  # ratio ~0.556
    assert (
        upscale_if_small(img, print, aspect_min=0.9, aspect_max=1.1)
        == "nothing"
    )
    assert fake_binary == []


REAL_EXE = UPSCALE_DIR / UPSCALE_EXE_NAME


@pytest.mark.skipif(
    not REAL_EXE.exists(),
    reason="realesrgan-ncnn-vulkan not downloaded (tools/realesrgan/)",
)
def test_real_binary_upscales_a_small_square(tmp_path):
    img = tmp_path / "real_rondel.png"
    make_png(img, 300, 300)
    logs: list[str] = []
    assert upscale_if_small(img, logs.append) == "done"
    with Image.open(img) as out:
        assert min(out.size) >= 800
        assert out.mode == "RGBA"  # transparency preserved
    assert any("upscaled 300x300" in line for line in logs)
