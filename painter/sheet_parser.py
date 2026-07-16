"""Sheet parser — PromptPainter's side of the sheet contract.

Pure and offline: stdlib only, no browser anywhere near it. The
contract (project CLAUDE.md):

1. The ``# H1`` names the theme.
2. An image entry is a ``**Bold heading** -> `drop/path.png```
   paragraph — the arrow line carries the OUTPUT FILENAME. Headings
   and paths wrap across lines; plain text may sit between the bold
   span and the arrow.
3. The FIRST fenced code block after the entry is the prompt, taken
   byte-identical.
4. Entries marked REUSE / SUPERSEDED / DO NOT GENERATE are logged as
   skipped, never generated. The marker must sit inside a bold span:
   in a span after the title it marks that one entry; alone in a
   paragraph's first span (no drop path) it is a section note that
   skips every entry until the next heading; in a section heading it
   skips the whole section.
5. A heading the parser cannot pair with a prompt is REPORTED loudly
   (the fix belongs in the sheet, not in parser leniency).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from painter.config import IMAGE_EXTENSIONS, SKIP_MARKER_PATTERN

_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ARROW_PATH = re.compile(r"→\s*`([^`\n]+)`")
_SKIP_MARKER = re.compile(SKIP_MARKER_PATTERN, re.IGNORECASE)
_WS = re.compile(r"\s+")


class SheetError(Exception):
    """The file is not a prompt sheet at all (no H1 theme)."""


@dataclass(frozen=True)
class PromptItem:
    """One image to generate."""

    title: str      # the bold heading, whitespace-normalized
    drop_path: str  # POSIX-relative output path from the arrow line
    prompt: str     # the fenced block content, byte-identical
    line: int       # 1-based line of the entry heading


@dataclass(frozen=True)
class SkippedItem:
    """An entry the sheet marks as not-to-generate."""

    title: str
    reason: str  # the marker span or section note that skipped it
    line: int


@dataclass(frozen=True)
class Problem:
    """A contract violation to report loudly."""

    message: str
    line: int


@dataclass(frozen=True)
class Sheet:
    """One parsed prompt sheet."""

    theme: str
    source: Path
    items: tuple[PromptItem, ...]
    skipped: tuple[SkippedItem, ...]
    problems: tuple[Problem, ...]


def parse_sheet(path: Path) -> Sheet:
    """Parse one sheet file into its queue, skips and problems."""
    lines = path.read_text(encoding="utf-8").split("\n")
    n = len(lines)

    theme: str | None = None
    items: list[PromptItem] = []
    skipped: list[SkippedItem] = []
    problems: list[Problem] = []

    # entry awaiting its prompt block: (title, drop_path, line)
    pending: tuple[str, str, int] | None = None
    # active skip reason from a marked section heading or note;
    # cleared by the next heading
    poison: str | None = None

    def flush_pending(why: str) -> None:
        nonlocal pending
        if pending is not None:
            title, _, at = pending
            problems.append(
                Problem(f'entry "{title}" has no prompt block ({why})', at)
            )
            pending = None

    i = 0
    while i < n:
        raw = lines[i]

        if raw.startswith("```"):
            fence_at = i + 1
            block: list[str] = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            if i >= n:
                problems.append(
                    Problem("unterminated fenced code block", fence_at)
                )
            i += 1
            if pending is not None:
                title, drop, at = pending
                items.append(PromptItem(title, drop, "\n".join(block), at))
                pending = None
            continue

        if raw.startswith("#"):
            flush_pending("a heading interrupts it")
            heading = raw.lstrip("#").strip()
            if theme is None and raw.startswith("# "):
                theme = heading
            poison = heading if _SKIP_MARKER.search(heading) else None
            i += 1
            continue

        if not raw.strip():
            i += 1
            continue

        # a paragraph: consecutive non-blank lines up to a fence/heading
        start = i + 1
        para_lines = [raw]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not lines[i].startswith("```")
            and not lines[i].startswith("#")
        ):
            para_lines.append(lines[i])
            i += 1
        para = "\n".join(para_lines)

        if not para.startswith("**"):
            continue  # prose or an *(italic note)* — not an entry

        spans = _BOLD_SPAN.findall(para)
        title = _WS.sub(" ", spans[0]).strip() if spans else ""
        arrow = _ARROW_PATH.search(para)
        marker_idx = next(
            (k for k, s in enumerate(spans) if _SKIP_MARKER.search(s)), None
        )

        if marker_idx is not None:
            flush_pending("a skip-marked paragraph interrupts it")
            reason = _WS.sub(" ", spans[marker_idx]).strip()
            if arrow is not None or marker_idx > 0:
                # a named entry marked as skipped
                skipped.append(SkippedItem(title, reason, start))
            else:
                # a standalone note — skips the rest of the section
                poison = reason
            continue

        if arrow is None:
            continue  # bold prose (**Register:**, **Drop paths:**, ...)

        drop = arrow.group(1).strip()
        drop_parts = PurePosixPath(drop)
        if drop_parts.is_absolute() or ".." in drop_parts.parts:
            problems.append(
                Problem(
                    f'entry "{title}": drop path escapes the out'
                    f" folder: {drop}",
                    start,
                )
            )
            continue
        if drop_parts.suffix.lower() not in IMAGE_EXTENSIONS:
            problems.append(
                Problem(
                    f'entry "{title}": arrow line does not name an'
                    f" image file: {drop}",
                    start,
                )
            )
            continue

        flush_pending("the next entry starts")

        if poison is not None:
            skipped.append(SkippedItem(title, poison, start))
            continue

        if any(item.drop_path == drop for item in items):
            problems.append(
                Problem(
                    f'entry "{title}": duplicate drop path {drop} —'
                    " an earlier entry already writes it",
                    start,
                )
            )
            continue

        pending = (title, drop, start)

    flush_pending("the sheet ends")

    if theme is None:
        raise SheetError(
            f"{path}: no '# ' H1 theme heading — not a prompt sheet"
        )
    if not items and not skipped:
        problems.append(Problem("sheet contains no image entries", 1))

    return Sheet(
        theme=theme,
        source=path,
        items=tuple(items),
        skipped=tuple(skipped),
        problems=tuple(problems),
    )
