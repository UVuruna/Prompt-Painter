# Settings

**Script:** [Settings (script)](settings.py)

## Purpose
Owner's #9: the GUI remembers the owner's choices between starts.
A flat JSON file at the project root (`settings.json`, gitignored —
local state, never shared). WHAT goes into the dict is the GUI's
business; this module is only the persistence.

A missing file is a normal first start (empty dict). A corrupt or
non-object file is reported LOUDLY on stderr but never crashes the
app — the owner loses remembered choices, not work — and the next
save overwrites it. Saves are atomic (temp file + replace).

## Connections

### Uses
- [Config](config.md) — `SETTINGS_PATH`

### Used by
- [GUI](../gui.md) — load on start, save on change/exit

## Functions

- `load_settings() -> dict` — the saved dict; `{}` on missing or
  corrupt file (corrupt = loud stderr line, never an exception).
- `save_settings(d: dict) -> None` — atomic JSON write.
