"""The FLAG MEMORY (owner's #3) — ``<out>/_state/ai_flags.json``,
split out of the single-file ``painter/ai.py`` (root Rule #20,
2026-07-30).

Keyed by the image's path RELATIVE to the out base; each entry carries
the defects, the check time, the model and the file's mtime — a
changed mtime (the image was REGENERATED) invalidates the flag on the
next prune. Pure disk state: no HTTP, no model, so the checker and the
GUI can read it without touching the API at all.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from painter.config import AI_FLAGS_FILENAME, STATE_DIRNAME


def flags_path(out_base: Path) -> Path:
    return Path(out_base) / STATE_DIRNAME / AI_FLAGS_FILENAME


def flag_key(image_path: Path, out_base: Path) -> str:
    """The flag dict's key for one image: its POSIX path RELATIVE to
    the out base. An image OUTSIDE the base keys by its absolute POSIX
    path — the flag still persists, but ``drop_and_site_for`` cannot
    match it to a queued collection (the re-send logs and skips it)."""
    resolved = Path(image_path).resolve()
    try:
        return resolved.relative_to(Path(out_base).resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def flag_file(key: str, out_base: Path) -> Path:
    """The image file a flag key points at — the EXACT reverse of
    ``flag_key`` (relative to the out base, or absolute when the image
    lived outside it). One home for the round-trip so the checker's
    flag key and the panel's viewer file can never drift apart."""
    path = Path(key)
    return path if path.is_absolute() else Path(out_base) / path


def load_flags(out_base: Path, log=print) -> dict:
    """The saved flags dict; {} on a missing file. A corrupt file is
    reported LOUDLY and treated as empty — flags are derived data (a
    re-check rebuilds them), so losing them never loses work."""
    path = flags_path(out_base)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log(f"AI FLAGS: cannot read {path} ({exc}) — starting empty")
        return {}
    if not isinstance(data, dict):
        log(
            f"AI FLAGS: {path} does not hold a JSON object — starting"
            " empty"
        )
        return {}
    return data


def save_flags(out_base: Path, flags: dict) -> Path:
    """Atomic write (tmp + replace), mirroring settings.py."""
    path = flags_path(out_base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)
    return path


def record_flag(
    out_base: Path,
    image_path: Path,
    defects: list[str],
    model: str,
    raw: str,
    log=print,
) -> str:
    """Load-merge-save one image's flag entry; returns its key. The
    stored mtime is the file's AT CHECK TIME — a later regeneration
    changes it and ``prune_stale_flags`` drops the entry. ``raw`` is the
    VERBATIM model response, persisted alongside the parsed defects so
    the owner can inspect exactly what the vision model said."""
    flags = load_flags(out_base, log)
    key = flag_key(image_path, out_base)
    flags[key] = {
        "defects": list(defects),
        "raw": raw,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "mtime": Path(image_path).stat().st_mtime,
    }
    save_flags(out_base, flags)
    return key


def clear_flag_keys(out_base: Path, keys: list[str], log=print) -> int:
    """Drop the given flag ENTRIES by key (the panel's Clear-flags
    action); returns the number actually removed."""
    flags = load_flags(out_base, log)
    removed = sum(1 for key in keys if flags.pop(key, None) is not None)
    if removed:
        save_flags(out_base, flags)
    return removed


def clear_flag(out_base: Path, image_path: Path, log=print) -> bool:
    """Drop one image's entry (an OK re-check clears the old flag);
    True when an entry existed."""
    return clear_flag_keys(
        out_base, [flag_key(image_path, out_base)], log
    ) == 1


def prune_stale_flags(out_base: Path, log=print) -> int:
    """Drop every entry whose file is GONE or whose mtime CHANGED since
    the check (the image was regenerated / retouched) — run before a
    check batch so the memory never asserts stale defects. Returns the
    number dropped."""
    flags = load_flags(out_base, log)
    keep: dict = {}
    dropped = 0
    for key, entry in flags.items():
        file = flag_file(key, out_base)
        try:
            same = file.stat().st_mtime == float(entry.get("mtime", -1.0))
        except (OSError, TypeError, ValueError):
            same = False  # gone or malformed entry -> stale
        if same:
            keep[key] = entry
        else:
            dropped += 1
    if dropped:
        save_flags(out_base, keep)
        log(
            f"AI FLAGS: {dropped} stale flag(s) cleared (file changed"
            " or gone since the check)"
        )
    return dropped
