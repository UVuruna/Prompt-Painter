"""Change aspect ratio — batch DEFORM every image to a target ratio.

Owner's standalone tool (2026-07-19): pick a folder and a target
ratio X:Y, then non-proportionally STRETCH every image to that ratio
IN PLACE. It stands beside the other in-place batch tools (background
removal, crop, upscale) and reports on the dashboard the same way.

THE RULE (owner-approved): NEVER shrink either dimension. The result
is the smallest box of the target ratio that still CONTAINS the
original, so exactly ONE axis is stretched larger and neither is cut.
For an image ``w x h`` and target ``X:Y`` (X width units, Y height
units)::

    target = X / Y ; cur = w / h
    |cur - target| <= ASPECT_TOL  -> already at ratio ("nothing")
    cur < target                  -> keep height, grow width:
                                     new_w = round(h * X / Y), new_h = h
    else                          -> keep width, grow height:
                                     new_h = round(w * Y / X), new_w = w

The resize is a deliberate non-proportional LANCZOS stretch; the
image mode (and so its alpha: RGBA in -> RGBA out) is preserved and
the file is written back as PNG. A no-op (already at ratio) NEVER
raises and leaves the file untouched; a real failure is LOUD
(``AspectError``, catchable so a batch survives one bad file). A
non-positive target ratio is rejected loudly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from painter.config import ASPECT_TOL

Log = Callable[[str], None]


class AspectError(RuntimeError):
    """The aspect deform failed on one image, or the target ratio is
    invalid (loud, never masked)."""


def change_aspect(
    path: Path,
    ratio_w: int,
    ratio_h: int,
    log: Log,
    *,
    tol: float = ASPECT_TOL,
) -> str:
    """Stretch one image to the target ratio ``ratio_w : ratio_h`` in
    place.

    Returns "done" (resized to the target ratio) or "nothing" (already
    at the ratio within ``tol`` — the file is left byte-unchanged). The
    stretch NEVER shrinks either axis (see the module docstring); mode
    and alpha are preserved and the result is saved as PNG.

    Raises ``AspectError`` loudly when the target ratio is non-positive
    or a real image failure occurs; a no-op never raises.
    """
    if ratio_w <= 0 or ratio_h <= 0:
        raise AspectError(
            f"target ratio must be positive, got {ratio_w}:{ratio_h}"
        )

    from PIL import Image

    try:
        with Image.open(path) as im:
            width, height = im.size
            target = ratio_w / ratio_h
            cur = width / height
            if abs(cur - target) <= tol:
                return "nothing"
            if cur < target:
                # too tall/narrow for the target — grow the WIDTH
                new_w, new_h = round(height * ratio_w / ratio_h), height
            else:
                # too wide for the target — grow the HEIGHT
                new_w, new_h = width, round(width * ratio_h / ratio_w)
            # a deliberate non-proportional stretch; resize keeps the
            # source mode, so RGBA (real alpha) survives as RGBA
            resized = im.resize((new_w, new_h), Image.LANCZOS)
        resized.save(path, "PNG", optimize=True)
    except AspectError:
        raise
    except Exception as exc:
        raise AspectError(
            f"aspect change failed on {path.name}: {exc}"
        ) from exc

    log(
        f"    stretched {width}x{height} -> {new_w}x{new_h}"
        f" (target {ratio_w}:{ratio_h}, LANCZOS)"
    )
    return "done"
