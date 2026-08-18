# Image Viewer

**Script:** [Image Viewer (script)](../image_viewer.py) ·
**Flow:** [diagram](../__flow/image_viewer.md)

## Purpose
`ImageViewer` (GUI rework Phase F4f, owner G6/G7) — the PORTRAIT
Prev/Next/Delete viewer that replaced [Doc Window](doc_window.md) for
IMAGE-level dashboard rows: the image's own file-stem title, the main
image (or its refusal/missing reason in its place), the prompt in a
read-only monospace block with its own "Copy (for AI)", and two
EXPANDABLE sub-sections — **Check** (the AI checker's verdict) and
**Steps** (the per-step restore filmstrip) — each entirely ABSENT
(not merely collapsed) when the caller gave it nothing to show for
the current entry.

Split out of the former `gui/viewers.py` (root Rule #20 god-file
refactor, 2026-07-30).

**The real gating condition (verified against `app_settings.py`, not
just this file — see Design Decisions):** both sections are gated on
whether the image was opened while a LIVE `DashPanel` for that site
still exists THIS SESSION, not on whether AI-check history or
pipeline backups exist on disk. `check_lookup`/`steps_lookup` are
`None` outright whenever `self.panels.get(site_key)` is `None` (no
panel object for that site slot right now) — in that case BOTH
sections are hidden regardless of what history actually sits on disk.
When a panel exists, `check_lookup` still returns `None` per-entry if
that drop path is missing from the panel's own in-memory
`_check_results` dict, and `steps_lookup` returns `[]` per-entry if
the panel's `jobtemp` is `None` or holds no backups for that `rel`.

Prev/Next walk an ORDERED list of plain-dict `entries` (the whole
collection/folder context the viewer was opened from) in ONE window —
no new Toplevels are created for navigation. Buttons disable at the
list ends (no wraparound). Delete always targets the CURRENTLY SAVED
file (`entry['dest']`), even while a Steps thumbnail is being
previewed in the main image slot — the confirmation dialog says so
explicitly.

## Connections
### Uses
- [Viewer Shared Rules](viewer_shared.md) — `DOC_MAX_FRAC`,
  `_copy_to_clipboard`, `_readonly_text_keys`
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo` and
  `ai_check_doc_md` (the Check section renders the SAME text
  `DashPanel._show_check` shows)
- [Scroll](scroll.md) — `ScrollFrame`
- [Theme](theme.md) — `finish_toplevel` (the shared Toplevel setup
  ritual), `THEME_TOPLEVELS` (unregister on `<Destroy>`), `skin_text`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`, `tk_font`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `ImageViewer`
- [Settings Mixin](app_settings.md) — `SettingsMixin._show_node_inner`
  opens it (the `"image"` level branch only — collection/folder levels
  still open `DocWindow`) through a PLAIN real-path import (see Design
  Decisions), building its `check_lookup`/`steps_lookup`/`restore_cb`/
  `on_restored`/`on_deleted` from the clicking site's own `DashPanel`
  (`_check_results`/`jobtemp`/`out_base`/`refresh_image_row`) — or all
  `None` when that site has no live panel

## Classes
### ImageViewer
See the Purpose section above and the class's own docstring. Key
methods: `_render_entry` (the one per-entry redraw, called on open,
Prev/Next, Delete and after a Steps restore); `_refresh_check_section`/
`_refresh_steps_section` (the presence/absence gate, see Purpose);
`_view_step_thumb`/`_clear_step_view` (swap the main image to a
Steps thumbnail and back, without leaving the window); `_restore_this_step`
(reuses the shared `_restore_step` helper, Rule #5 — never
re-implements `JobTemp.restore_to`); `_delete_current` (unlinks
`entry['dest']`, marks the entry deleted, advances or closes).

## Design Decisions
**`_prompt_txt`/`_check_txt` carry `width=1`** (2026-08-06, THE SPACE &
LEGIBILITY LAW rollout, `tests/test_layout_audit_tk.py`): a bare `tk.Text`
with no explicit width requests Tk's default 80-character grid, unrelated
to real content — `width=1` removes it as a hidden minimum on the outer
vertical `ScrollFrame` at the window's own declared minimum; both already
had an explicit `height=8`, so only width needed the fix.

**Opened through a PLAIN real-path import, not the deferred
`import gui; gui.DocWindow(...)` idiom its sibling viewers use.** No
test needs `monkeypatch.setattr(gui, "ImageViewer", fake)` (unlike
`DocWindow`/`StepRestoreWindow`, which `test_gui_checker.py`/
`test_gui_fixer.py`/`test_gui_pipeline.py` DO patch that way), so the
deferred idiom would buy nothing. It IS in `gui/__init__.py`'s
re-export block, so a future test could switch to the deferred form
without touching this module.

**`restore_cb(rel, label) -> bool` / `on_restored(entry)` are
additions beyond the `steps_lookup(rel) -> list[(label, Path)]`
2-tuple the section's presence/display contract uses.** Actually
restoring a step needs the raw `JobTemp` step key and a `JobTemp`
instance — neither travels through a bare `(label, Path)` display
pair. `SettingsMixin._image_viewer_restore_cb` reverses the display
label back to the raw step key via `_STEP_LABEL_TO_KEY` (safe: every
`JOBTEMP_STEP_LABEL` value is unique) before calling the shared
`_restore_step`.

**Why Check/Steps disappear when a site's dashboard panel is gone —
confirmed by reading `app_settings.py`, not assumed from this file
alone.** `_show_node_inner` resolves `panel = self.panels.get(site_key)`
and hands `_image_viewer_check_lookup(panel)` /
`_image_viewer_steps_lookup(panel)` to the viewer; both helpers return
`None` outright when `panel is None`. Since `self.panels` only holds
CURRENTLY RUNNING (or not-yet-closed) `DashPanel` instances for this
session, opening a dashboard row's "Show" AFTER closing that site's
panel — even though the AI-check report and pipeline backups are
still sitting on disk — shows an image with no Check/Steps sections
at all. This is a real, observable behavior, not a bug this doc is
fixing; flagged here because the legacy description only said
"lookup-gated" without naming what the lookup is actually keyed on.
