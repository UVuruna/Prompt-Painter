# Prompt + Image Section

**Script:** [Prompt + Image Section (script)](../prompt_image.py)

## Purpose
`PromptImageSection` — the PROMPT + IMAGE mode's setup surface (faza 2,
owner 2026-08-03, UV/prompt.txt tačka 3). The owner's rule: with the
mode ON, a run generates ONLY items that have BOTH a prompt and their
declared reference image(s) on disk — "ako učitam sve promptove i samo
1 sliku, radi se tačno 1 slika". The pairing is AUTHORED IN THE SHEET
(the `←` line(s) per entry, instructions.md rule 3c — a reference
sheet's prompt says "the ATTACHED IMAGE"), never guessed here by
filename matching (that idea belongs to AI CHECK's own drop-path
pairing and stays there).

The section owns the run's REFERENCE FOLDER — rung ② of the binding
resolution order (sheet folder → Reference folder → absolute,
`painter.runner.resolve_input_images`, deliberately REUSED rather than
re-derived — one resolution truth) — and a live per-entry eligibility
view over the queued collections (✔ complete / ✖ reference missing /
— no `←` line, plus the summary count). The section only REPORTS; the
actual narrowing happens in `run_sheet(require_input_image=True)` at
Start, against the disk state of that moment.

The mode TOGGLE button sits beside "Select images…"
(`BuildMixin._build_inputs_tail` — the owner's "TAJ BUTTON tamo gde je
SELECT IMAGES"), filled-ON / outline-OFF in the website tile's indigo;
the section itself grids into the setup right column's LOWER HALF only
while ON (`_apply_prompt_image_state`), splitting the column's height
50-50 with the Collections queue above it.

## Connections

### Uses
- [Run Loop](../../painter/__about/runner.md) — `resolve_input_images`
  (the ONE resolution order, reused verbatim)
- [Sheet Parser](../../painter/__about/sheet_parser.md) —
  `parse_sheet`/`SheetError` (the live eligibility view re-parses the
  queue)
- [The Theme Engine](theme.md) — `skin_listbox`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`/
  `rounded_entry`/`tk_font`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `PromptImageSection` for external tests
- [Build Mixin](app_build.md) — builds ONE section into the setup
  right column (`_pi_section`), owns the toggle button + the
  show/hide reconcile (`_toggle_prompt_image`/
  `_apply_prompt_image_state`)
- [Settings Mixin](app_settings.md) — persists `prompt_image`
  (enabled + reference_dir) and refreshes the view on queue mutations
  (`_refresh_prompt_image`)
- [Site Jobs Mixin](app_jobs.md) — Start reads `reference_dir()`/
  `enabled()` into `run_sheet(reference_dir=…,
  require_input_image=…)` — for the two website sites AND the API
  image job (one mode, every generator)

## Classes

### PromptImageSection
See Purpose above. Key state: `enabled_var` (the mode), `ref_dir_var`
(debounced trace → `refresh`), `status_list` (the per-entry lines),
`summary_var`. `refresh()` re-parses queued sheets and resolves every
entry's refs; `reference_dir()` returns the folder (None while blank —
a set but nonexistent folder is flagged in the list, not silently
dropped); `get_settings`/`apply_settings` — the standard round-trip.

## Design Decisions
- **Folder, not a loose-image pool.** Resolution stays EXACTLY the
  runner's three rungs — a GUI-side pool matched by basename would be
  a SECOND pairing mechanism with its own edge cases (the stem-match
  idea the owner explicitly rejected for generation). Point the
  Reference folder at any stash; the sheet's `←` paths do the rest.
- **Shared by design (Rule C), delivered in faza 3:** every
  [Collections Column](collections_column.md) (the website setup's
  AND the API panel's) renders its OWN section instance over the ONE
  shared mode state (`enabled_var`/`ref_dir_var` passed in — a
  standalone section, as in tests, still makes its own vars); the
  mode flips everywhere at once and both Starts honour it.
