"""Offline tests for phase two — staging, approval, rejection."""

import json

from painter.review import (
    StagedImage,
    approve,
    reject,
    staged_images,
    staging_root,
)


def stage_one(out_base, site="gemini", drop="trinity/Jesus_Advocate.png"):
    root = staging_root(out_base, site)
    img = root / drop
    img.parent.mkdir(parents=True)
    img.write_bytes(b"fake png bytes")
    progress = root / "trinity_prompts.progress.json"
    progress.write_text(
        json.dumps({"done": {drop: {"file": str(img), "at": "t"}}}),
        encoding="utf-8",
    )
    return img, progress


def test_staged_images_lists_per_site(tmp_path):
    stage_one(tmp_path, "gemini")
    stage_one(tmp_path, "chatgpt", drop="trinity/One_Judge.png")
    found = staged_images(tmp_path, ("gemini", "chatgpt"))
    assert [(s.site, s.drop_path) for s in found] == [
        ("gemini", "trinity/Jesus_Advocate.png"),
        ("chatgpt", "trinity/One_Judge.png"),
    ]
    # progress sidecars are never listed as images
    assert all(s.path.suffix == ".png" for s in found)


def test_approve_moves_to_final(tmp_path):
    img, progress = stage_one(tmp_path)
    item = staged_images(tmp_path, ("gemini",))[0]
    dest = approve(tmp_path, item)
    assert dest == tmp_path / "gemini" / "trinity" / "Jesus_Advocate.png"
    assert dest.read_bytes() == b"fake png bytes"
    assert not img.exists()
    # approval keeps the item marked done — no regeneration
    data = json.loads(progress.read_text(encoding="utf-8"))
    assert "trinity/Jesus_Advocate.png" in data["done"]


def test_reject_deletes_and_unmarks(tmp_path):
    img, progress = stage_one(tmp_path)
    item = staged_images(tmp_path, ("gemini",))[0]
    reject(tmp_path, item)
    assert not img.exists()
    data = json.loads(progress.read_text(encoding="utf-8"))
    assert data["done"] == {}  # a rerun will regenerate it
