# Job Temp / Restore

**Script:** [Job Temp (script)](jobtemp.py)

## Purpose
The four in-place tools (BG removal / Crop / Upscale / Aspect ratio)
overwrite files, so this module is their safety net (owner
2026-07-19): before each op the ORIGINAL is copied into a per-job temp
subdir, so the dashboard can show a BEFORE/AFTER viewer and RESTORE one
image or the whole job. The image-generation jobs make NEW files and
never need it.

GUI rework Phase 7 (owner decision 2026-07-21) extends the same store
with an optional PIPELINE STEP name, for the site-generation pipeline's
own multi-stage backups (BG → Crop → Aspect(force) → Upscale, Phase 8,
plus the Fixer AI's pre-fix snapshot, Phase 20). Passing no step keeps
the EXACT byte-for-byte path/behavior the four standalone tools have
always used — this is the CRITICAL regression guard, see "On-disk
layout" below. A named step is namespaced under its own subdir so a
multi-step pipeline can back up, and later restore to, each stage
independently without the steps ever colliding with each other or with
the unnamed backup.

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
- [Config (subfolder)](config/___config.md) — `PROJECT_ROOT`, `JOBTEMP_DIRNAME`,
  `JOBTEMP_REMOVED_ALPHA`, `JOB_METRIC`, and (Phase 7)
  `JOBTEMP_STEPS_SUBDIR`, `JOBTEMP_STEP_NAMES`, `JOBTEMP_MAX_BYTES`.

### Used by
- [GUI](../gui.md) — `_start_tool` creates one `JobTemp` per tool job,
  the worker `backup`s each original, TIMES the op, then on `done`
  `measure`s / keeps the backup (else `drop`s it), the tool panel shows
  the metric + per-image time and restores one/all, and the app clears
  temps on panel CLOSE, on exit and at startup. All FOUR of today's
  call sites use the unnamed (step=None) form — unchanged by Phase 7.
  The site-generation pipeline's own per-step backups (Phase 8) and the
  Fixer AI's pre-fix snapshot (Phase 20) are the future callers of the
  `step=` form added this phase; wiring them in is out of this phase's
  scope (an ENGINE-only phase — gui.py is untouched).
- [Tests (folder)](../tests/___tests.md) — `test_jobtemp.py`.

## On-disk layout (Phase 7 — the critical regression guard)

Every backup path is resolved by one internal rule
(`JobTemp._path_for(rel, step)`):

- **`step=None`** (the four standalone tools, unchanged) →
  `root/rel` — BYTE-FOR-BYTE the same path this store has always used.
- **A named `step`** (e.g. `"bg"`, `"original"`) →
  `root/JOBTEMP_STEPS_SUBDIR/step/rel` — namespaced under a reserved
  subdir (`"__steps__"`) so a named-step backup can never collide with
  the unnamed backup or with another step's own backup.

`restore_all()` walks `root` but explicitly SKIPS anything under
`JOBTEMP_STEPS_SUBDIR`, so it only ever restores unnamed backups — a
plain `rglob("*")` with no such guard would wrongly treat a named-step
backup's path (e.g. `__steps__/bg/a.png`) as if it were a real `rel` and
try to restore it onto `folder/__steps__/bg/a.png`, corrupting the live
output tree. `clear()` has no such guard — it wipes the WHOLE slot
subdir (unnamed backups and every named step together), which is the
correct behavior for a full job-close wipe.

## API

### `TEMP_ROOT`
`PROJECT_ROOT/.painter_tmp` — the gitignored root; every job slot gets
a subdir under it.

### class `JobTemp(slot, folder)`
One tool job's backup store. The slot's subdir is FRESH on
construction (a reused slot never inherits an old job's backups).

- `backup(src, rel, step=None) -> Path` — copy the state of `folder/rel`
  into the store BEFORE the op (`step=None`) or the named pipeline stage
  touches it. Tracks the copied size for `bytes_used`.
- `drop(rel, step=None)` — delete a backup (for a no-op, so an unchanged
  file holds no restore point); also removes it from the byte tally.
- `before_path(rel, step=None) -> Path | None` — the backup path, or
  None.
- `has_backup(rel, step=None) -> bool`.
- `steps_for(rel) -> list[str]` — the named steps that currently hold a
  backup for `rel`, in PIPELINE order (`JOBTEMP_STEP_NAMES`) — e.g. what
  a per-step restore viewer's filmstrip would offer for one image. The
  unnamed (step=None) backup is never itself a "step" here.
- `restore_one(rel) -> bool` — copy the UNNAMED backup back over
  `folder/rel` (False when there is none).
- `restore_to(rel, step=None) -> bool` — restore `folder/rel` to its
  state right BEFORE `step` ran (`step=None` behaves like
  `restore_one`). A pipeline's "restore everything to pristine" calls
  this explicitly per image with `step="original"` — `restore_all()`
  (below) is NEVER widened to reach named-step data.
- `restore_all() -> int` — restore every UNNAMED backed-up file; returns
  the count. Named-step backups are out of scope (see "On-disk layout").
- `clear()` — wipe this job's whole subdir, unnamed and every named step
  alike (on panel CLOSE).
- `bytes_used` (property) `-> int` — cumulative size of every backup
  this job slot currently holds (unnamed + every named step), summed
  from a per-`(rel, step)` size table so a repeated `backup()`/`drop()`
  of the same key never double-counts or drifts.
- `over_cap() -> bool` — `True` once `bytes_used` has reached
  `JOBTEMP_MAX_BYTES` (4 GiB). `JobTemp` NEVER auto-evicts anything —
  this is only a signal; a future caller (Phase 8) decides what to do
  (stop taking new per-step backups, fall back to original-only, raise
  a persistent dashboard banner).

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
