"""JobTemp + measure — the four tools' backup/restore + before→after math.

Backups round-trip byte-identical, a no-op backup can be dropped,
restore_all reverts the whole job, clear() wipes the slot, and measure()
reports the right % for all four kinds — including the larger-axis
aspect stretch where a naive "smaller side only" reading would report 0.
Everything runs on synthetic PNGs; the temp root is swept after each
test.
"""

import numpy as np
import pytest
from PIL import Image

import painter.jobtemp as jobtemp_module
from painter.config import JOBTEMP_STEPS_SUBDIR
from painter.jobtemp import JobTemp, TEMP_ROOT, clear_all, measure


@pytest.fixture(autouse=True)
def _sweep_temp():
    yield
    clear_all()


def _make_png(path, w, h, mode="RGBA", fill=(180, 60, 60, 255)):
    if mode == "RGBA":
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[h // 4:3 * h // 4, w // 4:3 * w // 4] = fill
        Image.fromarray(arr, "RGBA").save(path, "PNG")
    else:
        arr = np.full((h, w, 3), 255, dtype=np.uint8)
        arr[h // 4:3 * h // 4, w // 4:3 * w // 4] = fill[:3]
        Image.fromarray(arr, "RGB").save(path, "PNG")


# --- JobTemp ----------------------------------------------------------


def test_backup_restore_one_round_trips_bytes(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "a.png"
    _make_png(img, 40, 40)
    original = img.read_bytes()

    jt = JobTemp("bg", folder)
    jt.backup(img, "a.png")
    assert jt.has_backup("a.png")
    # the tool "changes" the file in place
    img.write_bytes(b"totally different bytes")
    assert img.read_bytes() != original

    assert jt.restore_one("a.png") is True
    assert img.read_bytes() == original  # byte-identical restore


def test_before_path_points_at_the_backup(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "b.png"
    _make_png(img, 20, 20)
    jt = JobTemp("crop", folder)
    bak = jt.backup(img, "b.png")
    assert jt.before_path("b.png") == bak
    assert jt.before_path("missing.png") is None


def test_drop_removes_a_no_op_backup(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "c.png"
    _make_png(img, 20, 20)
    jt = JobTemp("crop", folder)
    jt.backup(img, "c.png")
    jt.drop("c.png")
    assert not jt.has_backup("c.png")
    assert jt.restore_one("c.png") is False  # nothing to restore


def test_restore_all_reverts_every_backed_up_file(tmp_path):
    folder = tmp_path / "imgs"
    (folder / "sub").mkdir(parents=True)
    files = {
        "one.png": folder / "one.png",
        "sub/two.png": folder / "sub" / "two.png",
        "three.png": folder / "three.png",
    }
    originals = {}
    jt = JobTemp("upscale", folder)
    for rel, path in files.items():
        _make_png(path, 30, 30)
        originals[rel] = path.read_bytes()
        jt.backup(path, rel)
        path.write_bytes(b"stomped " + rel.encode())

    assert jt.restore_all() == 3
    for rel, path in files.items():
        assert path.read_bytes() == originals[rel]


def test_clear_removes_the_slot_dir(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "d.png"
    _make_png(img, 20, 20)
    jt = JobTemp("aspect", folder)
    jt.backup(img, "d.png")
    assert jt.root.exists()
    jt.clear()
    assert not jt.root.exists()


def test_clear_all_wipes_the_whole_root(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "e.png"
    _make_png(img, 20, 20)
    JobTemp("bg", folder).backup(img, "e.png")
    JobTemp("crop", folder).backup(img, "e.png")
    assert TEMP_ROOT.exists()
    clear_all()
    assert not TEMP_ROOT.exists()


def test_new_jobtemp_wipes_a_stale_slot(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "f.png"
    _make_png(img, 20, 20)
    JobTemp("bg", folder).backup(img, "f.png")
    # a fresh JobTemp for the SAME slot must start empty
    jt2 = JobTemp("bg", folder)
    assert not jt2.has_backup("f.png")


# --- Phase 7: per-step backups ----------------------------------------


def test_step_backup_is_namespaced_and_original_path_unchanged(tmp_path):
    """THE critical regression guard (Phase 7): a step=None backup must
    land at the EXACT byte-for-byte path the pre-Phase-7 store always
    used (root/rel) — the four standalone tools' on-disk layout is
    untouched. A named step lands somewhere else entirely, namespaced so
    it can never collide with the unnamed backup or with another step."""
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "a.png"
    _make_png(img, 40, 40)

    jt = JobTemp("bg", folder)
    unnamed = jt.backup(img, "a.png")
    assert unnamed == jt.root / "a.png"  # identical to the old layout
    assert unnamed.exists()

    named = jt.backup(img, "a.png", step="crop")
    assert named != unnamed
    assert named.exists()
    assert JOBTEMP_STEPS_SUBDIR in named.parts

    # the no-step lookups still resolve to the unnamed backup only
    assert jt.before_path("a.png") == unnamed
    assert jt.has_backup("a.png") is True
    # the named lookup resolves to the OTHER path
    assert jt.before_path("a.png", step="crop") == named
    assert jt.has_backup("a.png", step="crop") is True
    # a step that was never backed up is absent, independently
    assert jt.has_backup("a.png", step="upscale") is False
    assert jt.before_path("a.png", step="upscale") is None


def test_restore_to_named_step_reverts_only_that_stage(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "a.png"
    _make_png(img, 40, 40)

    jt = JobTemp("chatgpt", folder)
    # "original" — the pristine baseline, before the pipeline starts
    jt.backup(img, "a.png", step="original")
    pristine = img.read_bytes()

    # BG step runs: back up the pre-bg state (== pristine), then mutate
    jt.backup(img, "a.png", step="bg")
    img.write_bytes(b"after-bg")
    after_bg = img.read_bytes()

    # CROP step runs: back up the pre-crop state (== after_bg), mutate
    jt.backup(img, "a.png", step="crop")
    img.write_bytes(b"after-crop")

    # restore_to("crop") reverts to right BEFORE crop ran == after_bg,
    # NOT all the way back to pristine
    assert jt.restore_to("a.png", step="crop") is True
    assert img.read_bytes() == after_bg

    # the earlier stages' own backups are untouched by that restore
    assert jt.before_path("a.png", step="bg").read_bytes() == pristine
    assert jt.before_path("a.png", step="original").read_bytes() == pristine

    # a step that never backed this rel up has nothing to restore
    assert jt.restore_to("a.png", step="upscale") is False


def test_steps_for_lists_available_stages_in_order(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    img = folder / "a.png"
    _make_png(img, 40, 40)

    jt = JobTemp("chatgpt", folder)
    # back them up OUT of pipeline order, to prove steps_for orders by
    # JOBTEMP_STEP_NAMES, never by call/insertion order
    jt.backup(img, "a.png", step="upscale")
    jt.backup(img, "a.png", step="original")
    jt.backup(img, "a.png", step="bg")

    assert jt.steps_for("a.png") == ["original", "bg", "upscale"]
    # a rel with no step backups at all
    assert jt.steps_for("missing.png") == []
    # the unnamed (step=None) backup is not itself a "step"
    jt.backup(img, "a.png")
    assert jt.steps_for("a.png") == ["original", "bg", "upscale"]


def test_restore_all_only_touches_the_original_step_never_named_steps(tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    a = folder / "a.png"
    b = folder / "b.png"
    _make_png(a, 30, 30)
    _make_png(b, 30, 30)
    a_original = a.read_bytes()

    jt = JobTemp("bg", folder)
    # "a" has BOTH an unnamed backup and a named-step backup
    jt.backup(a, "a.png")                  # unnamed
    jt.backup(a, "a.png", step="crop")     # named
    a.write_bytes(b"stomped-a")

    # "b" has ONLY a named-step backup, no unnamed one
    jt.backup(b, "b.png", step="crop")
    b.write_bytes(b"stomped-b")

    count = jt.restore_all()

    # only the ONE unnamed backup (a.png) was restored
    assert count == 1
    assert a.read_bytes() == a_original
    # "b" was never touched — it had no unnamed backup to restore from
    assert b.read_bytes() == b"stomped-b"
    # restore_all must never manufacture a bogus steps folder inside the
    # LIVE output tree (the bug a naive rglob-everything walk would hit)
    assert not (folder / JOBTEMP_STEPS_SUBDIR).exists()


def test_backup_tracks_cumulative_bytes_and_over_cap_flags(tmp_path, monkeypatch):
    folder = tmp_path / "imgs"
    folder.mkdir()
    a = folder / "a.png"
    _make_png(a, 50, 50)
    size = a.stat().st_size

    jt = JobTemp("bg", folder)
    assert jt.bytes_used == 0
    assert jt.over_cap() is False

    jt.backup(a, "a.png")
    assert jt.bytes_used == size

    jt.backup(a, "a.png", step="crop")
    assert jt.bytes_used == size * 2

    # lower the cap under monkeypatch so the flag flips without writing
    # gigabytes of real test data
    monkeypatch.setattr(jobtemp_module, "JOBTEMP_MAX_BYTES", size * 2)
    assert jt.over_cap() is True  # AT the cap counts as over

    monkeypatch.setattr(jobtemp_module, "JOBTEMP_MAX_BYTES", size * 2 + 1)
    assert jt.over_cap() is False

    # dropping a backup reduces the running total again (no drift)
    jt.drop("a.png", step="crop")
    assert jt.bytes_used == size
    assert jt.over_cap() is False


# --- measure ----------------------------------------------------------


def test_measure_bg_counts_removed_pixels(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    # before: fully opaque white plate (RGB)
    _make_png(before, 100, 100, mode="RGB")
    # after: same size, a 20x20 corner cleared to transparent
    arr = np.full((100, 100, 4), 255, dtype=np.uint8)
    arr[:20, :20, 3] = 0
    Image.fromarray(arr, "RGBA").save(after, "PNG")

    m = measure("bg", before, after)
    assert m["before"] == "100x100"
    assert m["after"] == "100x100"
    assert m["label"] == "removed"
    assert abs(m["pct"] - 4.0) < 0.01  # 400 / 10000 = 4%


def test_measure_crop_reports_area_reduction(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 100, 100)
    _make_png(after, 60, 60)
    m = measure("crop", before, after)
    assert m["label"] == "reduction"
    # (100^2 - 60^2) / 100^2 = 0.64
    assert abs(m["pct"] - 64.0) < 0.01


def test_measure_upscale_reports_area_increase(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 100, 100)
    _make_png(after, 200, 200)
    m = measure("upscale", before, after)
    assert m["label"] == "increase"
    # (200^2 - 100^2) / 100^2 = 3.0 -> 300%
    assert abs(m["pct"] - 300.0) < 0.01


def test_measure_aspect_reports_changed_axis_growth(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 1024, 1024)
    _make_png(after, 1820, 1024)  # width stretched, height kept
    m = measure("aspect", before, after)
    assert m["label"] == "deformation"
    assert abs(m["pct"] - 77.73) < 0.1  # (1820-1024)/1024


def test_measure_aspect_larger_axis_stretch_is_not_zero(tmp_path):
    """The case a literal 'smaller side only' reading gets wrong: the
    LARGER axis is stretched, the smaller is untouched — deformation is
    the larger axis's growth, never 0."""
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _make_png(before, 1000, 900)
    _make_png(after, 1600, 900)  # width (larger axis) stretched
    m = measure("aspect", before, after)
    assert abs(m["pct"] - 60.0) < 0.01  # (1600-1000)/1000, NOT 0
