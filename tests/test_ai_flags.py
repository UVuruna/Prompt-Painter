"""Offline tests for the AI flag memory — NO live API.

Split from the former ``test_ai.py`` god-file (root Rule #20, second
round — the source split into ``painter/ai/`` 2026-07-30, this test
module follows it 1:1: everything ``painter/ai/flags.py`` exports —
``<out>/_state/ai_flags.json``, the mtime-invalidated record of what a
check found.
"""

from pathlib import Path

from painter import ai

# a real 1x1 PNG (same fixture bytes as test_ai_client/test_ai_checks)
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


def test_flags_round_trip(tmp_path):
    out = tmp_path / "out"
    img = _make_image(out, "emblem/gemini/mood/Glory.png")
    key = ai.record_flag(
        out, img, ["subject cut"], "gemini-test",
        "DEFECTS:\n- subject cut", log=lambda _l: None,
    )
    assert key == "emblem/gemini/mood/Glory.png"
    flags = ai.load_flags(out)
    entry = flags[key]
    assert entry["defects"] == ["subject cut"]
    assert entry["raw"] == "DEFECTS:\n- subject cut"  # verbatim, persisted
    assert entry["model"] == "gemini-test"
    assert entry["checked_at"]
    assert entry["mtime"] == img.stat().st_mtime
    # the file lives under <out>/_state/ai_flags.json
    assert ai.flags_path(out).is_file()
    # clear drops it; clearing again reports nothing to do
    assert ai.clear_flag(out, img) is True
    assert ai.clear_flag(out, img) is False
    assert ai.load_flags(out) == {}


def test_flags_merge_never_clobbers_other_entries(tmp_path):
    out = tmp_path / "out"
    a = _make_image(out, "badge/chatgpt/a.png")
    b = _make_image(out, "badge/chatgpt/b.png")
    ai.record_flag(out, a, ["x"], "m", "DEFECTS:\n- x", log=lambda _l: None)
    ai.record_flag(out, b, ["y"], "m", "DEFECTS:\n- y", log=lambda _l: None)
    assert set(ai.load_flags(out)) == {
        "badge/chatgpt/a.png", "badge/chatgpt/b.png",
    }


def test_prune_drops_regenerated_and_missing_files(tmp_path):
    import os

    out = tmp_path / "out"
    keep = _make_image(out, "badge/chatgpt/keep.png")
    regen = _make_image(out, "badge/chatgpt/regen.png")
    gone = _make_image(out, "badge/chatgpt/gone.png")
    for img in (keep, regen, gone):
        ai.record_flag(out, img, ["d"], "m", "DEFECTS:\n- d", log=lambda _l: None)
    # regenerate one (mtime changes), delete another
    os.utime(regen, (regen.stat().st_atime, regen.stat().st_mtime + 60))
    gone.unlink()
    dropped = ai.prune_stale_flags(out, log=lambda _l: None)
    assert dropped == 2
    assert set(ai.load_flags(out)) == {"badge/chatgpt/keep.png"}
    # a second prune finds nothing stale
    assert ai.prune_stale_flags(out, log=lambda _l: None) == 0


def test_corrupt_flags_file_is_loud_but_empty(tmp_path):
    out = tmp_path / "out"
    path = ai.flags_path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken json", encoding="utf-8")
    logs: list[str] = []
    assert ai.load_flags(out, log=logs.append) == {}
    assert any("cannot read" in line for line in logs)


def test_flag_key_relative_inside_absolute_outside(tmp_path):
    out = tmp_path / "out"
    inside = _make_image(out, "emblem/gemini/x.png")
    outside = tmp_path / "elsewhere" / "y.png"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(PNG_1PX)
    assert ai.flag_key(inside, out) == "emblem/gemini/x.png"
    key = ai.flag_key(outside, out)
    assert Path(key).is_absolute()
    assert key.endswith("elsewhere/y.png")
