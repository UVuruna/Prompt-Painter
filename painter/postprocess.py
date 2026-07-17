"""Background fix — the in-house tool run over each saved image.

Owner workflow step 5: Gemini renders on white, ChatGPT sometimes
forgets transparency. Every saved image goes through
``painter/bg_remove.py`` (part of THIS project), which decides PER
FILE — already-transparent images are skipped untouched, white
backgrounds are cleared (edge-connected flood fill + autocrop),
ambiguous ones are reported and left alone. It only ever touches
the file it is given, inside the output folder.
"""

from __future__ import annotations

from pathlib import Path

from painter.config import BG_FIX_CROP


class PostprocessError(RuntimeError):
    """The background tool failed on one image (loud, not masked)."""


def deps_error() -> str | None:
    """None when the background tool can run; else the reason it cannot."""
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as exc:
        return (
            f"the background tool needs numpy, scipy and Pillow ({exc}) —"
            " pip install -r requirements.txt, or disable the"
            " background fix"
        )
    return None


def fix_background(image_path: Path) -> str:
    """Run the tool on one saved image in place; returns its action.

    Actions come from the tool itself: 'white', 'black',
    'skip-transparent', 'skip-ambiguous'.
    """
    # imported lazily so nothing browser- or numpy-flavored loads for
    # dry runs and sheet checks
    from painter.bg_remove import process_file

    try:
        return process_file(
            image_path, image_path, "auto", BG_FIX_CROP, None, None
        )
    except Exception as exc:
        raise PostprocessError(
            f"bg_remove failed on {image_path.name}: {exc}"
        ) from exc
