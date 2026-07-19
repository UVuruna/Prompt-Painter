"""Upscale — Real-ESRGAN over the small circular/badge images.

Owner's #13: some generations come back small. The fix is the
standalone ``realesrgan-ncnn-vulkan`` Windows binary (no Python
package, no CUDA — Vulkan), kept under ``tools/realesrgan/``
(gitignored) and downloaded on first use from the official
Real-ESRGAN GitHub release.

Gating (owner 2026-07-19, four editable params — defaults reproduce
the old locked 2026-07-18 rule): an image QUALIFIES only if (1) its
aspect ratio W/H is within ``[aspect_min, aspect_max]`` (the
circular/badge class) AND (2) ``W < min_width`` OR ``H < min_height``.
Both pass -> upscale so W >= ``min_width`` and H >= ``min_height``
(aspect preserved, LANCZOS-corrected on overshoot, PNG in/out so
transparency survives). Anything else -> "nothing", so a caller can
count done vs skipped cleanly. The GUI passes per-agent / standalone
values; the config defaults (800/800/0.9/1.1) are the old behaviour.

Failures are LOUD (``UpscaleError``) but catchable — a machine
without Vulkan support keeps the rest of the pipeline alive.
"""

from __future__ import annotations

import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from painter.config import (
    UPSCALE_ASPECT_MAX,
    UPSCALE_ASPECT_MIN,
    UPSCALE_DIR,
    UPSCALE_EXE_NAME,
    UPSCALE_MIN_HEIGHT,
    UPSCALE_MIN_WIDTH,
    UPSCALE_MODEL,
    UPSCALE_ZIP_URL,
    fmt_size,
)

Log = Callable[[str], None]

_MANUAL_FIX = (
    f"download {UPSCALE_ZIP_URL} manually, unpack the exe and its"
    f" models/ folder into {UPSCALE_DIR}, and rerun"
)

# the binary is verified ONCE per process, not per image
_verified: Path | None = None


class UpscaleError(RuntimeError):
    """The upscaler cannot run or failed on one image (loud)."""


def _download_and_unpack(log: Log) -> None:
    """Fetch the official release zip and unpack it into UPSCALE_DIR."""
    UPSCALE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = UPSCALE_DIR / "realesrgan-download.zip"
    log(f"    downloading Real-ESRGAN binary ({UPSCALE_ZIP_URL}) ...")
    try:
        start = time.time()
        with urllib.request.urlopen(UPSCALE_ZIP_URL, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            fetched = 0
            next_log = 5 * 1024 * 1024
            with zip_path.open("wb") as fh:
                while chunk := resp.read(256 * 1024):
                    fh.write(chunk)
                    fetched += len(chunk)
                    if fetched >= next_log:
                        pct = f" ({fetched / total * 100:.0f}%)" if total else ""
                        log(
                            f"    ... {fmt_size(fetched)}{pct},"
                            f" {time.time() - start:.0f}s"
                        )
                        next_log += 5 * 1024 * 1024
    except Exception as exc:
        raise UpscaleError(
            f"cannot download the Real-ESRGAN binary: {exc} — {_MANUAL_FIX}"
        ) from exc
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(UPSCALE_DIR)
    except Exception as exc:
        raise UpscaleError(
            f"cannot unpack the Real-ESRGAN zip: {exc} — {_MANUAL_FIX}"
        ) from exc
    finally:
        zip_path.unlink(missing_ok=True)
    log(f"    Real-ESRGAN unpacked into {UPSCALE_DIR}")


def ensure_binary(log: Log = print) -> Path:
    """The verified upscaler exe; downloads the release on first use.

    Loud (``UpscaleError``, with manual instructions) when the
    download fails or the exe does not run on this machine.
    """
    global _verified
    if _verified is not None:
        return _verified
    exe = UPSCALE_DIR / UPSCALE_EXE_NAME
    if not exe.exists():
        # the zip may have unpacked into a subfolder — look once
        nested = list(UPSCALE_DIR.glob(f"*/{UPSCALE_EXE_NAME}"))
        if nested:
            exe = nested[0]
        else:
            _download_and_unpack(log)
            if not exe.exists():
                nested = list(UPSCALE_DIR.glob(f"*/{UPSCALE_EXE_NAME}"))
                if not nested:
                    raise UpscaleError(
                        f"the release zip held no {UPSCALE_EXE_NAME} —"
                        f" {_MANUAL_FIX}"
                    )
                exe = nested[0]
    try:
        probe = subprocess.run(
            [str(exe), "-h"], capture_output=True, text=True, timeout=30
        )
    except OSError as exc:
        raise UpscaleError(
            f"{exe.name} does not run on this machine ({exc}) — a GPU"
            f" with Vulkan support is required; {_MANUAL_FIX}"
        ) from exc
    blurb = (probe.stdout + probe.stderr).lower()
    if "usage" not in blurb and "input-path" not in blurb:
        raise UpscaleError(
            f"{exe.name} ran but printed no usage text (exit"
            f" {probe.returncode}): {(probe.stdout + probe.stderr)[:300]!r}"
            f" — {_MANUAL_FIX}"
        )
    _verified = exe
    return exe


def _run_binary(exe: Path, src: Path, dst: Path, scale: int) -> None:
    """One binary invocation; loud on a non-zero exit or no output."""
    cmd = [
        str(exe), "-i", str(src), "-o", str(dst),
        "-s", str(scale), "-n", UPSCALE_MODEL,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpscaleError(f"upscaler failed to run: {exc}") from exc
    if proc.returncode != 0 or not dst.exists():
        raise UpscaleError(
            f"upscaler exited {proc.returncode} on {src.name} (no"
            f" Vulkan device?): {(proc.stderr or proc.stdout)[:300]!r}"
        )


def upscale_if_small(
    path: Path,
    log: Log,
    *,
    min_width: int = UPSCALE_MIN_WIDTH,
    min_height: int = UPSCALE_MIN_HEIGHT,
    aspect_min: float = UPSCALE_ASPECT_MIN,
    aspect_max: float = UPSCALE_ASPECT_MAX,
) -> str:
    """Upscale one saved image in place when it qualifies.

    Returns "done" (upscaled so W >= ``min_width`` and H >=
    ``min_height``, aspect preserved) or "nothing" (aspect W/H outside
    ``[aspect_min, aspect_max]``, or already at both minimums). Raises
    ``UpscaleError`` loudly when the binary cannot run or fails —
    catchable, so the pipeline survives a machine without Vulkan.
    """
    from PIL import Image

    with Image.open(path) as im:
        width, height = im.size
    ratio = width / height
    if not (aspect_min <= ratio <= aspect_max):
        return "nothing"
    if width >= min_width and height >= min_height:
        return "nothing"

    exe = ensure_binary(log)
    # ALWAYS the model's native 4x: non-native -s 2/3 with the
    # x4plus model CORRUPTS the output (verified live 2026-07-18 on
    # a real rondel — tile misalignment, lost detail); the LANCZOS
    # step below brings the 4x result down to the exact target
    tmp = path.with_name(path.stem + "__upscale_tmp.png")
    try:
        _run_binary(exe, path, tmp, 4)
        with Image.open(tmp) as up:
            out = up.convert("RGBA") if up.mode != "RGBA" else up.copy()
    finally:
        tmp.unlink(missing_ok=True)

    # The 4x image is (usually) larger than both targets; scale it down
    # (aspect preserved) by the SMALLEST factor that still keeps W >=
    # min_width AND H >= min_height — i.e. the larger of the two ratios,
    # so the binding axis lands exactly on its target and the other
    # clears its own. Capped at 1.0: a tiny source whose 4x cannot reach
    # a target stays at full 4x (logged), never upscaled past 4x.
    factor = min(
        1.0, max(min_width / out.width, min_height / out.height)
    )
    if factor < 1.0:
        out = out.resize(
            (max(1, round(out.width * factor)),
             max(1, round(out.height * factor))),
            Image.LANCZOS,
        )
    out.save(path, "PNG", optimize=True)
    log(
        f"    upscaled {width}x{height} -> {out.width}x{out.height}"
        f" (Real-ESRGAN x4 + LANCZOS)"
    )
    if out.width < min_width or out.height < min_height:
        log(
            f"    NOTE: even x4 left {path.name} below {min_width}x"
            f"{min_height}px ({out.width}x{out.height}) — source was tiny"
        )
    return "done"
