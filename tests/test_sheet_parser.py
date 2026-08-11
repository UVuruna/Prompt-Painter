"""Golden tests for the sheet parser.

The goldens run against the REAL archetype sheets in
Watch Academy research/prompts/archetype/ — the tool's first consumer.
Expected values were read from the sheets by hand, never from the
parser's own output.

Expected paths follow the DOMY ONE-HIERARCHY structure (Watch Academy
RESTRUCTURE.md, owner-sealed 2026-07-22; goldens re-read from the
rewritten sheets 2026-07-27): `assets/<category>/<family>/<register
subfolders>/<Figure>.png` — e.g. `archetypes/trinity/primary/colored/`
— with the generator NEVER in the path (PromptPainter adds it as the
terminal filename suffix). That structure is final; if a golden ever
fails again, the SHEET changed — re-read it by hand, per the rule
above.
"""

from pathlib import Path

import pytest

from painter.sheet_parser import SheetError, parse_sheet

ARCHETYPE_DIR = (
    Path(__file__).resolve().parents[2]
    / "Watch Academy"
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
    # 4 archetypes + the Prism center Seal + Lucifer/Judas, whose REUSE
    # seats were given full prompts (DOMY, so now generated not skipped)
    "persons_prompts.md": (7, 0),
    "one_soul_prompts.md": (8, 0),
    "walks_prompts.md": (16, 0),
    # 4 temperaments + the 4 tetramorph (approved 2026-07-17, moved
    # to archetype/tetramorph/) + the 4 evangelist rondels (three-side
    # second column, SEALED 2026-07-18, archetype/evangelist/) + the
    # Throne center (DOMY 0.14.322)
    "temperaments_prompts.md": (13, 0),
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
    ("Jesus — the Advocate (blue arm, 04h)", "assets/archetypes/trinity/primary/colored/Jesus_Advocate.png"),
    ("The Devil — the Prosecutor (red arm, 20h)", "assets/archetypes/trinity/primary/colored/Devil_Prosecutor.png"),
    ("The One — the Judge (gold arm, 12h)", "assets/archetypes/trinity/primary/colored/One_Judge.png"),
    ("The Eye of Providence", "assets/archetypes/trinity/primary/colored/Providence_Eye.png"),
    ("The Advocate rondel", "assets/archetypes/trinity/primary/colored/Rondel_Advocate.png"),
    ("The Prosecutor rondel", "assets/archetypes/trinity/primary/colored/Rondel_Prosecutor.png"),
    ("The Judge rondel", "assets/archetypes/trinity/primary/colored/Rondel_Judge.png"),
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
    assert sheet.items[-1].drop_path == (
        "assets/archetypes/walks/primary/colored/Rondel_Bell.png"
    )
    assert sheet.items[-1].prompt == BELL_RONDEL_PROMPT


# --- persons: the former REUSE seats now carry prompts, so generate ---

def test_persons_all_generate():
    # Lucifer/Judas were REUSE seats with no prompt; DOMY later gave
    # them full prompts, so they now LOAD as items — nothing is skipped
    sheet = golden("persons_prompts.md")
    assert sheet.skipped == ()
    generated = {i.drop_path for i in sheet.items}
    assert generated == {
        "assets/archetypes/persons/primary/colored/One_Love.png",
        "assets/archetypes/persons/primary/colored/Michael_Courage.png",
        "assets/archetypes/persons/primary/colored/Devil_Hatred.png",
        "assets/archetypes/persons/primary/colored/Jesus_Humility.png",
        "assets/archetypes/persons/primary/colored/Lucifer_Pride.png",
        "assets/archetypes/persons/primary/colored/Judas_Fear.png",
        "assets/archetypes/persons/primary/colored/Seal.png",
    }


# --- temperaments: tetramorph approved + the Throne center ------------

def test_temperaments_tetramorph_now_approved():
    # the tetramorph was owner-APPROVED 2026-07-17 and moved to its
    # own archetype/tetramorph/ drop (DOMY 0.14.322) — no advice left
    sheet = golden("temperaments_prompts.md")
    assert all(i.advice is None for i in sheet.items)
    paths = [i.drop_path for i in sheet.items]
    assert "assets/archetypes/tetramorph/primary/colored/Man.png" in paths
    assert "assets/archetypes/tetramorph/primary/colored/Eagle.png" in paths
    assert "assets/archetypes/temperaments/primary/colored/Throne.png" in paths
    # the sheet is BOM-prefixed since 0.14.322 — utf-8-sig must
    # still see the H1
    assert sheet.theme.startswith("Seasons Archetype Prompts")


# --- calendar: wrapped bold headings normalize to one line ------------

def test_calendar_wrapped_title_normalized():
    sheet = golden("calendar_prompts.md")
    november = next(
        i for i in sheet.items
        if i.drop_path
        == "assets/calendars/almanac/primary/colored/November.png"
    )
    assert november.title == (
        "November (crimson-magenta `#FF0080`) — bare branches, "
        "the last harvest"
    )
    assert [i.drop_path for i in sheet.items] == [
        f"assets/calendars/almanac/primary/colored/{m}.png"
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
    assert "assets/archetypes/life/tree/colored/Unborn.png" in paths
    assert "assets/archetypes/life/animals/colored/Unborn.png" in paths
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
        # the bare bold picks up the section's FULL declared dir
        ("Aries", "assets/zodiac/astrology/sign/Aries.png"),
    ]
    assert sheet.items[0].prompt == "heading-form prompt"
    assert sheet.items[1].prompt == "bold-token prompt"
    assert sheet.items[2].prompt == "bare-bold prompt"


# --- input-image reference (← `...`), owner 2026-07-23 ---------------

def _parse_text(tmp_path, text: str):
    p = tmp_path / "sheet.md"
    p.write_text(text, encoding="utf-8")
    return parse_sheet(p)


def test_input_image_reference_parsed(tmp_path):
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**Hero** → `assets/x/Hero.png`\n"
        "← `refs/hero.png`\n\n"
        "```\nA hero prompt. ASPECT RATIO 1:1. Rondel.\n```\n",
    )
    assert [p.message for p in sheet.problems] == []
    assert len(sheet.items) == 1
    item = sheet.items[0]
    assert item.drop_path == "assets/x/Hero.png"
    assert item.input_images == ("refs/hero.png",)


def test_entry_without_input_image_is_none(tmp_path):
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n**Hero** → `assets/x/Hero.png`\n\n```\nprompt\n```\n",
    )
    assert sheet.items[0].input_images == ()


def test_input_image_may_be_a_jpg_reference(tmp_path):
    """A reference PHOTO may be a jpg/webp (TOOL_IMAGE_EXTENSIONS), even
    though the OUTPUT path is always .png."""
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**Hero** → `assets/x/Hero.png`\n"
        "← `refs/hero.jpg`\n\n"
        "```\nprompt\n```\n",
    )
    assert [p.message for p in sheet.problems] == []
    assert sheet.items[0].input_images == ("refs/hero.jpg",)


def test_input_image_accepts_a_relative_parent_path(tmp_path):
    """The ref is READ-ONLY, so a '../' sibling location is allowed (it
    never escapes an OUTPUT folder — the runner only reads it)."""
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**Hero** → `assets/x/Hero.png`\n"
        "← `../shared/hero.png`\n\n"
        "```\nprompt\n```\n",
    )
    assert [p.message for p in sheet.problems] == []
    assert sheet.items[0].input_images == ("../shared/hero.png",)


def test_inline_input_arrow_on_the_same_line(tmp_path):
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**Hero** → `assets/x/Hero.png` ← `refs/hero.png`\n\n"
        "```\nprompt\n```\n",
    )
    assert [p.message for p in sheet.problems] == []
    assert sheet.items[0].drop_path == "assets/x/Hero.png"
    assert sheet.items[0].input_images == ("refs/hero.png",)


def test_multiple_input_images_kept_in_line_order(tmp_path):
    """Faza 2 (owner 2026-08-03): a dual plate attaches TWO references
    — one ← line per attachment, line order = attach order (the prompt
    says "the FIRST/SECOND attached image")."""
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**The Father** → `assets/x/Vader.png`\n"
        "← `sw_reference/Vader.png`\n"
        "← `sw_reference/Luke.png`\n\n"
        "```\nTWO ATTACHED IMAGES: the FIRST ... the SECOND ...\n```\n",
    )
    assert [p.message for p in sheet.problems] == []
    assert sheet.items[0].input_images == (
        "sw_reference/Vader.png", "sw_reference/Luke.png",
    )


def test_one_bad_ref_among_good_ones_reports_and_keeps_the_good(tmp_path):
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**Hero** → `assets/x/Hero.png`\n"
        "← `refs/hero.png`\n"
        "← `notes.txt`\n\n"
        "```\nprompt\n```\n",
    )
    assert any("input image" in p.message for p in sheet.problems)
    assert sheet.items[0].input_images == ("refs/hero.png",)


def test_non_image_input_reference_reported(tmp_path):
    """A malformed '← `...`' on a real entry is a loud author error; the
    entry still loads (its output is valid), just with no input."""
    sheet = _parse_text(
        tmp_path,
        "# Theme\n\n"
        "**Hero** → `assets/x/Hero.png`\n"
        "← `notes.txt`\n\n"
        "```\nprompt\n```\n",
    )
    assert any("input image" in p.message for p in sheet.problems)
    assert sheet.items[0].input_images == ()
