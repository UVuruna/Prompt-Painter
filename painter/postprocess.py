"""Postprocess — background removal and transparent-crop, composable.

Owner workflow step 6, split in two (owner's #7): the pipeline
callers (main.py's post_save, the GUI's own) compose the steps by
flags instead of one fused fix:

* ``remove_background`` — the in-house remover, auto-detected per
  file: already-transparent images are untouched ("nothing"), white
  (Gemini) and black backgrounds are cleared ("done"), ambiguous
  ones are reported and left alone ("unclear").
* ``crop_transparent`` — autocrop a transparent image to its content
  bounding box plus a small config safety margin ("done"), or leave
  it be when there is no transparency to crop against or it is
  already tight ("nothing").

Both work IN PLACE, only ever on the file they are given (inside
the output folder), loud (``PostprocessError``) on real errors and
silent on no-ops. Heavy imports (numpy/scipy/Pillow) load lazily so
dry runs and sheet checks stay stdlib-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from painter.config import CROP_ALPHA_THRESH, CROP_MARGIN_PX

Log = Callable[[str], None]


class PostprocessError(RuntimeError):
    """A postprocess step failed on one image (loud, not masked)."""


def deps_error() -> str | None:
    """None when the postprocess steps can run; else the reason not."""
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as exc:
        return (
            f"postprocess needs numpy, scipy and Pillow ({exc}) —"
            " pip install -r requirements.txt, or disable the"
            " background fix and crop"
        )
    return None


def remove_background(path: Path, log: Log) -> str:
    """Clear one saved image's background in place.

    Returns "done" (white/black background cleared), "nothing"
    (already transparent — no-op) or "unclear" (ambiguous
    background: reported, left untouched). Raises
    ``PostprocessError`` on a real failure.
    """
    from PIL import Image

    from painter.bg_remove import (
        detect,
        remove_black_background,
        remove_white_border,
    )

    try:
        with Image.open(path) as im:
            action, white_full, white_edge = detect(im)
            if action == "skip-transparent":
                return "nothing"
            if action == "skip-ambiguous":
                log(
                    f"    background UNCLEAR (not white/black) — left"
                    f" untouched: {path.name}"
                )
                return "unclear"
            if action == "white":
                out = remove_white_border(im, white_full, white_edge)
            else:
                out = remove_black_background(im)
        out.save(path, "PNG", optimize=True)
        return "done"
    except Exception as exc:
        raise PostprocessError(
            f"background removal failed on {path.name}: {exc}"
        ) from exc


def crop_transparent(path: Path, log: Log) -> str:
    """Autocrop one transparent image to its content box, in place.

    The box keeps a small safety margin (``CROP_MARGIN_PX``).
    Returns "done" (cropped) or "nothing" — no transparency to crop
    against (fully opaque, so the box IS the image), fully
    transparent, or already tight. Raises ``PostprocessError`` on a
    real failure.
    """
    from PIL import Image

    from painter.bg_remove import content_bbox

    try:
        with Image.open(path) as im:
            rgba = im.convert("RGBA")
        box = content_bbox(rgba, CROP_ALPHA_THRESH)
        if box is None:
            return "nothing"  # fully transparent — nothing to crop to
        width, height = rgba.size
        left = max(0, box[0] - CROP_MARGIN_PX)
        top = max(0, box[1] - CROP_MARGIN_PX)
        right = min(width, box[2] + CROP_MARGIN_PX)
        bottom = min(height, box[3] + CROP_MARGIN_PX)
        if (left, top, right, bottom) == (0, 0, width, height):
            return "nothing"  # opaque or already tight
        rgba.crop((left, top, right, bottom)).save(
            path, "PNG", optimize=True
        )
        return "done"
    except Exception as exc:
        raise PostprocessError(
            f"crop failed on {path.name}: {exc}"
        ) from exc
