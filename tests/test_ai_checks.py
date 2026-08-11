"""Offline tests for the AI image checker — NO live API.

Split from the former ``test_ai.py`` god-file (root Rule #20, second
round — the source split into ``painter/ai/`` 2026-07-30, this test
module follows it 1:1: everything ``painter/ai/checks.py`` exports —
the owner's #3: the checker's response format, the Fixer AI's fix
prompt, the per-image checker orchestrator and the re-send reverse
mapping.
"""

from pathlib import Path

import pytest

from painter import ai

# a real 1x1 PNG (same fixture bytes as test_ai_client/test_runner)
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f030005fe02fea72d994800000000"
    "49454e44ae426082"
)


def _make_image(out: Path, rel: str) -> Path:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_1PX)
    return path


# --- the checker's response format -------------------------------------


def test_parse_check_response_ok_variants():
    assert ai.parse_check_response("OK") == []
    assert ai.parse_check_response("ok.") == []
    assert ai.parse_check_response("  OK\n") == []


def test_parse_check_response_defect_lines():
    text = (
        "DEFECTS:\n"
        "- subject slightly cut at the left edge\n"
        "- leftover white patch near the top\n"
    )
    assert ai.parse_check_response(text) == [
        "subject slightly cut at the left edge",
        "leftover white patch near the top",
    ]
    # a single defect on the header line is tolerated
    assert ai.parse_check_response("DEFECTS: watermark bottom-right") == [
        "watermark bottom-right"
    ]


def test_parse_check_response_garbage_is_loud():
    with pytest.raises(ai.AiError, match="unexpected check response"):
        ai.parse_check_response("The image looks quite nice overall.")
    with pytest.raises(ai.AiError):
        ai.parse_check_response("")


def test_fix_note_joins_the_defects():
    note = ai.fix_note(["cut at edge", "stray line"])
    assert "cut at edge; stray line" in note
    assert "Regenerate" in note


# --- build_fix_prompt (GUI rework Phase 20 — the Fixer AI) --------------


def test_build_fix_prompt_with_defects_lists_each_as_a_bullet():
    prompt = ai.build_fix_prompt(
        ["subject cropped at the shoulder", "stray line near the halo"],
    )
    assert "- subject cropped at the shoulder" in prompt
    assert "- stray line near the halo" in prompt


def test_build_fix_prompt_empty_defects_is_never_blank():
    """A caller that (against the gate) calls this with no defects still
    gets a SENSIBLE, non-empty instruction — edit_image/submit_with_image
    always need SOME text; this function stays honest about ANY input
    regardless of whether an upstream gate held (root Rule #1)."""
    prompt = ai.build_fix_prompt([])
    assert prompt.strip()
    assert "no specific defect" in prompt.lower()


def test_build_fix_prompt_appends_raw_verbatim_when_given():
    raw = "DEFECTS:\n- the halo is off-centre to the left"
    prompt = ai.build_fix_prompt(["halo off-centre"], raw)
    assert "halo off-centre" in prompt          # the parsed bullet
    assert "off-centre to the left" in prompt   # the verbatim raw, too
    assert prompt.index("halo off-centre") < prompt.index("off-centre to the left")


def test_build_fix_prompt_omits_raw_section_when_raw_is_none_or_blank():
    base = ai.build_fix_prompt(["x"])
    assert base == ai.build_fix_prompt(["x"], None)
    assert base == ai.build_fix_prompt(["x"], "   ")  # whitespace-only


def test_build_fix_prompt_is_pure_and_deterministic():
    a = ai.build_fix_prompt(["x", "y"], "raw text")
    b = ai.build_fix_prompt(["x", "y"], "raw text")
    assert a == b


# --- the per-image checker orchestrator (owner 2026-07-21) -------------


def test_check_one_image_flags_records_raw_and_times(tmp_path, monkeypatch):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Glory.png")
    clock = [100.0]
    monkeypatch.setattr(ai.client.time, "monotonic", lambda: clock[0])
    raw = "DEFECTS:\n- subject cut at the left edge"

    def fake_check(src, instructions, *, model=None, log=None):
        clock[0] += 0.5           # the "call" takes half a second
        return raw

    result = ai.check_one_image(
        img, out, "instr", check=fake_check, log=lambda _l: None
    )
    assert result["kind"] == "flagged"
    assert result["rel"] == "emblem/gemini/mood/Glory.png"
    assert result["defects"] == ["subject cut at the left edge"]
    assert result["raw"] == raw
    assert result["time"] == 0.5  # timing is plumbed, not a hardcoded 0
    # the raw is PERSISTED alongside the defects for later inspection
    assert ai.load_flags(out)["emblem/gemini/mood/Glory.png"]["raw"] == raw


def test_check_one_image_passes_prompt_through_to_check(tmp_path):
    """F6 (REWORK.md): a supplied ``prompt`` reaches ``check`` as a
    keyword arg, exactly as given."""
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Glory.png")
    seen: dict = {}

    def fake_check(src, instructions, *, prompt=None, model=None, log=None):
        seen["prompt"] = prompt
        return "OK"

    ai.check_one_image(
        img, out, "instr", prompt="a golden sun disc",
        check=fake_check, log=lambda _l: None,
    )
    assert seen["prompt"] == "a golden sun disc"


def test_check_one_image_without_prompt_never_forwards_the_kwarg(tmp_path):
    """The default (``prompt=None``) path never even SENDS the kwarg —
    a ``check`` double with no ``prompt`` parameter of its own (an
    older test, or a caller that never opts in) keeps working
    unchanged; this is the backward-compatibility guarantee F6 relies
    on for every EXISTING ``check=`` caller in this file."""
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Glory.png")

    def fake_check(src, instructions, *, model=None, log=None):
        return "OK"  # no **kwargs, no prompt param — must not blow up

    result = ai.check_one_image(
        img, out, "instr", check=fake_check, log=lambda _l: None,
    )
    assert result["kind"] == "ok"


def test_check_one_image_ok_clears_stale_flag_and_carries_raw(tmp_path):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Clean.png")
    # a pre-existing flag a now-clean re-check must drop
    ai.record_flag(out, img, ["old"], "m", "DEFECTS:\n- old", log=lambda _l: None)
    result = ai.check_one_image(
        img, out, "instr", check=lambda *a, **k: "OK", log=lambda _l: None
    )
    assert result["kind"] == "ok"
    assert result["defects"] == []
    assert result["raw"] == "OK"
    assert ai.load_flags(out) == {}   # the stale flag was cleared


def test_check_one_image_error_is_caught_never_fatal(tmp_path):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/x.png")

    def boom(*a, **k):
        raise ai.AiError("Gemini API HTTP 503 on gemini: high demand")

    result = ai.check_one_image(
        img, out, "instr", check=boom, log=lambda _l: None
    )
    assert result["kind"] == "error"  # returned, never raised (tool-job rule)
    assert "503" in result["raw"]     # the error text, shown in the viewer
    assert ai.load_flags(out) == {}   # nothing recorded on an error


def test_check_pairing_maps_each_response_to_the_right_image(tmp_path):
    """FIX 5: over a batch, each image's flag / raw / viewer-file maps to
    THAT exact image — no off-by-one — including an image OUTSIDE the out
    base (an absolute key that ``flag_file`` still round-trips, the run
    that checked Watch Academy while the out base was Downloads)."""
    out = tmp_path / "out"
    serpent = _make_image(out, "emblem/gemini/mood/Serpent.png")
    glory = _make_image(out, "emblem/gemini/mood/Glory.png")
    herod = tmp_path / "DOMY" / "assets" / "Herod.png"
    herod.parent.mkdir(parents=True)
    herod.write_bytes(PNG_1PX)
    images = [serpent, glory, herod]

    # a DISTINCT response per image, keyed by the file stem
    responses = {
        "Serpent": "DEFECTS:\n- frame cut on the left",
        "Glory": "OK",
        "Herod": "DEFECTS:\n- watermark bottom-right",
    }

    def fake_check(src, instructions, *, model=None, log=None):
        return responses[Path(src).stem]

    results = {
        src: ai.check_one_image(
            src, out, "instr", check=fake_check, log=lambda _l: None
        )
        for src in images
    }
    for src, result in results.items():
        # the raw is THIS image's response, not a neighbour's
        assert result["raw"] == responses[src.stem]
        # the flag key round-trips (flag_file — the SAME function the
        # panel's viewer uses) back to THIS exact file
        assert ai.flag_file(result["rel"], out).resolve() == src.resolve()

    # the persisted flags carry each image's OWN defects; the OK image none
    flags = ai.load_flags(out)
    assert flags[results[serpent]["rel"]]["defects"] == ["frame cut on the left"]
    assert flags[results[herod]["rel"]]["defects"] == ["watermark bottom-right"]
    assert results[glory]["rel"] not in flags
    # the outside image keyed by an ABSOLUTE path (never matches a queue)
    assert Path(results[herod]["rel"]).is_absolute()


def test_ai_check_doc_md_shows_defects_and_verbatim_raw():
    """FIX 3: the viewer markdown carries the name + path, the parsed
    defects AND the verbatim raw response — and an OK row is viewable
    too (its raw shows, no defect section)."""
    import gui

    md = gui.ai_check_doc_md(
        "emblem/gemini/mood/Glory.png",
        ["subject cut left"],
        "DEFECTS:\n- subject cut left",
    )
    assert "Glory.png" in md                        # the image name heading
    assert "`emblem/gemini/mood/Glory.png`" in md   # the full path
    assert "- subject cut left" in md               # the parsed defect bullet
    assert "**Full AI response:**" in md            # the raw section
    assert "DEFECTS:\n- subject cut left" in md      # the verbatim response

    ok = gui.ai_check_doc_md("emblem/gemini/mood/Clean.png", None, "OK")
    assert "AI-flagged defects" not in ok           # nothing parsed
    assert "**Full AI response:**" in ok and "OK" in ok


# --- the re-send reverse mapping ----------------------------------------


def test_drop_and_site_for_reverses_dest_for():
    from painter.config import dest_for

    # the assets mirror: out rel -> the original site-agnostic drop
    rel = dest_for("assets/emblem/mood/Glory.png", "gemini")
    assert ai.drop_and_site_for(rel) == (
        "assets/emblem/mood/Glory.png", "gemini",
    )
    # the API generator reverses through its _api suffix the same way
    rel = dest_for("assets/emblem/mood/Glory.png", "api_image")
    assert ai.drop_and_site_for(rel) == (
        "assets/emblem/mood/Glory.png", "api_image",
    )
    # the legacy layout: <site>/<drop>
    rel = dest_for("fake/img_0.png", "chatgpt")
    assert ai.drop_and_site_for(rel) == ("fake/img_0.png", "chatgpt")


def test_drop_and_site_for_strips_the_version_sibling():
    """A ``_vN`` version file (the ticked-redo output, owner
    2026-07-27) reverses to the SAME canonical drop as its master, so
    a flagged version still matches its sheet entry for a re-send —
    the owner's irregular bare ``_v`` form included."""
    assert ai.drop_and_site_for("emblem/mood/Glory_v3_gem.png") == (
        "assets/emblem/mood/Glory.png", "gemini",
    )
    assert ai.drop_and_site_for("emblem/mood/Glory_v_gpt.png") == (
        "assets/emblem/mood/Glory.png", "chatgpt",
    )
    # a name whose stem legitimately ends in letters+digits without
    # the _v marker is untouched
    assert ai.drop_and_site_for("emblem/mood/Glory2_gem.png") == (
        "assets/emblem/mood/Glory2.png", "gemini",
    )


def test_drop_and_site_for_none_when_no_site_segment():
    assert ai.drop_and_site_for("random/folder/pic.png") is None
    assert ai.drop_and_site_for("pic.png") is None
    # an ABSOLUTE flag key (image outside the out base) never matches
    assert ai.drop_and_site_for("C:/somewhere/else/pic.png") is None


def test_plan_resend_groups_by_site_and_sheet():
    flagged = {
        "emblem/gemini/mood/Glory.png": ["subject cut"],
        "emblem/gemini/mood/Anger.png": ["stray line", "halo"],
        "chatgpt/fake/img_0.png": ["watermark"],  # the legacy layout
    }
    drop_to_source = {
        "assets/emblem/mood/Glory.png": "C:/sheets/mood.md",
        "assets/emblem/mood/Anger.png": "C:/sheets/mood.md",
        "fake/img_0.png": "C:/sheets/fake.md",
    }
    plans, notes, unmatched = ai.plan_resend(flagged, drop_to_source)
    assert unmatched == []
    assert plans["gemini"] == {
        "C:/sheets/mood.md": {
            "assets/emblem/mood/Glory.png",
            "assets/emblem/mood/Anger.png",
        }
    }
    assert plans["chatgpt"] == {"C:/sheets/fake.md": {"fake/img_0.png"}}
    # each item carries ITS OWN fix note with its ';'-joined defects
    assert "subject cut" in notes["gemini"]["assets/emblem/mood/Glory.png"]
    assert "stray line; halo" in notes["gemini"]["assets/emblem/mood/Anger.png"]
    assert "watermark" in notes["chatgpt"]["fake/img_0.png"]


def test_plan_resend_reports_unmatched_loudly():
    flagged = {
        "nosite/pic.png": ["x"],                 # no site segment
        "emblem/gemini/mood/Ghost.png": ["y"],   # site, but not queued
    }
    plans, notes, unmatched = ai.plan_resend(flagged, {})
    assert plans == {} and notes == {}
    reasons = dict(unmatched)
    assert reasons["nosite/pic.png"] == "no site in the path"
    assert (
        reasons["emblem/gemini/mood/Ghost.png"]
        == "not in any queued collection"
    )
