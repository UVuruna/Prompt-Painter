# Job Temp Config — Flow

**About:** [description](../__about/jobtemp.md)

## Structure

```mermaid
flowchart TB
    A[jobtemp.py] --> B[BACKUP STORE — DIRNAME + PER-STEP LAYOUT]
    B --> B1[JOBTEMP_DIRNAME, JOBTEMP_REMOVED_ALPHA]
    B --> B2[JOBTEMP_STEPS_SUBDIR, JOBTEMP_STEP_NAMES]
    A --> C[DISK CAP + KEEP-ALL-STEPS TOGGLE + BANNER TEXT]
    C --> C1[JOBTEMP_MAX_BYTES]
    C --> C2[JOBTEMP_KEEP_ALL_STEPS_DEFAULT]
    C --> C3[JOBTEMP_CAP_BANNER_TEXT]
    A --> D[RESTORE VIEWER LABELS]
    D --> D1[JOBTEMP_STEP_LABEL]
    D --> D2[STEP_RESTORE_CURRENT_LABEL]
    A --> E[BEFORE/AFTER CHECKERBOARD BACKDROP]
    E --> E1[CHECKER_TILE_PX, CHECKER_LIGHT, CHECKER_DARK]
```

## The step ordering contract

`JOBTEMP_STEP_NAMES` fixes the canonical order regardless of the
order individual `backup()` calls actually happen in:

    ("original", "bg", "crop", "aspect", "upscale", "fixer")

`JobTemp.steps_for(rel)` (in `painter/jobtemp.py`) filters this tuple
down to whichever steps actually backed up one `rel` — its result is
ALWAYS in this order.
