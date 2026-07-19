# Job Temp / Restore

**Script:** [Job Temp (script)](jobtemp.py)

## Purpose
The four in-place tools (BG removal / Crop / Upscale / Aspect ratio)
overwrite files, so this module is their safety net (owner
2026-07-19): before each op the ORIGINAL is copied into a per-job temp
subdir, so the dashboard can show a BEFORE/AFTER viewer and RESTORE one
image or the whole job. The image-generation jobs make NEW files and
never need it.

Whether an image has a before/after keys ONLY on its BACKUP existing —
i.e. the engine actually rewrote the file (`done`) — never on a
resolution change. BG removal changes ALPHA, not dimensions (its
before/after share WxH), so a resolution-based "did anything change?"
test would wrongly report "nothing" for a cleared background; keying on
the backup keeps before/after + restore working for ALL four tools.

`measure` computes the before→after number each tool panel shows
(% removed / reduction / increase / deformation) from the temp backup
vs the in-place result — so the engine functions stay untouched and
every metric is derived OUTSIDE them. Only the stdlib loads at import;
PIL/numpy load lazily inside `measure`, so dry runs stay stdlib-only.

## Connections

### Uses
- [Config](config.md) — `PROJECT_ROOT`, `JOBTEMP_DIRNAME`,
  `JOBTEMP_REMOVED_ALPHA`, `JOB_METRIC`.

### Used by
- [GUI](../gui.md) — `_start_tool` creates one `JobTemp` per tool job,
  the worker `backup`s each original, TIMES the op, then on `done`
  `measure`s / keeps the backup (else `drop`s it), the tool panel shows
  the metric + per-image time and restores one/all, and the app clears
  temps on panel CLOSE, on exit and at startup.
- [Tests (folder)](../tests/___tests.md) — `test_jobtemp.py`.

## API

### `TEMP_ROOT`
`PROJECT_ROOT/.painter_tmp` — the gitignored root; every job slot gets
a subdir under it.

### class `JobTemp(slot, folder)`
One tool job's backup store. The slot's subdir is FRESH on
construction (a reused slot never inherits an old job's backups).

- `backup(src, rel) -> Path` — copy the ORIGINAL of `folder/rel` into
  the store BEFORE the op.
- `drop(rel)` — delete a backup (for a no-op, so an unchanged file
  holds no restore point).
- `before_path(rel) -> Path | None` — the backup path, or None.
- `has_backup(rel) -> bool`.
- `restore_one(rel) -> bool` — copy the backup back over `folder/rel`
  (False when there is none).
- `restore_all() -> int` — restore every backed-up file; returns the
  count.
- `clear()` — wipe this job's whole subdir (on panel CLOSE).

### `clear_all()`
Wipe the WHOLE temp root — app-exit cleanup and a startup orphan sweep.

### `measure(kind, before, after) -> dict`
Returns `{'before': 'WxH', 'after': 'WxH', 'pct': float, 'label': str}`:

- `bg` — % of pixels whose alpha fell below `JOBTEMP_REMOVED_ALPHA`
  (removal never resizes, so before/after share WxH).
- `crop` — % area REDUCTION.
- `upscale` — % area INCREASE.
- `aspect` — % growth of the CHANGED axis = the deformation (the
  stretch only ever grows one axis; the literal "smaller side only"
  reading gives 0% whenever the LARGER axis is stretched, so the
  changed axis is measured instead).
