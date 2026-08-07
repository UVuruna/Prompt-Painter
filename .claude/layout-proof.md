SESSION: 1a7f7544-71ac-4569-a919-84dcbae8047b

Session change under review, in two commits:
* `2091e37` — `BeforeAfterWindow._add_pair` lays each Before/After pair
  SIDE BY SIDE (gui/restore_windows.py).
* `ad8f473` — the window now OPENS AT THE SIZE OF ITS CONTENT and a
  resize grows the elements too (gui/restore_windows.py +
  gui/dash_helpers.py). This landed because an INDEPENDENT grader failed
  the first pass at 4/10: the pair was side by side but the window still
  took its height from a blind `screen_h * DOC_HEIGHT_FRAC`, leaving the
  1664x2550 plate in the top third of a 1382px frame. See
  `.claude/visual-proof.json`.

* `THE PACE` — `AgentPanel` and `ApiImageGenPanel` lost their four/two
  pace spinners for ONE "Polite pace" switch (gui/agent_panel.py,
  gui/api_panel.py, gui/app_jobs.py). The Pacing group is now one switch
  plus its range hint and the on-degrade combo.

Every window below was re-shot by `tests/test_layout_audit_tk.py` in
this session and OPENED and graded here against DESIGN.md.

- PainterGui menu (gui/app.py + gui/menu.py) - MIN 1099x640 - SHOT .claude/shots/PainterGui_menu.png - GRADE 9/10 - audit: PASS - python tests/test_layout_audit_tk.py, minimum + minimum+50% + 2560x1400
- PainterGui main (gui/app.py + gui/app_views.py + gui/agent_panel.py) - MIN 1099x640 - SHOT .claude/shots/PainterGui_main.png - GRADE 9/10 - audit: PASS - same run
- PainterGui running (gui/app.py + gui/tool_dash.py) - MIN 1099x640 - SHOT .claude/shots/PainterGui_running.png - GRADE 9/10 - audit: PASS - same run
- DocWindow (gui/doc_window.py) - MIN 520x400 - SHOT .claude/shots/DocWindow.png - GRADE 8/10 - audit: PASS - python tests/test_layout_audit_tk.py, minimum + minimum+50%
- ImageViewer (gui/image_viewer.py) - MIN 420x560 - SHOT .claude/shots/ImageViewer.png - GRADE 8/10 - audit: PASS - same run
- BeforeAfterWindow (gui/restore_windows.py) - MIN 520x400 - SHOT .claude/shots/BeforeAfterWindow.png - GRADE 9/10 - audit: PASS - same run
- StepRestoreWindow (gui/restore_windows.py) - MIN 520x400 - SHOT .claude/shots/StepRestoreWindow.png - GRADE 8/10 - audit: PASS - same run
- SelectWindow (gui/select_window.py) - MIN 860x520 - SHOT .claude/shots/SelectWindow.png - GRADE 8/10 - audit: PASS - same run
- AiKeyWizard (gui/dialogs.py) - MIN 542x396 (FIXED SIZE, resizable(False, False), content-fit) - SHOT .claude/shots/AiKeyWizard.png - GRADE 9/10 - audit: PASS - same run, minimum only (no +50% - non-resizable)

Every MIN fits inside 1280x720; no window needed a raised floor this
session, so `.claude/layout-frame.json` stays absent.

## What I actually saw in each shot

**BeforeAfterWindow 9/10 (the window this session changed).** Re-opened
and re-graded AFTER commit `ad8f473`, since the audit re-shot it. MULTI
mode at MIN: per changed image, the file path as a heading, then "Before"
and "After" as two columns reading LEFT to RIGHT, top-aligned, a
separator between pairs. The two 40px test fixtures now UPSCALE to fill
their columns instead of sitting as postage stamps in a window opened for
them — the owner's rule working in the other direction. Nothing clipped,
no text elided; the scrollbar is present because there genuinely are more
pairs below, not because a pair is starved.

Independently verified at production size on the owner's real 1664x2550
plate by a separate grader (not the implementer): the window opens
760x730 with the image row filling ~70 % of its height, and after a
manual resize to 1100x1000 the row fills ~76 % with visibly larger
glyphs — the frame and the content grow together. Both states graded
9/10; see `.claude/visual-proof.json`.

**PainterGui menu 9/10.** Eight equal tiles on a 4x2 grid, consistent
icon/title/description rhythm, per-tile accent colours distinct, gutters
even, no orphaned text. Nothing to fix.

**PainterGui main 9/10.** Re-opened after the Polite pace change.
Settings column left, queue column right, labels aligned to their
controls, the "0 prompt(s) - 0 complete pair(s) -> 0 will run"
eligibility line reads clearly. The Pacing group is now ONE switch
("Polite pace") with its range hint "12-36s between images; off =
2-13s" beside it, then the on-degrade combo on its own row — where four
spinners used to sit. Raised from 8/10 because losing them shortened the
left column enough that the Prompt group (Background / Style) now
reaches the fold instead of scrolling out of sight at the MINIMUM size.

**PainterGui running 9/10.** Empty-state dashboard: tabs, toolbar,
centred "No jobs yet — press a site Start, or a tool button above."
The large empty area is an EMPTY job list, not starved content.

**DocWindow 8/10.** Heading wraps properly, the prompt code block is
readable monospace, the bar's four buttons wrap onto a second row rather
than widening the window (`wrap_bar_label` doing its job). Body text
continues below the fold into its scroll region — expected for a
document viewer, and why this is an 8.

**ImageViewer 8/10.** Prev/Next/Delete bar, title, thumbnail, Prompt
panel with Copy button, collapsed "Check" and "Steps (3)" disclosures.
Empty space below the collapsed sections is the disclosures being
closed, not a hole.

**StepRestoreWindow 8/10.** Horizontal filmstrip, one stage per column
with its own "Restore to here". The fourth column is partly past the
right edge WITH a horizontal scrollbar under it — deliberate for a
filmstrip at its minimum width, and the reason it stays an 8.

**SelectWindow 8/10.** Hint, legend, per-site totals right-aligned, two
collapsed sheet rows with matching per-site counts. Columns line up; the
empty area below is collapsed tree content.

**AiKeyWizard 9/10.** Fixed-size guided setup: numbered steps, one
primary action button, key field full width, three footer buttons
right-aligned with clear hierarchy. Well spaced, nothing cramped.
