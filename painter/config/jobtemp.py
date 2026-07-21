"""Tool temp / before-after / restore (owner 2026-07-19).

The four in-place tools back the ORIGINAL of every file up before they
touch it, so a job's whole folder (or one image) can be RESTORED and a
before/after viewer can show both. Backups live under a gitignored
project-local temp root, one subdir per job slot; cleared on the
panel's CLOSE, on app exit, and swept at startup.
"""

from .jobs import JOB_LABEL

JOBTEMP_DIRNAME = ".painter_tmp"  # PROJECT_ROOT-relative temp/backup root
# alpha below this counts as a "removed" (transparent) pixel for the BG
# metric — the same opacity notion as CROP_INK_ALPHA / CLEAN_EDGE_ALPHA.
JOBTEMP_REMOVED_ALPHA = 40

# GUI rework Phase 7 (owner decision 2026-07-21): the site-generation
# pipeline (BG -> Crop -> Aspect(force) -> Upscale, Phase 8) backs up an
# image's state before EVERY enabled step it runs, not just once — so a
# per-step restore viewer (Phase 9) can revert any single stage without
# losing the others. JobTemp namespaces those per-step backups under
# this reserved subdir name, which a real image's relative path is never
# expected to collide with, so a named-step backup can never be confused
# with the plain step=None backup the four standalone tools have always
# used (CRITICAL regression guard — see jobtemp.py), or with another
# step's own backup.
JOBTEMP_STEPS_SUBDIR = "__steps__"

# The ORDERING CONTRACT `JobTemp.steps_for(rel)` relies on. The pipeline
# itself runs BG -> Crop -> Aspect -> Upscale (Phase 8's reordered
# _compose_post_save), bookended by two backups that are not pipeline
# STEPS themselves: "original" is the pristine baseline captured before
# the pipeline touches the file at all — what "restore everything to
# pristine" restores to, via the explicit call
# `restore_to(rel, step="original")` — and "fixer" is the Fixer AI's
# pre-fix snapshot (Phase 20), taken long after the pipeline and the
# checker have already run. `steps_for()` filters THIS tuple down to
# whichever steps actually backed up one rel, so its result is always in
# this same original -> bg -> crop -> aspect -> upscale -> fixer order,
# regardless of the order the individual backup() calls actually
# happened in.
JOBTEMP_STEP_NAMES = ("original", "bg", "crop", "aspect", "upscale", "fixer")

# Intermediate-backup disk cap (owner decision 2026-07-21): 4 GiB per
# job. Findings' memory math — 4 enabled steps x ~3MB/image = ~12MB/image
# (~15MB with Fixer), so a realistic overnight batch (~300 images) peaks
# ~3.6-4.5GB, transient and cleared on close — sits close to this cap in
# the "keep every step" default case. `JobTemp.over_cap()` is a SIGNAL
# only (JobTemp never auto-evicts anything itself); the Phase 8 caller
# reads it to stop taking NEW per-step backups (falling back to
# original-only) and raise a persistent dashboard banner.
JOBTEMP_MAX_BYTES = 4 * 1024**3  # 4 GiB

# Per-agent "Keep every pipeline step (uses more disk)" toggle default
# (owner decision 2026-07-21) — ON: every enabled pipeline step gets its
# own restorable backup rather than only the original baseline. Consumed
# by the AgentPanel's ``keep_all_steps_var`` (GUI rework Phase 8);
# JobTemp itself has no notion of "agents" — it only ever backs up
# whatever step name a caller passes.
JOBTEMP_KEEP_ALL_STEPS_DEFAULT = True

# GUI rework Phase 8: the LOUD, PERSISTENT dashboard banner text a site
# job's panel shows the ONE time its JobTemp crosses JOBTEMP_MAX_BYTES
# (owner decision: "loud persistent dashboard banner, not just a log
# line") — formatted from that same constant so the number in the
# message can never drift from the real cap. Plain, static copy (no
# per-call parameters), so it lives here like every other user-facing
# string constant (SAFER_PREAMBLE, CONTINUE_NUDGE, AI_CHECK_INSTRUCTIONS).
JOBTEMP_CAP_BANNER_TEXT = (
    f"Backup cap reached ({JOBTEMP_MAX_BYTES / 1024 ** 3:.0f} GiB) — new"
    " per-step backups have stopped for this run; every image still"
    " keeps its ORIGINAL (pristine) backup, just not the BG/Crop/"
    "Aspect/Upscale in-between stages."
)

# GUI rework Phase 9: the per-step restore viewer's filmstrip label for
# each raw JOBTEMP_STEP_NAMES key ("original"/"bg"/... are internal
# identifiers, never shown to the owner as-is). The four real pipeline
# stages REUSE JOB_LABEL (Rule #5 — one label per tool kind, defined
# once); "original" and "fixer" are pipeline bookends with no tool of
# their own, so they get their own short label here. Every
# JOBTEMP_STEP_NAMES entry has one — see gui._filmstrip_stages.
JOBTEMP_STEP_LABEL = {
    "original": "Original",
    "bg": JOB_LABEL["bg"],
    "crop": JOB_LABEL["crop"],
    "aspect": JOB_LABEL["aspect"],
    "upscale": JOB_LABEL["upscale"],
    "fixer": "Fixer AI",
}

# The filmstrip's own final entry — the LIVE file as it stands right
# now. Not a JobTemp backup at all (so it carries no "Restore to here"
# of its own in gui.StepRestoreWindow), just the last stop after every
# kept named step in gui._filmstrip_stages's returned list.
STEP_RESTORE_CURRENT_LABEL = "Current"

# Transparency backdrop for the before/after viewer. BG removal (and the
# other tools) leave the AFTER image transparent where the background was
# cleared; drawn straight onto the panel colour, "removed" looks
# unchanged. So the viewer composites any image WITH ALPHA over a neutral
# light/dark checkerboard (the same cue Photoshop uses) and the removed
# area reads as removed. Deliberately theme-agnostic greys — this is a
# transparency backdrop, not app chrome.
CHECKER_TILE_PX = 12                 # checker square side, px
CHECKER_LIGHT = (205, 205, 205)      # the light squares
CHECKER_DARK = (150, 150, 150)       # the dark squares
