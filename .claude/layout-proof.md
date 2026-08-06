SESSION: 2e702622-ce8d-4fbf-b18c-3d823f7b1046

- PainterGui menu (gui/app.py + gui/menu.py) - MIN 1099x640 - SHOT .claude/shots/PainterGui_menu.png - GRADE 9/10 - audit: PASS - python tests/test_layout_audit_tk.py, minimum + minimum+50% + 2560x1400
- PainterGui main (gui/app.py + gui/app_views.py) - MIN 1099x640 - SHOT .claude/shots/PainterGui_main.png - GRADE 8/10 - audit: PASS - same run
- PainterGui running (gui/app.py + gui/tool_dash.py) - MIN 1099x640 - SHOT .claude/shots/PainterGui_running.png - GRADE 8/10 - audit: PASS - same run
- DocWindow (gui/doc_window.py) - MIN 520x400 - SHOT .claude/shots/DocWindow.png - GRADE 8/10 - audit: PASS - python tests/test_layout_audit_tk.py, minimum + minimum+50%
- ImageViewer (gui/image_viewer.py) - MIN 420x560 - SHOT .claude/shots/ImageViewer.png - GRADE 8/10 - audit: PASS - same run
- BeforeAfterWindow (gui/restore_windows.py) - MIN 520x400 - SHOT .claude/shots/BeforeAfterWindow.png - GRADE 8/10 - audit: PASS - same run
- StepRestoreWindow (gui/restore_windows.py) - MIN 520x400 - SHOT .claude/shots/StepRestoreWindow.png - GRADE 8/10 - audit: PASS - same run
- SelectWindow (gui/select_window.py) - MIN 860x520 - SHOT .claude/shots/SelectWindow.png - GRADE 8/10 - audit: PASS - same run
- AiKeyWizard (gui/dialogs.py) - MIN 542x396 (FIXED SIZE, resizable(False, False), content-fit) - SHOT .claude/shots/AiKeyWizard.png - GRADE 9/10 - audit: PASS - same run, minimum only (no +50% - non-resizable)

7 top-level windows total (PainterGui + 6 dialog Toplevels), all registered
(added this session — MIGRATE-LAYOUT.md step 2: "a window missing from the
registry is a hole in the guard"; the earlier pass in this lineage had
registered PainterGui only). NOT separately registered: `_ModalToolDialog`/
`_AiDialog` (gui/dialogs.py) — abstract plumbing with no concrete instance of
their own; their only live subclass chain (`_AiDialog` -> `AiKeyWizard`) IS
registered above (`AiSheetDialog`, the other former `_AiDialog` subclass, was
retired — see gui/dialogs.py's own docstring).

## How PASS was established

`tests/test_layout_audit_tk.py` (installed this session per MIGRATE-LAYOUT.md
- the Tk translation of the Remote User reference audit; EXPANDED later this
session from a PainterGui-only registry to all 7 top-level windows): the REAL
PainterGui built off-screen (x=+9000, alpha 0 - nothing flashes on the
owner's display), audited in all three views at the computed minimum, at
+50% and at 2560x1400:

- CLIPPED - a mapped widget allocated less than its own requested size
- ESCAPES - a child's box leaving the window's box
- the minsize is COMPUTED (`_apply_min_size` derives it from the Main Menu
  grid - owner 2026-08-03) and fits THE SCREEN FLOOR 1280x720 (1099x640 does)

Zero faults on the first run - the 2026-08-03 UI rework already obeys the
law. Screenshots via Win32 PrintWindow(PW_RENDERFULLCONTENT), taken by the
audit itself at the minimum, so the picture is of the exact build measured.

Honesty note (also in the audit's docstring): Tk has no per-widget elide API
and no cheap scrollbar-range introspection, so the Qt audits' ELIDED and
SCROLL+SLACK checks have no direct Tk equivalent here - CLIPPED + ESCAPES
catch their visible consequences.

**The 6 dialog windows (added later this session):** each built in its
FULLEST realistic state (real markdown with headings/code/bullets, multi-pair
before/after sets, a 4-stage restore filmstrip, two collections with a DONE
item and a SUPERSEDED-advice item, real check/steps data — see
`tests/test_layout_audit_tk.py`'s own `_doc_window_win`/`_image_viewer_win`/
`_before_after_win`/`_step_restore_win`/`_select_window_win`/
`_ai_key_wizard_win` factories), audited the same way (a new
`_OffscreenToplevels` context manager pins every `tk.Toplevel` off-screen and
transparent the INSTANT it is born — before its own `__init__` can lay out a
single widget at the window manager's default on-screen position — and
neutralises `wait_window` so AiKeyWizard's own modal loop never blocks the
audit).

**First run on the expanded registry: 27 real CLIPPED faults across 5 of the
6 dialogs**, all fixed per the ladder (not suppressed — each is a genuine,
reproducible layout bug, several with PRODUCTION (not test-invented) text
that overflows the window's own declared minimum):

1. **DocWindow/BeforeAfterWindow/StepRestoreWindow/SelectWindow top bars**
   overflowed their declared minimum width — the hint/subtitle Label never
   wrapped, so realistic (BeforeAfterWindow/StepRestoreWindow/SelectWindow:
   actual PRODUCTION strings, not test-invented) hint text forced the bar
   wider than the window. Fixed (ladder step 2, reflow): new
   `gui.widgets.wrap_bar_label(bar, label, *buttons)` wires each hint/
   subtitle Label to wrap into the bar's live remaining width (buttons'
   `winfo_reqwidth()` reserved, computed on every `<Configure>`) instead of
   forcing the window wider.
2. Two FALSE POSITIVES in the audit's own measurement, investigated and
   confirmed by hand, then fixed correctly (source fix where the false
   signal came from a real gap, test-side exemption where it was purely a
   Tk measurement quirk):
   - A bare `tk.Text` with no explicit `width`/`height` requests Tk's
     DEFAULT 80x24 character grid, unrelated to real content — every Text
     here wraps ("word") and/or scrolls, so a smaller allocation is the
     point. Fixed at the SOURCE: `gui/doc_window.py`'s `self.txt` and
     `gui/image_viewer.py`'s `_prompt_txt`/`_check_txt` now carry
     `width=1` (`doc_window.py`'s `txt` also `height=1`) — the SAME
     convention `gui/sheetgen_panel.py` already used for its own two Text
     widgets, just not yet applied to these.
   - `gui.scroll.ScrollFrame`'s own viewport `tk.Canvas` — confirmed by
     hand (`winfo_reqwidth()`/`cget("width")` stuck at 472 after a resize
     down to 408, while `bbox('all')`, the embedded item's real width, and
     `winfo_width()` all correctly read 408): Tk's Canvas requested size is
     the LARGEST it has ever needed, not a live figure, lagging behind
     `ScrollFrame._apply_width`'s `itemconfigure` shrink. `check_clipped`
     now exempts the ScrollFrame/canvas widgets themselves — real overflow
     inside a scrolled body still shows up via `check_escapes`, which reads
     real on-screen coordinates, never this stale request.
3. A ScrollFrame debounce timing gap: `gui/scroll.py` defers its width/
   scrollregion re-fit past `RESIZE_SETTLE_MS` (150ms) so a window DRAG
   never re-fits on every intermediate `<Configure>` — the audit's own
   `settle()` now actively pumps the event loop for 220ms after every
   resize instead of measuring immediately, so it never reads a stale
   pre-resize layout.

**Also fixed: a cross-interpreter crash that only showed up in the FULL
suite.** `run_audit()` used to build its OWN separate `tb.Window()`;
`gui.icons`' icon cache is process-lifetime and ties each cached image to the
Tcl interpreter that first rendered it, so a second, independent interpreter
reusing that cache raised `TclError: image "pyimageN" doesn't exist` —
reproduced deterministically with `pytest tests/test_gui_widgets.py
tests/test_layout_audit_tk.py -q` (fails), confirmed as PRE-EXISTING (not
introduced by the dialog-registry expansion — the PainterGui-only version had
the identical bug). Fixed: `run_audit()` now takes a GIVEN root — the pytest
test passes the suite's own shared `tk_root` fixture (deiconified for the
run, withdrawn again after, matching `tests/conftest.py`'s own convention);
only the standalone `python tests/test_layout_audit_tk.py` CLI entry point
builds (and fully destroys) its own fresh root. Verified:
`python -m pytest tests -q` — 964 passed, 1 skipped (run twice, stable).

## Grades - what the pictures show

- menu 9/10: the 4x2 bento tile grid, per-tool accent borders, dark-first,
  reads instantly at the minimum.
- main 8/10: dense but coherent two-column setup (agents/pipeline/pacing
  beside collections/output), single blue accent for section titles.
- running 8/10: clean empty-state dashboard with a clear call to action.
- DocWindow 8/10: readable markdown (heading/bold/code), the top bar's hint
  and four action buttons (Copy/Close/Image Fix/Website Fix) now stay on
  one line at the minimum with room to spare; the body scrolls cleanly past
  the fold with a visible bar — legitimate, the window is genuinely full.
- ImageViewer 8/10: Prev/Next/Delete always visible up top, image + prompt
  clear, Check/Steps as a tidy collapsed accordion — functional and clean,
  though the collapsed state leaves real empty space below at the minimum
  (an intentional accordion resting state, not starvation of any element
  that needs it).
- BeforeAfterWindow 8/10: consistent with DocWindow's chrome, the MULTI-mode
  subtitle now wraps to two lines instead of forcing the window wider,
  before/after pairs scroll cleanly.
- StepRestoreWindow 8/10: a proper horizontal filmstrip (4 stages + Current),
  a horizontal scrollbar correctly appears once the stages exceed the
  minimum width — legitimate scroll, not a bug.
- SelectWindow 8/10: the tree + legend + per-site totals read clearly at the
  minimum; the long hint line now wraps under the button row instead of
  pushing the window past 860px.
- AiKeyWizard 9/10: a tight, well-composed four-step wizard, sized exactly
  to its content — nothing wasted, nothing crowded.

## Changes this session

- gui/menu.py: the one `grid_propagate(False)` carries a written exemption
  (tile box computed by `gui.logic.menu_min_size`; `_apply_min_size` raises
  the window minsize so the whole grid always renders). [earlier pass]
- tests/test_layout_law.py + tests/test_layout_audit_tk.py installed,
  wired into tests/run_guards.py (static in --fast, audit in the full run).
  [earlier pass]
- gui/widgets.py: new `wrap_bar_label(bar, label, *reserved)` — see "How
  PASS was established" #1 above. [this pass]
- gui/doc_window.py, gui/restore_windows.py (`BeforeAfterWindow`,
  `StepRestoreWindow`), gui/select_window.py: wired `wrap_bar_label` onto
  each window's own top-bar hint/subtitle. [this pass]
- gui/doc_window.py, gui/image_viewer.py: `width=1`(`/height=1`) on the bare
  `tk.Text` widgets — see "How PASS was established" #2 above. [this pass]
- tests/test_layout_audit_tk.py: expanded from a PainterGui-only registry to
  the full 7-window registry, fixed the cross-interpreter icon-cache crash,
  fixed the ScrollFrame settle-timing gap, added the CLIPPED-check
  exemptions for `tk.Text` and `ScrollFrame`/its canvas. [this pass]

## Guard self-tests (both teeth SEEN failing, then passing)

- static: planted a `grid_propagate(False)` comment-free -> FAIL; removed -> PASS.
  [earlier pass]
- runtime, PainterGui: planted WINDOW_MIN_W = 6000 (the owner's own "6000px
  menu" scenario) -> "ABSURD MINIMUM 6000x640 - does not fit the screen
  floor 1280x720" -> reverted -> PASS. [earlier pass]
- runtime, dialog registry (this pass): removed the
  `wrap_bar_label(bar, hint_lbl, copy_btn, close_btn)` call from
  `DocWindow.__init__` -> `python tests/test_layout_audit_tk.py` printed
  `LAYOUT AUDIT: FAIL` with `[DocWindow @ minimum 520x400] CLIPPED TFrame
  ...: has 520x49, requested 571x49` plus the squeezed Close button's own
  CLIPPED lines -> restored (diffed byte-identical against the pre-plant
  backup) -> `LAYOUT AUDIT: PASS`.

## Every GUI file the Stop gate lists for this session - where each is covered

My own edits, covered by the window lines above / in the root proof:
cycling_header.py, session_keeper_overlay.py, shutdown_dialog.py,
settings_tab.py, system_config.py, styled_inputs.py, filtered_log_panel.py,
home_tab.py (all Aviator - see Applications/Aviator/.claude/layout-proof.md,
7 windows, GRADE >= 8/10, audit PASS) and, in PromptPainter: menu.py
(earlier pass — the PainterGui menu line above, GRADE 9/10), widgets.py,
doc_window.py, image_viewer.py, restore_windows.py, select_window.py (this
pass — the 6 dialog-window lines above, GRADE >= 8/10, audit PASS).

probe_watchface.py - a throwaway MEASUREMENT probe in the session scratchpad
(it built WatchFaceDialog off-screen to measure the 826x2090 absurd minimum);
it is not part of any project and shipped nothing - the window it measured is
covered by "Gadgets/DOMY Watch/.claude/layout-proof.md" (WatchFaceDialog,
MIN 862x720, GRADE 8/10).

Touched by the PARALLEL session (its uncommitted working tree, not my edits),
all covered by that same DOMY proof and verified here by my own audit re-run
(10/10 PASS): observatory.py, dialog.py, location_section.py,
cube_preview3d.py, time_travel.py, shortcuts_window.py, window.py,
widgets.py, ring.py, hands.py, umbra_aura.py, pointer.py,
weekday_theme_grid.py.
