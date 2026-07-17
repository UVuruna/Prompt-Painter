"""Background fix — the DOMY Watch tool run over each saved image.

Owner workflow step 5: Gemini renders on white, ChatGPT sometimes
forgets transparency. The DOMY Watch ``tools/bg_remove.py`` decides
PER FILE — already-transparent images are skipped untouched, white
backgrounds are cleared (edge-connected flood fill), ambiguous ones
are reported and left alone — so every saved image simply goes
through it. The tool only ever touches the file it is given, inside
the output folder.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from painter.config import BG_TOOL_ARGS, BG_TOOL_PY, BG_TOOL_TIMEOUT_S


class PostprocessError(RuntimeError):
    """The background tool failed on one image (loud, not masked)."""


def deps_error() -> str | None:
    """None when the background tool can run; else the reason it cannot."""
    if not BG_TOOL_PY.exists():
        return (
            f"background tool not found: {BG_TOOL_PY} — adjust BG_TOOL_PY"
            " in painter/config.py or disable the background fix"
        )
    probe = subprocess.run(
        [sys.executable, "-c", "import numpy, scipy, PIL"],
        capture_output=True,
    )
    if probe.returncode != 0:
        return (
            "the background tool needs numpy, scipy and Pillow —"
            " pip install numpy scipy pillow, or disable the"
            " background fix"
        )
    return None


def fix_background(image_path: Path) -> str:
    """Run the tool on one saved image in place; returns its action.

    Actions come from the tool itself: 'white', 'black',
    'skip-transparent', 'skip-ambiguous'.
    """
    result = subprocess.run(
        [sys.executable, str(BG_TOOL_PY), str(image_path), *BG_TOOL_ARGS],
        capture_output=True,
        text=True,
        timeout=BG_TOOL_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise PostprocessError(
            f"bg_remove failed on {image_path.name}:"
            f" {result.stderr.strip() or result.stdout.strip()}"
        )
    # single-file mode prints exactly: "<action> -> <dst>"
    last = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return last.split(" -> ")[0] or "done"
