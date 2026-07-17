"""Golden tests for the sheet parser.

The goldens run against the REAL archetype sheets in
DOMY Watch research/prompts/archetype/ — the tool's first consumer.
Expected values were read from the sheets by hand, never from the
parser's own output.
"""

from pathlib import Path

import pytest

from painter.sheet_parser import SheetError, parse_sheet

ARCHETYPE_DIR = (
    Path(__file__).resolve().parents[2]
    / "DOMY Watch"
    / "research"
    / "prompts"
    / "archetype"
)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not ARCHETYPE_DIR.is_dir(),
    reason=f"golden sheets not found at {ARCHETYPE_DIR}",
)


def golden(name: str):
    return parse_sheet(ARCHETYPE_DIR / name)


# --- counts over all eight sheets ------------------------------------

GOLDEN_COUNTS = {
    # sheet: (items, skipped)
    "trinity_prompts.md": (7, 0),
    "family_prompts.md": (7, 0),
    "persons_prompts.md": (4, 2),
    "one_soul_prompts.md": (8, 0),
    "walks_prompts.md": (16, 0),
    # 4 approved + 4 tetramorph loaded as ADVICE-skipped items
    "temperaments_prompts.md": (8, 0),
    "calendar_prompts.md": (12, 0),
    "life_prompts.md": (16, 0),
}


@pytest.mark.parametrize("name", sorted(GOLDEN_COUNTS))
def test_golden_counts(name):
    sheet = golden(name)
    want_items, want_skipped = GOLDEN_COUNTS[name]
    assert [p.message for p in sheet.problems] == []
    assert len(sheet.items) == want_items
    assert len(sheet.skipped) == want_skipped


@pytest.mark.parametrize("name", sorted(GOLDEN_COUNTS))
def test_prompts_are_clean(name):
    sheet = golden(name)
    paths = [item.drop_path for item in sheet.items]
    assert len(paths) == len(set(paths)), "duplicate drop paths"
    for item in sheet.items:
        assert item.prompt.strip(), f"{item.title}: empty prompt"
        assert "```" not in item.prompt, f"{item.title}: fence leaked"


# --- trinity: the full (title, path) tuple set ------------------------

TRINITY_ENTRIES = [
    ("Jesus — the Advocate (blue arm, 04h)", "trinity/Jesus_Advocate.png"),
    ("The Devil — the Prosecutor (red arm, 20h)", "trinity/Devil_Prosecutor.png"),
    ("The One — the Judge (gold arm, 12h)", "trinity/One_Judge.png"),
    ("The Eye of Providence", "trinity/Providence_Eye.png"),
    ("The Advocate rondel", "trinity/rondel_Advocate.png"),
    ("The Prosecutor rondel", "trinity/rondel_Prosecutor.png"),
    ("The Judge rondel", "trinity/rondel_Judge.png"),
]


def test_trinity_titles_and_paths():
    sheet = golden("trinity_prompts.md")
    assert sheet.theme == (
        "Trinity Archetype Prompts (Gemini) — the Courtroom Trio and the Eye"
    )
    assert [(i.title, i.drop_path) for i in sheet.items] == TRINITY_ENTRIES


# The first person's prompt, byte-identical to the sheet.
JESUS_ADVOCATE_PROMPT = (
    "TALL pointed-arch lancet stained-glass window, night-window register, "
    "photorealistic render, isolated background, the window shape IS the "
    "lancet. Deep midnight-blue and silver glass throughout, no warm tones. "
    "Center: Jesus standing as a DEFENDER — placed between a kneeling, "
    "cowering accused and the surrounding dark, one arm extended "
    "protectively across the accused like a shield, the other hand open and "
    "raised in plea toward the light above; a cold white rose of light "
    "behind his head. Upper left panel: the accused woman shielded while "
    "dropped stones lie at the crowd's feet; upper right panel: the "
    "shepherd carrying the lamb home through night hills. Border: "
    "thorned-vine leadwork in blue-black; three rim roundels — an open "
    "protecting palm at the apex, a small shield at one side, a lamb at the "
    "other. Palette: midnight blue, silver-white light, blue-black lead. NO "
    "lettering anywhere."
)


def test_trinity_jesus_prompt_byte_identical():
    sheet = golden("trinity_prompts.md")
    assert sheet.items[0].prompt == JESUS_ADVOCATE_PROMPT


# The last entry of walks — proves end-of-file pairing too.
BELL_RONDEL_PROMPT = (
    "SMALL round stained-glass rondel, night-window register, "
    "photorealistic render, isolated background. A hand-bell beside an "
    "open sacred book, alb-ivory and cream glass, cross-and-lily leadwork "
    "rim. NO lettering anywhere."
)


def test_walks_bell_rondel_prompt_byte_identical():
    sheet = golden("walks_prompts.md")
    assert sheet.items[-1].title == "The Bell rondel"
    assert sheet.items[-1].drop_path == "walks/rondel_Bell.png"
    assert sheet.items[-1].prompt == BELL_RONDEL_PROMPT


# --- persons: REUSE seats are skipped, never generated ----------------

def test_persons_reuse_skipped():
    # the two REUSE seats have NO prompt in the sheet — nothing to
    # load, so they stay informational skips (not items)
    sheet = golden("persons_prompts.md")
    assert [s.title for s in sheet.skipped] == [
        "Lucifer — Pride (red arm, 20h)",
        "Judas — Weakness / Fear (blue arm, 04h)",
    ]
    for s in sheet.skipped:
        assert "REUSE" in s.reason
    generated = {i.drop_path for i in sheet.items}
    assert generated == {
        "persons/One_Love.png",
        "persons/Michael_Courage.png",
        "persons/Devil_Hatred.png",
        "persons/Jesus_Humility.png",
    }


# --- temperaments: the unapproved tetramorph section loads as ADVICE --

def test_temperaments_tetramorph_is_advice_not_law():
    sheet = golden("temperaments_prompts.md")
    normal = [i for i in sheet.items if i.advice is None]
    advised = [i for i in sheet.items if i.advice is not None]
    assert [i.drop_path for i in normal] == [
        "temperaments/Sanguine.png",
        "temperaments/Choleric.png",
        "temperaments/Melancholic.png",
        "temperaments/Phlegmatic.png",
    ]
    # the tetramorph rondels LOAD (prompt and all) but carry the
    # sheet's advice — the GUI unticks them by default
    assert [i.title for i in advised] == [
        "the Man/Angel rondel",
        "the Lion rondel",
        "the Ox rondel",
        "the Eagle rondel",
    ]
    for item in advised:
        assert "do not generate" in item.advice.lower()
        assert item.prompt.strip()  # the prompt IS loaded


# --- calendar: wrapped bold headings normalize to one line ------------

def test_calendar_wrapped_title_normalized():
    sheet = golden("calendar_prompts.md")
    november = next(
        i for i in sheet.items if i.drop_path == "calendar/November.png"
    )
    assert november.title == (
        "November (crimson-magenta `#FF0080`) — bare branches, "
        "the last harvest"
    )
    assert [i.drop_path for i in sheet.items] == [
        f"calendar/{m}.png"
        for m in (
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November",
            "December",
        )
    ]


# --- life: two registers share stems without colliding ----------------

def test_life_registers_do_not_collide():
    sheet = golden("life_prompts.md")
    paths = {i.drop_path for i in sheet.items}
    assert "life/tree/Unborn.png" in paths
    assert "life/animals/Unborn.png" in paths
    assert len(paths) == 16


# --- fixtures: contract violations are reported loudly ----------------

def test_unpaired_heading_reported():
    sheet = parse_sheet(FIXTURES_DIR / "unpaired.md")
    assert [i.title for i in sheet.items] == [
        "The Paired — a prompt follows (test, 02h)"
    ]
    assert len(sheet.problems) == 1
    assert "The Orphan" in sheet.problems[0].message


def test_no_h1_raises():
    with pytest.raises(SheetError):
        parse_sheet(FIXTURES_DIR / "no_h1.md")


def test_bad_paths_reported():
    sheet = parse_sheet(FIXTURES_DIR / "bad_paths.md")
    assert sheet.items == ()
    messages = " | ".join(p.message for p in sheet.problems)
    # an escaping path on a real (arrow) entry stays LOUD
    assert "../outside/Escape.png" in messages
    # an arrow at a non-image target is prose (drop-dir pointers in
    # the weekday sheets), silently ignored — no item, no problem
    assert "fixture/readme.txt" not in messages


def test_legacy_forms_parse():
    sheet = parse_sheet(FIXTURES_DIR / "legacy.md")
    assert [p.message for p in sheet.problems] == []
    assert [(i.title, i.drop_path) for i in sheet.items] == [
        ("Sun — Ancient of Days", "ancient_of_days.png"),
        ("Moon", "moon.png"),
        ("Aries", "sign/Aries.png"),
    ]
    assert sheet.items[0].prompt == "heading-form prompt"
    assert sheet.items[1].prompt == "bold-token prompt"
    assert sheet.items[2].prompt == "bare-bold prompt"
