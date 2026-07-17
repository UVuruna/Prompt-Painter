"""The run loop — queue, done-edge, save, fix, report, resume, pace.

Per pending item: paste (prompt + the site's rule suffix) -> submit
-> await the done edge -> extract bytes -> save DIRECTLY under
``<out_root>/<drop-path>`` -> background fix -> report line -> mark
done in the sidecar ``.progress.json`` -> pause -> next. A crash or
a quota stop costs nothing: the next run resumes past every marked
item, and the report keeps every finished line.

The loop only ever writes under ``out_root`` (images, progress,
report, background fixes) — sheets are READ ONLY by construction.
"""

from __future__ import annotations

import json
import random
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from painter.config import PROGRESS_SUFFIX, REPORT_SUFFIX, Timing
from painter.driver import ItemRefused, SiteDriver, sniff_format
from painter.sheet_parser import Sheet, SkippedItem

Log = Callable[[str], None]
# GUI stop button etc.; checked between items and during the pause
ShouldStop = Callable[[], bool]
# background fix: (saved file) -> action string; exceptions are logged
PostSave = Callable[[Path], str]

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> str:
    """WxH from a PNG header (all saved images are PNG), else '?'."""
    if len(data) >= 24 and data.startswith(_PNG_MAGIC):
        width, height = struct.unpack(">II", data[16:24])
        return f"{width}x{height}"
    return "?"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_s(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _pause(timing: Timing, should_stop: ShouldStop | None, log: Log) -> None:
    """A random polite pause between prompts, interruptible by Stop."""
    wait = random.uniform(timing.pause_min_s, timing.pause_max_s)
    log(f"    pause {wait:.2f}s (paced run)")
    pause_end = time.monotonic() + wait
    while time.monotonic() < pause_end:
        if should_stop is not None and should_stop():
            break
        time.sleep(0.5)


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


class RunReport:
    """``<out_root>/<sheet-stem>_report.txt`` — appended per run.

    Written INCREMENTALLY (header, then a line per image, then the
    summary) so an interrupted run keeps every finished line.
    """

    def __init__(self, path: Path, theme: str, site_name: str):
        self.path = path
        self._theme = theme
        self._site = site_name
        self._gen_times: list[float] = []
        self._extra_times: list[float] = []
        self._refused = 0

    def _append(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")

    def start(self, pending: int, total: int, skipped=()) -> None:
        self._append("=" * 68)
        self._append(f"{self._theme}  [{self._site}]")
        self._append(f"Run started:  {_now()}  ({pending}/{total} pending)")
        for sk in skipped:
            self._append(
                f"SKIPPED by the sheet (L{sk.line}): {sk.title} —"
                f" {sk.reason}"
            )
        self._append("-" * 68)

    def item(
        self,
        drop_path: str,
        gen_s: float,
        extra_s: float,
        orig_res: str,
        final_res: str,
        actions: list[str],
    ) -> None:
        self._gen_times.append(gen_s)
        self._extra_times.append(extra_s)
        note = f"  [{', '.join(actions)}]" if actions else ""
        resolution = (
            f"{orig_res} -> {final_res}"
            if final_res not in ("", orig_res)
            else orig_res
        )
        self._append(
            f"{_now()}  {drop_path:<44} gen {gen_s:6.1f}s"
            f"  {resolution}{note}"
        )

    def refused(self, drop_path: str, reason: str) -> None:
        self._refused += 1
        self._append(f"{_now()}  {drop_path:<44} REFUSED — {reason[:120]}")

    def finish(self, generated: int, wall_s: float, stopped_why: str) -> None:
        self._append("-" * 68)
        if self._refused:
            self._append(
                f"Refused: {self._refused} image(s) — rework those"
                " prompts in the sheet (or intervene manually) and rerun"
            )
        if self._gen_times:
            avg = sum(self._gen_times) / len(self._gen_times)
            self._append(
                f"Images: {generated}  |  average generation:"
                f" {_fmt_s(avg)}/image"
            )
            self._append(
                "Total generation + processing:"
                f" {_fmt_s(sum(self._gen_times) + sum(self._extra_times))}"
                f"  (wall clock incl. pauses: {_fmt_s(wall_s)})"
            )
        else:
            self._append("Images: 0")
        self._append(f"Run finished: {_now()}  ({stopped_why})")
        self._append("")


def run_sheet(
    sheet: Sheet,
    driver: SiteDriver,
    out_root: Path,
    timing: Timing,
    log: Log = print,
    should_stop: ShouldStop | None = None,
    post_save: PostSave | None = None,
    prompt_suffix: str | Callable[[str], str] = "",
    report: bool = True,
    only: set[str] | None = None,
) -> int:
    """Generate every pending item of a clean sheet; returns the count.

    The caller has already refused sheets with problems; skipped
    entries are logged here and never driven. ``only`` narrows the
    run to the owner's ticked drop paths (None = everything).
    """
    out_root.mkdir(parents=True, exist_ok=True)
    progress = Progress(out_root / (sheet.source.stem + PROGRESS_SUFFIX))
    run_report = (
        RunReport(
            out_root / (sheet.source.stem + REPORT_SUFFIX),
            sheet.theme,
            driver.site.name,
        )
        if report
        else None
    )

    for sk in sheet.skipped:
        log(f"  SKIP {sk.title} — {sk.reason}")

    queue = [it for it in sheet.items if not progress.is_done(it.drop_path)]
    already = len(sheet.items) - len(queue)
    if already:
        log(
            f"  RESUME: {already}/{len(sheet.items)} already done per"
            f" {progress.path.name}"
        )
    report_skips = list(sheet.skipped)
    if only is not None:
        # the owner's ticks decide everything — advice included
        selected = [it for it in queue if it.drop_path in only]
        if len(selected) != len(queue):
            log(
                f"  SELECTION: {len(selected)}/{len(queue)} pending"
                " item(s) ticked for this run"
            )
        queue = selected
    else:
        # no explicit selection: sheet-advised items sit out by default
        for it in (adv := [it for it in queue if it.advice]):
            log(f"  NOT RUN (sheet advice): {it.title} — {it.advice}")
            report_skips.append(
                SkippedItem(it.title, f"advice, not ticked: {it.advice}", it.line)
            )
        if adv:
            log(
                "  (tick them in 'Select images...' to generate them"
                " anyway)"
            )
            queue = [it for it in queue if not it.advice]
    if run_report is not None:
        run_report.start(len(queue), len(sheet.items), tuple(report_skips))

    start = time.monotonic()
    total = len(queue)
    generated = 0
    refused = 0
    fix_failures = 0
    stopped_why = "all pending items done"
    try:
        for idx, item in enumerate(queue, start=1):
            if should_stop is not None and should_stop():
                stopped_why = "stopped on request"
                log(f"  STOPPED on request — {generated}/{total} this run")
                break
            elapsed = time.monotonic() - start
            log(f"[{elapsed:7.1f}s] ({idx}/{total}) {item.title}")

            t_item = time.monotonic()
            # the suffix may depend on the prompt itself (Gemini's
            # aspect law: lancets portrait, badges square)
            suffix = (
                prompt_suffix(item.prompt)
                if callable(prompt_suffix)
                else prompt_suffix
            )
            try:
                driver.submit_prompt(item.prompt + suffix)
                driver.await_done(log)
                data = driver.extract_image()
            except ItemRefused as exc:
                refused += 1
                log(f"    REFUSED — {exc}")
                log(
                    "    continuing with the next item; rework the"
                    " prompt (or intervene manually) and rerun later"
                )
                if run_report is not None:
                    run_report.refused(item.drop_path, str(exc))
                if idx < total:
                    _pause(timing, should_stop, log)
                continue
            gen_s = time.monotonic() - t_item

            dest = out_root / item.drop_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            orig_res = _png_size(data)
            fmt = sniff_format(data)
            if fmt != dest.suffix.lstrip(".").lower():
                log(
                    f"    WARNING: bytes look like"
                    f" {fmt or 'an unknown format'}, saved as"
                    f" {dest.suffix} because the sheet names the file"
                )

            actions: list[str] = []
            extra_s = 0.0
            final_res = orig_res
            if post_save is not None:
                t_fix = time.monotonic()
                try:
                    action = post_save(dest)
                    actions.append(f"REMOVE BG: {action}")
                    log(f"    bgfix: {action}")
                except Exception as exc:
                    fix_failures += 1
                    actions.append("REMOVE BG: FAILED")
                    log(f"    BGFIX FAILED (image kept as saved): {exc}")
                extra_s = time.monotonic() - t_fix
                final_res = _png_size(dest.read_bytes())

            if run_report is not None:
                run_report.item(
                    item.drop_path, gen_s, extra_s, orig_res, final_res,
                    actions,
                )
            progress.mark_done(item.drop_path, dest)
            generated += 1
            log(f"    saved {dest} ({len(data):,} bytes)")

            if idx < total:
                _pause(timing, should_stop, log)
    except BaseException as exc:
        stopped_why = f"aborted: {type(exc).__name__}"
        raise
    finally:
        if run_report is not None:
            run_report.finish(
                generated, time.monotonic() - start, stopped_why
            )

    if refused:
        log(
            f"  NOTE: {refused} item(s) REFUSED by the site — listed in"
            " the report; rework those prompts and rerun"
        )
    if fix_failures:
        log(
            f"  NOTE: background fix failed on {fix_failures} image(s) —"
            " rerun painter/bg_remove.py over the output folder later"
        )
    return generated
