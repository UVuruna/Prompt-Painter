"""The per-sheet run report writer (THE STRUCTURE LAW split, faza 2
2026-08-03 — report writing is its own responsibility; pulled out of
``painter/runner.py`` when the run loop outgrew the god-file line
guard).

``RunReport`` appends ``<out>/_state/<site>/<sheet-stem>_report.txt``
INCREMENTALLY — header, then a line per image, then the summary — so an
interrupted run keeps every finished line ("sve se računa", owner
2026-07-18: run start/finish timestamps, per-image GENERATE time and
OUR time, original -> final resolution, file size, extra actions, the
averages and the collection total).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from painter.config import fmt_duration, fmt_size


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
