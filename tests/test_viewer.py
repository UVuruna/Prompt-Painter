"""Before/after viewer transparency backdrop — the tool-panel fix.

BG removal (and crop/aspect) leave the AFTER image transparent where the
background was cleared; drawn straight onto the panel colour it looks
unchanged. The viewer composites any image WITH ALPHA over a neutral
checkerboard so "removed" reads as removed. These check the two pure-PIL
helpers behind that (``_checkerboard`` builds the board, ``_has_alpha``
decides when to use it); the on-screen composite itself is verified by
the ImageGrab screenshots, not here (it needs a live Tk PhotoImage).

Importing ``gui`` pulls tkinter/ctk but opens no window, so this runs
headless like the rest of the suite.
"""

import numpy as np
from PIL import Image

import gui
from painter.config import CHECKER_DARK, CHECKER_LIGHT, CHECKER_TILE_PX


def test_checkerboard_has_the_requested_size_and_two_shades():
    board = gui._checkerboard(50, 40)
    assert board.size == (50, 40)
    colours = {px for px in board.getdata()}
    assert colours == {CHECKER_LIGHT, CHECKER_DARK}


def test_checkerboard_alternates_tiles():
    """Neighbouring tiles differ — the top-left tile is light, the tile
    one square to the right is dark (a real checker, not a flat fill)."""
    board = gui._checkerboard(CHECKER_TILE_PX * 2, CHECKER_TILE_PX)
    assert board.getpixel((0, 0)) == CHECKER_LIGHT
    assert board.getpixel((CHECKER_TILE_PX, 0)) == CHECKER_DARK


def test_has_alpha_true_for_transparent_modes():
    assert gui._has_alpha(Image.new("RGBA", (4, 4)))
    assert gui._has_alpha(Image.new("LA", (4, 4)))


def test_has_alpha_false_for_opaque_modes():
    assert not gui._has_alpha(Image.new("RGB", (4, 4)))
    assert not gui._has_alpha(Image.new("L", (4, 4)))


def test_has_alpha_true_for_palette_with_transparency():
    p = Image.new("P", (4, 4))
    p.info["transparency"] = 0
    assert gui._has_alpha(p)


def test_checker_composite_replaces_cleared_pixels():
    """The core promise: a fully transparent corner ends up showing the
    checker (a background colour), never black/nothing — so a removed
    background is visible. Replicates the composite _scaled_photo does,
    without needing a Tk PhotoImage."""
    rgba = np.zeros((CHECKER_TILE_PX, CHECKER_TILE_PX, 4), dtype=np.uint8)
    rgba[..., :3] = (200, 20, 20)
    rgba[..., 3] = 0  # fully transparent tile
    img = Image.fromarray(rgba, "RGBA")
    board = gui._checkerboard(img.width, img.height)
    board.paste(img, (0, 0), img)
    # transparent everywhere -> the checker shows through untouched
    assert board.getpixel((0, 0)) == CHECKER_LIGHT
