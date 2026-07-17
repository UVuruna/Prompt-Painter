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

from painter.config import (
    PROGRESS_SUFFIX,
    REPORT_SUFFIX,
    SAFER_PREAMBLE,
    STATE_DIRNAME,
    Timing,
    dest_for,
    fmt_duration,
    fmt_size,
)
from painter.driver import ItemRefused, SiteDriver, sniff_format
from painter.sheet_parser import Sheet, SkippedItem

Log = Callable[[str], None]
# GUI stop button etc.; checked between items and during the pause
ShouldStop = Callable[[], bool]
# background fix: (saved file) -> action string; exceptions are logged
PostSave = Callable[[Path], str]
# structured progress events for dashboards: receives dicts like
# {"type": "item_done", "gen_s": 41.2} — see run_sheet for the types
OnEvent = Callable[[dict], None]

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> str:
    """WxH from a PNG header (all saved images are PNG), else '?'."""
    if len(data) >= 24 and data.startswith(_PNG_MAGIC):
        width, height = struct.unpack(">II", data[16:24])
        return f"{width}x{height}"
    return "?"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
        self._over_times: list[float] = []
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
        over_s: float,
        orig_res: str,
        final_res: str,
        size_bytes: int,
        actions: list[str],
    ) -> None:
        self._gen_times.append(gen_s)
        self._over_times.append(over_s)
        note = f"  [{', '.join(actions)}]" if actions else ""
        resolution = (
            f"{orig_res} -> {final_res}"
            if final_res not in ("", orig_res)
            else orig_res
        )
        self._append(
            f"{_now()}  {drop_path:<44} gen {gen_s:6.1f}s"
            f"  ours {over_s:6.1f}s  {resolution:>21}"
            f"  {fmt_size(size_bytes):>8}{note}"
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
            n = len(self._gen_times)
            avg_gen = sum(self._gen_times) / n
            avg_over = sum(self._over_times) / n
            self._append(
                f"Images: {generated}  |  average generation (AI):"
                f" {fmt_duration(avg_gen)}/image  |  average our time"
                f" (save+bgfix+pause): {fmt_duration(avg_over)}/image"
            )
            self._append(
                "Total AI + our time:"
                f" {fmt_duration(sum(self._gen_times) + sum(self._over_times))}"
                f"  (wall clock: {fmt_duration(wall_s)})"
            )
        else:
            self._append("Images: 0")
        self._append(f"Run finished: {_now()}  ({stopped_why})")
        self._append("")


def run_sheet(
    sheet: Sheet,
    driver: SiteDriver,
    out_base: Path,
    site_key: str,
    timing: Timing,
    log: Log = print,
    should_stop: ShouldStop | None = None,
    post_save: PostSave | None = None,
    prompt_suffix: str | Callable[[str], str] = "",
    report: bool = True,
    only: set[str] | None = None,
    on_event: OnEvent | None = None,
    safer_retry: bool = False,
) -> int:
    """Generate every pending item of a clean sheet; returns the count.

    Saves land at ``out_base / dest_for(drop, site_key)`` — the
    assets-mirroring layout. Run state and the report live under
    ``out_base/_state/<site>/`` so the image tree stays copy-ready.
    The caller has already refused sheets with problems; skipped
    entries are logged here and never driven. ``only`` narrows the
    run to the owner's ticked drop paths (None = everything).
    """
    state_dir = out_base / STATE_DIRNAME / site_key
    state_dir.mkdir(parents=True, exist_ok=True)
    progress = Progress(state_dir / (sheet.source.stem + PROGRESS_SUFFIX))
    run_report = (
        RunReport(
            state_dir / (sheet.source.stem + REPORT_SUFFIX),
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

    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    def generate_one(text: str) -> tuple[bytes, float]:
        """Submit one prompt and return (image bytes, send timestamp).

        The send timestamp marks when SEND was pressed, so the caller
        can time the pure generation (send -> image) apart from the
        input hesitation inside submit_prompt.
        """
        driver.submit_prompt(text)
        t_send = time.monotonic()
        driver.await_done(log)
        return driver.extract_image(), t_send

    emit(
        {
            "type": "sheet_start",
            "sheet": sheet.source.name,
            "pending": len(queue),
            "total": len(sheet.items),
        }
    )

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
            emit(
                {
                    "type": "item_start",
                    "title": item.title,
                    "idx": idx,
                    "of": total,
                }
            )

            # the suffix may depend on the prompt itself (Gemini's
            # aspect law: lancets portrait, badges square)
            suffix = (
                prompt_suffix(item.prompt)
                if callable(prompt_suffix)
                else prompt_suffix
            )
            base = item.prompt + suffix
            try:
                data, t_send = generate_one(base)
            except ItemRefused as exc:
                reason = str(exc)
                data = None
                if safer_retry:
                    log("    REFUSED — one safer retry (allegory note) ...")
                    emit({"type": "item_retry"})
                    try:
                        data, t_send = generate_one(SAFER_PREAMBLE + base)
                        log("    safer retry SUCCEEDED")
                    except ItemRefused as exc2:
                        reason = str(exc2)
                if data is None:
                    refused += 1
                    log(f"    REFUSED — {reason}")
                    log(
                        "    continuing with the next item; rework the"
                        " prompt (or intervene manually) and rerun later"
                    )
                    if run_report is not None:
                        run_report.refused(item.drop_path, reason)
                    emit(
                        {
                            "type": "item_refused",
                            "drop_path": item.drop_path,
                        }
                    )
                    if idx < total:
                        _pause(timing, should_stop, log)
                    continue
            t_image = time.monotonic()
            gen_s = t_image - t_send

            dest = out_base / dest_for(item.drop_path, site_key)
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
            if post_save is not None:
                try:
                    action = post_save(dest)
                    actions.append(f"REMOVE BG: {action}")
                    log(f"    bgfix: {action}")
                except Exception as exc:
                    fix_failures += 1
                    actions.append("REMOVE BG: FAILED")
                    log(f"    BGFIX FAILED (image kept as saved): {exc}")

            saved_bytes = dest.read_bytes()
            size = len(saved_bytes)
            final_res = _png_size(saved_bytes)
            progress.mark_done(item.drop_path, dest)  # resume-safe now
            generated += 1
            log(f"    saved {dest} ({size:,} bytes)")
            # count it live right away (dashboard progress + generate
            # avg) — carries everything the dashboard needs to add the
            # image to its table now, except our-time (needs the pause)
            emit(
                {
                    "type": "item_progress",
                    "idx": idx,
                    "of": total,
                    "title": item.title,
                    "drop_path": item.drop_path,
                    "gen_s": gen_s,
                    "orig_res": orig_res,
                    "final_res": final_res,
                    "size": size,
                }
            )

            # OUR time = everything from the image appearing to the next
            # SEND: save + background fix + the paced pause (owner
            # 2026-07-17: "sve se računa"). The pause is timed here so it
            # belongs to this image's overhead; the last image has none.
            if idx < total:
                _pause(timing, should_stop, log)
            over_s = time.monotonic() - t_image

            if run_report is not None:
                run_report.item(
                    item.drop_path, gen_s, over_s, orig_res, final_res,
                    size, actions,
                )
            emit(
                {
                    "type": "item_done",
                    "title": item.title,
                    "drop_path": item.drop_path,
                    "gen_s": gen_s,
                    "over_s": over_s,
                    "orig_res": orig_res,
                    "final_res": final_res,
                    "size": size,
                }
            )
    except BaseException as exc:
        stopped_why = {
            "TerminalState": "quota / rate limit — stopped",
            "GenerationTimeout": "generation timed out",
        }.get(type(exc).__name__, f"aborted: {type(exc).__name__}")
        raise
    finally:
        if run_report is not None:
            run_report.finish(
                generated, time.monotonic() - start, stopped_why
            )
        emit({"type": "sheet_done", "generated": generated})

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
