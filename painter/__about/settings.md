# Settings

**Script:** [Settings (script)](../settings.py)

## Purpose

Owner's #9: the GUI remembers the owner's choices between starts. A
flat JSON file at the project root (`settings.json`, gitignored —
local state, never shared). WHAT goes into the dict is the GUI's
business; this module is only the persistence.

A missing file is a normal first start (empty dict). A corrupt or
non-object file is reported LOUDLY on stderr but never crashes the
app — the owner loses remembered choices, not work — and the next
save overwrites it. Saves are atomic (temp file + replace).

Since owner 2026-07-20 the dict also carries `gemini_api_key` — the
AI features' free AI Studio key, written by the GUI's guided wizard
and read back by [AI (subfolder)](../ai/___ai.md) on every call. It
is a CREDENTIAL, one more reason this file stays gitignored. The
dict's full SHAPE (per-tool filter conditions, per-agent style, the
`models` per-purpose override, migrations of old scalar keys) is the
GUI's own concern, documented in the GUI folder's docs — this module
never inspects or migrates the dict's contents, it only loads and
saves it whole.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — `SETTINGS_PATH`

### Used by
- [GUI (folder)](../../gui/___gui.md) — load on start, save on
  change/exit; owns the dict's shape and every key migration
- [Gemini REST Client](../ai/__about/client.md) — `load_settings` (the
  API key, the per-purpose `models` override)

## Functions

- `load_settings() -> dict` — the saved dict; `{}` on missing or
  corrupt file (corrupt = loud stderr line, never an exception).
- `save_settings(d: dict) -> None` — atomic JSON write (temp file +
  `replace`); always writes the WHOLE dict it is given, never a merge
  — a key the caller stops emitting simply drops off disk on the next
  save.
