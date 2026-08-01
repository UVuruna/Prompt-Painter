"""Offline tests for the AI sheet-generator flow — NO live API.

Split from the former ``test_ai.py`` god-file (root Rule #20, second
round — the source split into ``painter/ai/`` 2026-07-30, this test
module follows it 1:1: everything ``painter/ai/sheet_flow.py`` exports —
the owner's #2 feature: questions, contract, validate-and-repair, save.
"""

from painter import ai
from painter.config import AI_MAX_QUESTIONS


def test_parse_questions_reads_numbered_and_bulleted_lines():
    text = (
        "Here is what I need to know:\n"
        "1. How many images?\n"
        "2) Which drop folder?\n"
        "- Transparent or white background?\n"
        "* Rondel or lancet shape?\n"
        "Thanks!\n"
    )
    assert ai.parse_questions(text) == [
        "How many images?",
        "Which drop folder?",
        "Transparent or white background?",
        "Rondel or lancet shape?",
    ]


def test_parse_questions_caps_at_the_config_maximum():
    text = "\n".join(f"{n}. Question {n}?" for n in range(1, 11))
    assert len(ai.parse_questions(text)) == AI_MAX_QUESTIONS


def test_parse_questions_empty_on_prose():
    assert ai.parse_questions("I have no questions, generating now.") == []


def test_qa_block_marks_skipped_answers():
    block = ai.qa_block(["Count?", "Folder?"], ["12", "  "])
    assert "Q: Count?" in block and "A: 12" in block
    assert "A: (no preference — your choice)" in block


def test_strip_md_fence_unwraps_only_the_whole_file_wrapper():
    inner = "# Theme\n\n**A** → `assets/badge/t/A.png`\n\n```\nprompt\n```\n"
    wrapped = f"```markdown\n{inner}```"
    out = ai.strip_md_fence(wrapped)
    assert out == inner.rstrip("\n")
    # the unwrap keeps the INNER prompt fence pair intact
    assert out.count("```") == 2
    assert out.lstrip().startswith("# Theme")
    # an unwrapped sheet passes through byte-identical
    assert ai.strip_md_fence(inner) == inner


VALID_MD = (
    "# Astro Test\n\n"
    "**Sun** → `assets/zodiac/astro/Sun.png`\n\n"
    "```\nA radiant sun rondel.\n```\n\n"
    "**Moon** → `assets/zodiac/astro/Moon.png`\n\n"
    "```\nA silver moon rondel.\n```\n"
)
BROKEN_MD = (
    "# Astro Test\n\n"
    "**Sun** → `assets/zodiac/astro/Sun.png`\n\n"
    "no prompt block follows — a contract violation\n"
)


def test_validate_sheet_md_clean_and_broken(tmp_path):
    problems, theme = ai.validate_sheet_md(VALID_MD, tmp_path)
    assert problems == []
    assert theme == "Astro Test"
    problems, _theme = ai.validate_sheet_md(BROKEN_MD, tmp_path)
    assert problems and "no prompt block" in problems[0]
    problems, theme = ai.validate_sheet_md("just prose\n", tmp_path)
    assert theme is None and "H1" in problems[0]


def test_generate_sheet_repairs_once_and_validates(tmp_path):
    calls: list[tuple[str, str]] = []

    def gen(prompt, system=None, **_kw):
        calls.append((prompt, system))
        # first (generation) call returns a BROKEN sheet, the repair
        # call returns the fixed one — wrapped in a fence the flow strips
        if len(calls) == 1:
            return BROKEN_MD
        return f"```markdown\n{VALID_MD}```"

    logs: list[str] = []
    md, problems, theme = ai.generate_sheet(
        "12 astrology images", ["Count?"], ["12"], "THE CONTRACT",
        tmp_path, gen=gen, log=logs.append,
    )
    assert problems == []
    assert theme == "Astro Test"
    assert md.lstrip().startswith("# Astro Test")
    assert len(calls) == 2
    # the generation call carries the request + the answered poll in the
    # user prompt and the contract in the system prompt
    assert "12 astrology images" in calls[0][0]
    assert "Q: Count?" in calls[0][0] and "A: 12" in calls[0][0]
    assert "THE CONTRACT" in calls[0][1]
    # the repair call feeds the parser problems + the broken md back
    assert "no prompt block" in calls[1][0]
    assert BROKEN_MD.strip() in calls[1][0]
    assert any("repair round" in line for line in logs)


def test_generate_sheet_still_broken_reports_problems(tmp_path):
    md, problems, _theme = ai.generate_sheet(
        "req", [], [], "contract", tmp_path,
        gen=lambda p, s=None, **_k: BROKEN_MD, log=lambda _l: None,
    )
    assert problems  # the caller must NOT load this md
    assert md == BROKEN_MD


def test_generate_sheet_valid_first_try_skips_the_repair(tmp_path):
    calls = []

    def gen(prompt, system=None, **_kw):
        calls.append(prompt)
        return VALID_MD

    _md, problems, _theme = ai.generate_sheet(
        "req", [], [], "contract", tmp_path, gen=gen, log=lambda _l: None
    )
    assert problems == []
    assert len(calls) == 1  # no repair round needed


def test_save_sheet_slugs_and_never_collides(tmp_path):
    sheets = tmp_path / "sheets"
    first = ai.save_sheet("# x\n", "Astrology — Zodiac Set!", sheets)
    second = ai.save_sheet("# y\n", "Astrology — Zodiac Set!", sheets)
    assert first.name == "astrology_zodiac_set.md"
    assert second.name == "astrology_zodiac_set_2.md"
    assert first.read_text(encoding="utf-8") == "# x\n"
