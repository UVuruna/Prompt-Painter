"""The SHEET-GENERATOR flow (owner's #2) — split out of the
single-file ``painter/ai.py`` (root Rule #20, 2026-07-30).

Parse the model's numbered clarifying questions, build the two calls
from the sheet contract (``instructions.md``), validate a produced
``.md`` with the REAL sheet parser and drive ONE automatic repair
round, then save the clean sheet under ``sheets/`` with a slugged
filename.
"""

from __future__ import annotations

import re
from pathlib import Path

from painter.config import (
    AI_MAX_QUESTIONS,
    AI_QUESTIONS_SYSTEM,
    AI_REPAIR_PROMPT,
    AI_SHEET_REQUEST,
    AI_SHEET_SYSTEM,
    PROJECT_ROOT,
)
from painter.sheet_parser import SheetError, parse_sheet

from .client import generate_text



# "1. q" / "1) q" / "- q" / "* q" — the poll lines the model returns
_QUESTION_LINE = re.compile(r"^\s*(?:\d+[.)]\s*|[-*•]\s+)(.+?)\s*$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def contract_text() -> str:
    """instructions.md verbatim — the authoring contract both system
    prompts embed (the same doc the Instructions button shows)."""
    return (PROJECT_ROOT / "instructions.md").read_text(encoding="utf-8")


def parse_questions(text: str) -> list[str]:
    """The model's clarifying questions, capped at ``AI_MAX_QUESTIONS``.

    Accepts numbered ('1.' / '1)') and dash/star bullet lines; plain
    prose lines are ignored. An answer with NO parseable question
    lines returns [] — the caller then skips the poll and generates
    from the request alone.
    """
    questions: list[str] = []
    for line in text.splitlines():
        m = _QUESTION_LINE.match(line)
        if m and m.group(1).strip():
            questions.append(m.group(1).strip())
    return questions[:AI_MAX_QUESTIONS]


def ask_questions(request: str, contract: str, gen=None) -> list[str]:
    """FIRST call: the contract + 'questions only' system prompt.

    ``gen`` defaults to ``client.generate_text`` resolved at
    CALL time, so tests (and a mocked GUI run) can monkeypatch
    ``painter.ai.client.generate_text`` and the flow follows."""
    gen = gen or generate_text
    system = AI_QUESTIONS_SYSTEM.format(
        contract=contract, max_q=AI_MAX_QUESTIONS
    )
    return parse_questions(gen(request, system))


def qa_block(questions: list[str], answers: list[str]) -> str:
    """The answered poll as Q/A lines; a skipped (blank) answer is an
    explicit 'no preference' so the model still decides something."""
    lines: list[str] = []
    for question, answer in zip(questions, answers):
        lines.append(f"Q: {question}")
        lines.append(f"A: {answer.strip() or '(no preference — your choice)'}")
    return "\n".join(lines) or "(no questions were asked)"


def strip_md_fence(text: str) -> str:
    """Unwrap a whole-file ``` fence pair (models wrap the sheet in one
    despite instructions). ONLY the exact wrapper case is touched — a
    body not starting with a fence, or not ending with a bare closing
    fence, passes through byte-identical so the sheet's own inner
    prompt fences always survive."""
    body = text.strip()
    if not body.startswith("```"):
        return text
    lines = body.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return text
    return "\n".join(lines[1:-1])


def validate_sheet_md(md: str, work_dir: Path) -> tuple[list[str], str | None]:
    """Parse ``md`` with the REAL parser (on a scratch file under
    ``work_dir``) and return ``(problem strings, theme)`` — an empty
    problem list means the sheet is contract-clean and loadable."""
    tmp = Path(work_dir) / "_ai_sheet_validate.md"
    tmp.write_text(md, encoding="utf-8")
    try:
        sheet = parse_sheet(tmp)
    except SheetError:
        return ["no '# ' H1 theme heading — not a prompt sheet"], None
    return (
        [f"L{p.line}: {p.message}" for p in sheet.problems],
        sheet.theme,
    )


def generate_sheet(
    request: str,
    questions: list[str],
    answers: list[str],
    contract: str,
    work_dir: Path,
    gen=None,
    log=print,
) -> tuple[str, list[str], str | None]:
    """SECOND call + at most ONE automatic repair round.

    Returns ``(md, problems, theme)``: ``problems == []`` means the md
    passed the real parser and may be saved/loaded; otherwise ``md`` is
    the best (repaired) attempt for the owner to fix manually — the
    caller must NOT load it. ``gen`` resolves to ``generate_text`` at
    CALL time (monkeypatch-friendly, like ``ask_questions``).
    """
    gen = gen or generate_text
    system = AI_SHEET_SYSTEM.format(contract=contract)
    user = AI_SHEET_REQUEST.format(
        request=request, qa=qa_block(questions, answers)
    )
    md = strip_md_fence(gen(user, system))
    problems, theme = validate_sheet_md(md, work_dir)
    if problems:
        log(
            f"AI sheet fails the parser ({len(problems)} problem(s)) —"
            " one automatic repair round"
        )
        repair = AI_REPAIR_PROMPT.format(
            problems="\n".join(problems), md=md
        )
        md = strip_md_fence(gen(repair, system))
        problems, theme = validate_sheet_md(md, work_dir)
    return md, problems, theme


def slug_for(theme: str) -> str:
    """A filesystem-safe stem from the sheet's H1 theme."""
    slug = _SLUG_STRIP.sub("_", theme.lower()).strip("_")
    return slug or "ai_sheet"


def save_sheet(md: str, theme: str, sheets_dir: Path) -> Path:
    """Write a VALIDATED sheet under ``sheets_dir`` (created on demand)
    with a slugged, collision-free filename; returns the path."""
    sheets_dir = Path(sheets_dir)
    sheets_dir.mkdir(parents=True, exist_ok=True)
    base = slug_for(theme)
    path = sheets_dir / f"{base}.md"
    n = 2
    while path.exists():
        path = sheets_dir / f"{base}_{n}.md"
        n += 1
    path.write_text(md, encoding="utf-8")
    return path
