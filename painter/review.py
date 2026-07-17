"""Staging and approval — phase two of the output workflow.

Phase one (the run loop) writes every generated image to
``<out>/_staging/<site>/<drop-path>``. Phase two is the owner's:
he reviews the staged images and ONLY his approval moves one to its
final ``<out>/<site>/<drop-path>``. A rejected image is deleted and
cleared from the progress sidecar, so the next run regenerates it
(usually after the prompt was reworked in the sheet).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from painter.config import IMAGE_EXTENSIONS, PROGRESS_SUFFIX, STAGING_DIRNAME


def staging_root(out_base: Path, site: str) -> Path:
    return out_base / STAGING_DIRNAME / site


def final_root(out_base: Path, site: str) -> Path:
    return out_base / site


@dataclass(frozen=True)
class StagedImage:
    """One generated image awaiting the owner's verdict."""

    site: str
    drop_path: str  # POSIX-relative, the sheet's own path
    path: Path      # where it sits in staging


def staged_images(out_base: Path, sites: tuple[str, ...]) -> list[StagedImage]:
    """Every image currently staged for the given sites."""
    found: list[StagedImage] = []
    for site in sites:
        root = staging_root(out_base, site)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                drop = path.relative_to(root).as_posix()
                found.append(StagedImage(site, drop, path))
    return found


def approve(out_base: Path, item: StagedImage) -> Path:
    """Move one staged image to its final destination; returns it."""
    dest = final_root(out_base, item.site) / item.drop_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    item.path.replace(dest)
    return dest


def reject(out_base: Path, item: StagedImage) -> None:
    """Delete one staged image and unmark it, so a rerun regenerates it."""
    item.path.unlink()
    _unmark_in_dir(staging_root(out_base, item.site), item.drop_path)


def _unmark_in_dir(root: Path, drop_path: str) -> None:
    """Remove a drop path from every progress sidecar under root."""
    for progress_file in root.glob(f"*{PROGRESS_SUFFIX}"):
        data = json.loads(progress_file.read_text(encoding="utf-8"))
        if drop_path in data.get("done", {}):
            del data["done"][drop_path]
            tmp = progress_file.with_name(progress_file.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(progress_file)
