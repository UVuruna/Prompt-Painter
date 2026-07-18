"""Settings persistence — the GUI's remembered choices (owner's #9).

A flat JSON file at the project root (``settings.json``, gitignored
— it is the owner's local state, never shared). WHAT goes into the
dict is the GUI's business; this module is only the loading and
saving. A missing file is a normal first start (empty dict); a
corrupt file is reported LOUDLY but never crashes the app — the
owner loses remembered choices, not work.
"""

from __future__ import annotations

import json
import sys

from painter.config import SETTINGS_PATH


def load_settings() -> dict:
    """The saved settings dict; {} on a missing or corrupt file."""
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"SETTINGS: cannot read {SETTINGS_PATH.name} ({exc}) —"
            " starting with defaults; saving will overwrite it",
            file=sys.stderr,
        )
        return {}
    if not isinstance(data, dict):
        print(
            f"SETTINGS: {SETTINGS_PATH.name} does not hold a JSON"
            f" object (got {type(data).__name__}) — starting with"
            " defaults; saving will overwrite it",
            file=sys.stderr,
        )
        return {}
    return data


def save_settings(d: dict) -> None:
    """Write the settings dict atomically (tmp file + replace)."""
    tmp = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".tmp")
    tmp.write_text(
        json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(SETTINGS_PATH)
