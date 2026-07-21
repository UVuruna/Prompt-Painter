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
last-used gate), `aspect_ratio` (the last W:H entered in
the Aspect dialog), and a per-agent `style` (the rendering-style
dropdown, under `agents.<site>`) — all plain JSON scalars
and small dicts, so this module round-trips them with zero special
handling. Since owner 2026-07-20 it also carries `gemini_api_key` —
the AI features' free AI Studio key, written by the GUI's guided
wizard and read back by [AI Client & Flows](ai.md) on every call;
it is a CREDENTIAL, one more reason this file stays gitignored. GUI
rework Phase 4 (2026-07-21) replaced the Aspect dialog's old scalar
`aspect_filter` (`from`/`to`/`mode`) with `aspect_filter_conditions` —
a list of [Shared Filter Framework](filters.md) condition dicts — and
added `filter_presets` (a `{name: [condition-dict, ...]}` library
shared by every `FilterEditor` instance, not just the Aspect tool).
The OLD `aspect_filter` key is read ONCE (a one-time migration in
`gui._migrate_legacy_aspect_filter`, only when the new key is absent)
and never written back — like any key the GUI stops emitting, it
simply drops off disk on the next save (this module always writes
the WHOLE dict it is given, never a merge — see `save_settings`
below).

GUI rework Phase 6 (2026-07-21) applied the SAME additive-migration
pattern to the upscale gate: the per-agent `up_minw`/`up_minh`/
`up_aspmin`/`up_aspmax` four scalars (under `agents.<site>`) became
ONE `up_minside` string plus `up_filter_conditions` (a [Shared Filter
Framework](filters.md) condition list, mirroring
`aspect_filter_conditions`'s own shape); `upscale_tool`'s old
`min_width`/`min_height`/`aspect_min`/`aspect_max` scalars became
`{"min_side": int, "conditions": [condition-dict, ...]}`. Both OLD
shapes are read ONCE each (`gui._migrate_legacy_upscale_gate`, only
when the corresponding NEW key is absent) and never written back —
same drop-off-disk-on-next-save behaviour as every other migrated key
here.

## Connections

### Uses
- [Config (subfolder)](config/___config.md) — `SETTINGS_PATH`

### Used by
- [GUI](../gui.md) — load on start, save on change/exit

## Functions

- `load_settings() -> dict` — the saved dict; `{}` on missing or
  corrupt file (corrupt = loud stderr line, never an exception).
- `save_settings(d: dict) -> None` — atomic JSON write.
