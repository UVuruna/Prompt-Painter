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
4. Skip markers (REUSE / SUPERSEDED / DO NOT GENERATE, inside bold
   spans) are ADVICE, not law: an entry that still carries a drop
   path and a prompt LOADS as an item with ``advice`` set — the
   callers untick it by default. A marker in a span after the title
   advises that entry; alone in a paragraph's first span it advises
   the rest of the section; in a section heading it advises the
   whole section. Marked entries with NO prompt (the REUSE seats)
   become informational ``SkippedItem``s — nothing to load.
5. A heading the parser cannot pair with a prompt is REPORTED loudly
   (the fix belongs in the sheet, not in parser leniency) — unless
   it is advice-marked, in which case it is a retired entry, listed,
   never a violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from painter.config import IMAGE_EXTENSIONS, SKIP_MARKER_PATTERN

_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ARROW_PATH = re.compile(r"→\s*`([^`\n]+)`")
_BACKTICK_TOKEN = re.compile(r"`([^`\n]+)`")
# the whole paragraph is "**Name** — `file.png`" (dash optional)
_STRICT_BOLD_TOKEN = re.compile(
    r"\*\*.+?\*\*\s*(?:[—–-]{1,3}\s*)?`[^`\n]+`\s*\.?", re.DOTALL
)
_PAREN_TOKEN = re.compile(r"\s*\((?:[^()`]*`[^`]*`)+[^()]*\)")
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
    # a skip marker on the entry or its section (REUSE, SUPERSEDED,
    # DO NOT GENERATE ...) — ADVICE, not law (owner 2026-07-17): the
    # item still loads, but runs only when explicitly ticked
    advice: str | None = None


@dataclass(frozen=True)
class SkippedItem:
    """A marked entry with NO prompt in the sheet — nothing to load."""

    title: str
    reason: str  # the marker span or section note
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

    # entry awaiting its prompt block:
    # (title, drop_path, line, advice, legacy)
    # legacy entries (heading/bold-token forms) are best-effort: they
    # pair only with an IMMEDIATELY following fence and never raise
    # problems — the strict arrow contract keeps the loud failures
    pending: tuple[str, str, int, str | None, bool] | None = None
    # active advice from a marked section heading or note;
    # cleared by the next heading
    poison: str | None = None
    # legacy sheets: a section heading carrying one backticked
    # directory token (`assets/zodiac/astrology/sign/`) — bare bold
    # entries below it drop into <last-segment>/<Name>.png
    section_dir: str | None = None

    def flush_pending(why: str) -> None:
        nonlocal pending
        if pending is not None:
            title, _, at, advice, legacy = pending
            if advice is not None:
                # a marked entry with no prompt block — retired; listed,
                # never a contract violation
                skipped.append(SkippedItem(title, advice, at))
            elif not legacy:
                problems.append(
                    Problem(
                        f'entry "{title}" has no prompt block ({why})', at
                    )
                )
            # unpaired LEGACY mentions (reuse pointers etc.) drop silently
            pending = None

    def register_entry(
        title: str, drop: str, at: int, advice: str | None, legacy: bool
    ) -> None:
        """Validate a drop path and set the entry pending.

        Legacy-form entries never raise problems: an invalid or
        duplicate path there is a reuse pointer, not an entry.
        """
        nonlocal pending
        drop_parts = PurePosixPath(drop)
        if drop_parts.is_absolute() or ".." in drop_parts.parts:
            if not legacy:
                problems.append(
                    Problem(
                        f'entry "{title}": drop path escapes the out'
                        f" folder: {drop}",
                        at,
                    )
                )
            return
        if drop_parts.suffix.lower() not in IMAGE_EXTENSIONS:
            if not legacy:
                problems.append(
                    Problem(
                        f'entry "{title}": the entry does not name an'
                        f" image file: {drop}",
                        at,
                    )
                )
            return
        if any(item.drop_path == drop for item in items):
            if not legacy:
                problems.append(
                    Problem(
                        f'entry "{title}": duplicate drop path {drop} —'
                        " an earlier entry already writes it",
                        at,
                    )
                )
            return
        pending = (title, drop, at, advice, legacy)

    def png_tokens_of(text: str) -> list[str]:
        return [
            t.strip()
            for t in _BACKTICK_TOKEN.findall(text)
            if PurePosixPath(t.strip()).suffix.lower() in IMAGE_EXTENSIONS
        ]

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
                title, drop, at, advice, _legacy = pending
                items.append(
                    PromptItem(title, drop, "\n".join(block), at, advice)
                )
                pending = None
            continue

        if raw.startswith("#"):
            flush_pending("a heading interrupts it")
            heading = raw.lstrip("#").strip()
            if theme is None and raw.startswith("# "):
                theme = heading
                i += 1
                continue
            heading_pngs = png_tokens_of(heading)
            if len(heading_pngs) == 1 and not raw.startswith("# "):
                # legacy heading entry: "### Sun (`sun.png`)" — the
                # heading itself carries the output filename
                title = _WS.sub(
                    " ", _PAREN_TOKEN.sub("", heading)
                ).strip(" -—")
                advice = (
                    heading if _SKIP_MARKER.search(heading) else poison
                )
                register_entry(
                    title or heading, heading_pngs[0], i + 1, advice,
                    legacy=True,
                )
            else:
                # a section heading: may advise (skip marker) and may
                # set the drop dir for bare bold entries below
                poison = (
                    heading if _SKIP_MARKER.search(heading) else None
                )
                dirs = [
                    t.strip()
                    for t in _BACKTICK_TOKEN.findall(heading)
                    if t.strip().endswith("/")
                ]
                section_dir = (
                    PurePosixPath(dirs[0]).name if len(dirs) == 1 else None
                )
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
        para_pngs = png_tokens_of(para)
        marker_idx = next(
            (k for k, s in enumerate(spans) if _SKIP_MARKER.search(s)), None
        )

        reason = (
            _WS.sub(" ", spans[marker_idx]).strip()
            if marker_idx is not None
            else None
        )

        # where does this entry's output path come from?
        drop: str | None = None
        legacy = False
        if arrow is not None and not title.endswith(":"):
            candidate = arrow.group(1).strip()
            if (
                PurePosixPath(candidate).suffix.lower()
                in IMAGE_EXTENSIONS
            ):
                drop = candidate
            # else: an arrow inside prose ("Drop dirs" pointing at a
            # folder) — not an entry
        if drop is None and arrow is None and (
            len(para_pngs) == 1
            and not title.endswith(":")
            and _STRICT_BOLD_TOKEN.fullmatch(para.strip())
        ):
            # legacy bold entry — the WHOLE paragraph is
            # "**Sun** — `sun.png`" (prose mentions never match)
            drop = para_pngs[0]
            legacy = True
        elif (
            section_dir is not None
            and marker_idx is None
            and para.strip() == f"**{spans[0]}**"
            and "`" not in spans[0]
            and len(title) < 40
        ):
            # legacy bare bold entry under a dir-carrying section:
            # "**Aries**" below "## SIGN look (`.../sign/`)"
            drop = f"{section_dir}/{title}.png"
            legacy = True

        if drop is None:
            if marker_idx is not None:
                flush_pending("a skip-marked paragraph interrupts it")
                if marker_idx > 0:
                    # a named entry with NO prompt to load (REUSE seats)
                    skipped.append(SkippedItem(title, reason, start))
                else:
                    # a standalone note — advice for the section's rest
                    poison = reason
            continue  # else: bold prose (**Register:**, **Drop paths:**)

        flush_pending("the next entry starts")

        # the entry's own marker outranks the section's advice; either
        # way the prompt LOADS — advice only unticks it by default
        register_entry(title, drop, start, reason or poison, legacy)

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
