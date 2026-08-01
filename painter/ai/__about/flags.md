# Flag Memory

**Script:** [Flag Memory (script)](../flags.py)

## Purpose

`<out>/_state/ai_flags.json` — the record of what a check found, so a
defect survives the app closing and a re-check knows what changed.
Pure disk state: no HTTP, no model, so the GUI can read it without
touching the API. Split out of the single-file `painter/ai.py` (root
Rule #20, 2026-07-30).

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) —
  `AI_FLAGS_FILENAME`, `STATE_DIRNAME`

### Used by
- [Image Checker](checks.md) — `flag_key`/`record_flag`/`clear_flag`
  around every checked image
- [AI (subfolder)](../___ai.md) — `__init__.py` re-exports it
- [GUI (folder)](../../../gui/___gui.md) — the checker report viewer
  and its Clear-flags action

## Functions

- Flags file `<out>/_state/ai_flags.json`, atomic writes, keyed by
  `flag_key(image, out_base)` — the image's POSIX path RELATIVE to
  the out base (absolute when the image lives outside it; such keys
  persist but can never match a queued collection):
  `load_flags` / `save_flags` / `record_flag` (defects, the VERBATIM
  raw response, checked_at, model, the file's mtime AT CHECK TIME) /
  `clear_flag` / `clear_flag_keys` / `prune_stale_flags` — the prune
  drops every entry whose file is gone or whose mtime changed (the
  image was REGENERATED), run before each check batch. A corrupt flags
  file is reported loudly and treated as empty (flags are derived
  data — a re-check rebuilds them).
- `flag_file(key, out_base) -> Path` — the EXACT reverse of
  `flag_key` (relative under the base, or absolute when the image was
  outside): the ONE home for the round-trip, used by
  `prune_stale_flags` AND the GUI viewer, so the flag key and the
  image it opens can never drift apart.

## Design Decisions
- **The flag mtime is the invalidation.** A regenerated image gets a
  new mtime, so its stale defects can never be asserted again — no
  separate bookkeeping when the re-send overwrites a file.
- **A corrupt flags file is empty, not fatal.** Flags are DERIVED
  data — a re-check rebuilds them — so a broken file is reported
  loudly and treated as empty rather than blocking a run.
