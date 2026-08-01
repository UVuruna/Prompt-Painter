# Job Temp Config

**Script:** [Job Temp Config (script)](../jobtemp.py) ·
**Flow:** [diagram](../__flow/jobtemp.md)

## Purpose

Tool temp / restore / before-after config (owner 2026-07-19): the
four in-place tools' backup store layout, the per-step backup ordering
contract, the disk cap + "keep every step" toggle, the restore
viewer's filmstrip labels, and the before/after viewer's transparency
checkerboard.

**Distinct from `painter/jobtemp.py`** (top level, outside `config/`):
that file owns the `JobTemp` CLASS (the actual backup/restore
mechanics); this file owns only its TUNABLES. Same short name,
different folder, different responsibility.

## Connections

### Uses
- [Jobs Config](jobs.md) — `JOB_LABEL` (the four real pipeline stages
  reuse it rather than duplicating a label)

### Used by
- [Job Temp](../../__about/jobtemp.md) (`painter/jobtemp.py`) — every
  constant here (`JOBTEMP_DIRNAME`, `JOBTEMP_REMOVED_ALPHA`,
  `JOBTEMP_STEPS_SUBDIR`, `JOBTEMP_STEP_NAMES`, `JOBTEMP_MAX_BYTES`,
  `JOBTEMP_KEEP_ALL_STEPS_DEFAULT`)
- GUI (`gui/restore_windows.py`) — `JOBTEMP_STEP_LABEL`,
  `STEP_RESTORE_CURRENT_LABEL`, `JOBTEMP_CAP_BANNER_TEXT`
- GUI before/after viewer (`gui/image_viewer.py`,
  `gui/viewer_shared.py`) — `CHECKER_TILE_PX`, `CHECKER_LIGHT`,
  `CHECKER_DARK`
- Re-exported by [Config Package Index](__init__.md)

## Constants

**Backup store — dirname + per-step layout:**
- `JOBTEMP_DIRNAME` — `.painter_tmp`, the gitignored temp/backup root
- `JOBTEMP_REMOVED_ALPHA` — alpha below this counts as "removed" for
  the BG metric
- `JOBTEMP_STEPS_SUBDIR` — `__steps__`, namespaces per-step backups
  from the plain (step=None) backups the four standalone tools use
- `JOBTEMP_STEP_NAMES` — the ordering contract
  `JobTemp.steps_for(rel)` relies on: `("original", "bg", "crop",
  "aspect", "upscale", "fixer")`

**Disk cap + keep-all-steps toggle + banner text:**
- `JOBTEMP_MAX_BYTES` — 4 GiB per job (owner decision 2026-07-21)
- `JOBTEMP_KEEP_ALL_STEPS_DEFAULT` — per-agent "keep every step"
  toggle default (ON)
- `JOBTEMP_CAP_BANNER_TEXT` — the loud, persistent dashboard banner
  shown once a job crosses the cap; formatted FROM `JOBTEMP_MAX_BYTES`
  so the number can never drift from the real cap

**Restore viewer labels:**
- `JOBTEMP_STEP_LABEL` — raw step key → filmstrip label (the four
  pipeline stages reuse `JOB_LABEL`; `"original"`/`"fixer"` get their
  own)
- `STEP_RESTORE_CURRENT_LABEL` — the filmstrip's final "Current" entry
  (the live file, not a backup)

**Before/after checkerboard backdrop:**
- `CHECKER_TILE_PX`, `CHECKER_LIGHT`, `CHECKER_DARK` — the
  theme-agnostic transparency backdrop (Photoshop-style checker)
