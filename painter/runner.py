"""The run loop — queue, done-edge, save, fix, resume, pace.

Per pending item: paste (prompt + the chosen background suffix) ->
submit -> await the done edge -> extract bytes -> save under the
sheet's own drop path -> background fix -> mark done in the sidecar
``.progress.json`` -> pause -> next. A crash or a quota stop costs
nothing: the next run resumes past every marked item.

The loop only ever writes under ``out_root`` (the images, the
progress sidecar, the background fixes) — the sheet and its folder
are READ ONLY by construction.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from painter.config import PROGRESS_SUFFIX, Timing
from painter.driver import SiteDriver, sniff_format
from painter.sheet_parser import Sheet

Log = Callable[[str], None]
# GUI stop button etc.; checked between items and during the pause
ShouldStop = Callable[[], bool]
# background fix: (saved file) -> action string; exceptions are logged
PostSave = Callable[[Path], str]


class Progress:
    """Sidecar state file: ``<out_root>/<sheet-stem>.progress.json``."""

    def __init__(self, path: Path):
        self.path = path
        self._done: dict[str, dict] = {}
        if path.exists():
            self._done = json.loads(path.read_text(encoding="utf-8"))["done"]

    def is_done(self, drop_path: str) -> bool:
        return drop_path in self._done

    def mark_done(self, drop_path: str, out_file: Path) -> None:
        self._done[drop_path] = {
            "file": str(out_file),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps({"done": self._done}, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)


def run_sheet(
    sheet: Sheet,
    driver: SiteDriver,
    out_root: Path,
    timing: Timing,
    log: Log = print,
    should_stop: ShouldStop | None = None,
    post_save: PostSave | None = None,
    prompt_suffix: str = "",
) -> int:
    """Generate every pending item of a clean sheet; returns the count.

    The caller has already refused sheets with problems; skipped
    entries are logged here and never driven.
    """
    out_root.mkdir(parents=True, exist_ok=True)
    progress = Progress(out_root / (sheet.source.stem + PROGRESS_SUFFIX))

    for sk in sheet.skipped:
        log(f"  SKIP {sk.title} — {sk.reason}")

    queue = [it for it in sheet.items if not progress.is_done(it.drop_path)]
    already = len(sheet.items) - len(queue)
    if already:
        log(
            f"  RESUME: {already}/{len(sheet.items)} already done per"
            f" {progress.path.name}"
        )

    start = time.monotonic()
    total = len(queue)
    generated = 0
    fix_failures = 0
    for idx, item in enumerate(queue, start=1):
        if should_stop is not None and should_stop():
            log(f"  STOPPED on request — {generated}/{total} done this run")
            break
        elapsed = time.monotonic() - start
        log(f"[{elapsed:7.1f}s] ({idx}/{total}) {item.title}")
        driver.submit_prompt(item.prompt + prompt_suffix)
        driver.await_done(log)
        data = driver.extract_image()

        dest = out_root / item.drop_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        fmt = sniff_format(data)
        if fmt != dest.suffix.lstrip(".").lower():
            log(
                f"    WARNING: bytes look like {fmt or 'an unknown format'},"
                f" saved as {dest.suffix} because the sheet names the file"
            )
        if post_save is not None:
            try:
                action = post_save(dest)
                log(f"    bgfix: {action}")
            except Exception as exc:
                fix_failures += 1
                log(f"    BGFIX FAILED (image kept as saved): {exc}")
        progress.mark_done(item.drop_path, dest)
        generated += 1
        log(f"    saved {dest} ({len(data):,} bytes)")

        if idx < total:
            log(f"    pause {timing.pause_between_prompts_s:.0f}s (paced run)")
            pause_end = time.monotonic() + timing.pause_between_prompts_s
            while time.monotonic() < pause_end:
                if should_stop is not None and should_stop():
                    break
                time.sleep(min(0.5, timing.pause_between_prompts_s))

    if fix_failures:
        log(
            f"  NOTE: background fix failed on {fix_failures} image(s) —"
            " rerun the DOMY tool over the output folder later"
        )
    return generated
