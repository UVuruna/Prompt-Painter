# Review (Staging & Approval)

**Script:** [Review (script)](review.py)

## Purpose
Phase two of the output workflow (owner 2026-07-17). Phase one — the
run loop — writes every generated image to
`<out>/_staging/<site>/<drop-path>`. This module owns what happens
next: listing what is staged, and executing the owner's verdict.
Only his Approve puts an image at its final destination.

- `approve` → moves the image to `<out>/<site>/<drop-path>`
  (creating folders as needed). The progress mark stays — an
  approved image is done.
- `reject` → deletes the staged image AND clears its entry from the
  progress sidecar, so the next run regenerates it (usually after
  the prompt was reworked in the sheet).

## Connections

### Uses
- [Config](config.md) — `STAGING_DIRNAME`, `PROGRESS_SUFFIX`,
  `IMAGE_EXTENSIONS`

### Used by
- [GUI](../gui.md) — the review window (thumbnails +
  Approve/Reject per image, Approve-all)
- [Main (CLI)](../main.md) — `--approve-all` and the end-of-run
  staging summary

## API

- `staging_root(out_base, site)` / `final_root(out_base, site)` —
  the two folder roots.
- `staged_images(out_base, sites) -> list[StagedImage]` — every
  image awaiting a verdict (progress sidecars are never listed).
- `approve(out_base, item) -> Path` / `reject(out_base, item)`.

### StagedImage
`site`, `drop_path` (the sheet's own POSIX-relative path), `path`
(where it sits in staging).
