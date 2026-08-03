# Modal Dialogs

**Script:** [Modal Dialogs (script)](../dialogs.py) ·
**Flow:** [diagram](../__flow/dialogs.md)

## Purpose
The AI modal dialogs, pulled out of `gui/__init__.py` (root Rule #20
god-file refactor):

- **`_ModalToolDialog`** — the shared centre-on-parent placement
  helper (`_center_on`). It survives as its own base only because
  `AiKeyWizard` (via `_AiDialog`) still uses it — the old standalone
  Upscale/Aspect modal dialogs that used to be its other callers are
  retired (Phase 14), and `AiSheetDialog` retired too (faza 4 — the
  wizard is a real panel now, [Sheet Generator Panel](sheetgen_panel.md)).
- **`_AiDialog`** — the worker-queue poll loop the AI dialog family
  shares (`_init_ai_queue`/`_arm_poll`/`_poll`), so worker threads only
  ever `self._q.put(...)` and never touch a widget directly. It is
  also the owner of the module's `AI_POLL_MS` constant — the constant
  followed `_AiDialog` here from `gui/__init__.py` once that class
  itself moved, since its only other reader (`ApiImageGenPanel`)
  hadn't moved yet before that.
- **`AiKeyWizard`** — the guided Gemini-API-key onboarding: four
  numbered steps (open the AI Studio signup page via the system
  browser, sign in, create a key, paste it), a "Test key" button
  making one tiny REAL call on a worker thread (green status on
  success, a loud red error otherwise), and "Save key" persisting it
  immediately. Opened by the toolbar's "AI key…" button AND
  AUTOMATICALLY whenever any AI feature is invoked and the underlying
  call raises `ai.NoKey` (`SettingsMixin._ensure_ai_key`) — the key is
  re-checked once the wizard closes (verified: `AiKeyWizard.__init__`
  ends with a blocking `self.wait_window(self)`, so the caller's
  second `ai.api_key()` check runs only after the modal actually
  closes). It is FULLY MODAL (`grab_set()`) and therefore deliberately
  does NOT register in `THEME_TOPLEVELS` — the grab blocks the
  Day/Night switch too, so a flip genuinely cannot happen while it is
  open.
- **`AiSheetDialog`** — RETIRED (faza 4, owner 2026-08-03, UV
  tačka 4): the request → questions → sheet flow lives in
  [Sheet Generator Panel](sheetgen_panel.md) now, as a persistent
  setup panel with an editable, parser-revalidated draft.

## Connections
### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`AI_STUDIO_URL`, `AI_TEST_PROMPT`); `ai` (imported LOCALLY inside
  the Test-key worker closure — `generate_text`/`AiError` — mirrors
  the rest of this codebase's lazy-import convention for `ai`)
- [Theme](theme.md) — `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`,
  `rounded_entry`, `status`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `AiKeyWizard`,
  `AI_POLL_MS` and (for any remaining internal reference)
  `_AiDialog`/`_ModalToolDialog`
- [Settings Mixin](app_settings.md) — `_open_key_wizard`/
  `_ensure_ai_key` open `AiKeyWizard` by its imported name
  (`from .dialogs import AiKeyWizard`); `_new_collection_ai` opens the
  [Sheet Generator Panel](sheetgen_panel.md) instead (faza 4)
- `gui.api_panel.ApiImageGenPanel._arm_probe_poll` and
  `gui.doc_window.DocWindow._arm_fix_poll` — both reach `AI_POLL_MS`
  through a deferred `import gui` rather than importing this module
  directly (see Design Decisions)

## Classes
### `_ModalToolDialog`
See the Purpose section above.

### `_AiDialog`
See the Purpose section above.

### AiKeyWizard
See the Purpose section above.

## Design Decisions
**Why `AI_POLL_MS` didn't stay in `gui/__init__.py`.** The prior step
(`gui.api_panel`) left it behind specifically because `_AiDialog` (its
only OTHER reader at the time) hadn't moved yet — moving it then would
have just relocated the same circular-import problem onto
`ApiImageGenPanel`. Now that `_AiDialog` itself has moved, the constant
follows its real owner into `gui.dialogs`. `gui.api_panel` and
`gui.doc_window` (`DocWindow`'s own unrelated Fixer poll) both keep
reaching it via a deferred `import gui; gui.AI_POLL_MS` — the same
late-binding idiom `gui.theme._pkg()` established — rather than a
real-path `from .dialogs import AI_POLL_MS`, since `gui.doc_window`
would then be circular with `gui.dialogs` (which imports `DocWindow`
FROM `gui.doc_window`).
