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

The dict SHAPE lives with the GUI (`_collect_settings` /
`_apply_settings`, documented in [GUI](../gui.md)); as of owner
2026-07-19 it also carries `settings_collapsed` (the per-agent
fine-tune collapse), `upscale_tool` (the standalone Upscale dialog's
last-used four gate params), `aspect_ratio` (the last W:H entered in
the Aspect dialog), `aspect_filter` (the Aspect dialog's last input
FILTER — `from`/`to`/`mode`), a per-agent `style` (the rendering-style
dropdown, under `agents.<site>`), and per-agent `up_minw`/`up_minh`/
`up_aspmin`/`up_aspmax` under `agents.<site>` — all plain JSON scalars
and small dicts, so this module round-trips them with zero special
handling. Since owner 2026-07-20 it also carries `gemini_api_key` —
the AI features' free AI Studio key, written by the GUI's guided
wizard and read back by [AI Client & Flows](ai.md) on every call;
it is a CREDENTIAL, one more reason this file stays gitignored.

## Connections

### Uses
- [Config](config.md) — `SETTINGS_PATH`

### Used by
- [GUI](../gui.md) — load on start, save on change/exit

## Functions

- `load_settings() -> dict` — the saved dict; `{}` on missing or
  corrupt file (corrupt = loud stderr line, never an exception).
- `save_settings(d: dict) -> None` — atomic JSON write.
