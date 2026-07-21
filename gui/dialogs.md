# Modal Dialogs

**Script:** [Modal Dialogs (script)](dialogs.py)

## Purpose
The AI modal dialogs, pulled out of `gui/__init__.py` (root Rule #20
god-file refactor):

- `_ModalToolDialog` — shared centre-on-parent placement math
  (`_center_on`), kept as its own base for a hypothetical future
  non-AI modal dialog (Rule #5), even though `_AiDialog` is its only
  family today.
- `_AiDialog` — the worker->UI queue poll loop shared by both AI
  dialogs (`_init_ai_queue`/`_arm_poll`/`_poll`), so worker threads
  only ever `self._q.put(...)` and never touch a widget directly.
- `AiKeyWizard` — the guided Gemini-API-key onboarding (four numbered
  steps + Test key + Save key), opened from the toolbar and
  automatically on `NoKey`.
- `AiSheetDialog` — 'New collection (AI)…': a clarifying-questions
  poll, then a generated `.md` validated by the real parser (one
  automatic repair round); a still-broken draft opens in a
  `DocWindow` for manual fixing instead of loading.

`AI_POLL_MS` (the worker-queue poll cadence) moves HERE with
`_AiDialog` — the class that owns the loop it paces — and is
re-exported from `gui/__init__.py` so `gui.AI_POLL_MS` keeps resolving
for every OTHER late-binding reader (see Design Decisions).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`AI_STUDIO_URL`, `AI_TEST_PROMPT`, `SHEETS_DIR`); `ai` (imported
  LOCALLY inside each worker closure — `generate_text`/`AiError`,
  `contract_text`/`ask_questions`, `generate_sheet`, `save_sheet` —
  mirrors the original file's own lazy-import convention)
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_text`,
  `skin_toplevel`
- [Viewers](viewers.md) — `DocWindow` (`AiSheetDialog._finish`'s
  "fix manually, not loaded" viewer)
- [Themed Widget Toolkit](widgets.md) — `rounded_button`,
  `rounded_entry`, `status`, `tk_font`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `AiKeyWizard`,
  `AiSheetDialog`, `AI_POLL_MS` and (for any remaining internal
  reference) `_AiDialog`/`_ModalToolDialog`
- `PainterGui` (still in `gui/__init__.py`) — opens `AiKeyWizard`/
  `AiSheetDialog` by their re-exported bare names (the toolbar's 'AI
  key…'/'New collection (AI)…' buttons, and automatically on `NoKey`)
- `gui.api_panel.ApiImageGenPanel._arm_probe_poll` and
  `gui.viewers.DocWindow._arm_fix_poll` — both reach `AI_POLL_MS`
  through a deferred `import gui` rather than importing this module
  directly (see Design Decisions)

## Classes

### `_ModalToolDialog`
See the Purpose section above.

### `_AiDialog`
See the Purpose section above.

### AiKeyWizard
See the Purpose section above.

### AiSheetDialog
See the Purpose section above.

## Design Decisions
**Why `AI_POLL_MS` didn't stay in `gui/__init__.py`.** The prior step
(`gui.api_panel`) left it behind specifically because `_AiDialog` (its
only OTHER reader at the time) hadn't moved yet — moving it then would
have just relocated the same circular-import problem onto
`ApiImageGenPanel`. Now that `_AiDialog` itself has moved, the constant
follows its real owner into `gui.dialogs`. `gui.api_panel` and
`gui.viewers` (`DocWindow`'s own unrelated Fixer poll) both keep
reaching it via a deferred `import gui; gui.AI_POLL_MS` — the same
late-binding idiom `gui.theme._pkg()` established — rather than a
real-path `from .dialogs import AI_POLL_MS`, since `gui.viewers` would
then be circular with `gui.dialogs` (which imports `DocWindow` FROM
`gui.viewers`).
