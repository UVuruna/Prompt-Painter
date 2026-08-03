# Model Picker Row

**Script:** [Model Picker Row (script)](../model_picker.py)

## Purpose
`ModelPickerRow` — one purpose's Gemini-model picker (faza 4, owner
2026-08-03, UV tačka 5: "podešavanje za TEXT GEN i IMAGE CHECK tamo
ko to KORISTI"): the reusable "Refresh models → capable dropdown →
curated hint → persist the pick" row. The AI Check panel hosts the
VISION purpose, the New Collection (AI) panel the TEXT purpose; the
API panel keeps its own specialized Image picker (it composes with
the access gate and the "show all (debug)" switch — a documented
divergence, see [API Panel](api_panel.md)).

Behaviorally identical to the API panel's F5 plumbing: discovery on a
background thread (private queue + `self.after` poll); the dropdown
lists only purpose-CAPABLE models (`ai.capable_models`); the combo
preselects via `CTkComboBox.set()` (which does NOT fire `command`),
so only a GENUINE user pick persists to settings.json's
`MODELS_SETTING`; every pick refreshes the curated one-line hint
(`config.model_hint` — honest UNKNOWN for anything uncurated). The
hint seeds at build from `model_for(purpose)` so the row is honest
before any discovery. The picked name is informational — the actual
run always resolves via `ai.model_for(purpose)`, which reads the SAME
override this row writes.

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `painter.ai`
  (`list_models`/`capable_models`/`recommend_model`/`model_for`,
  lazy), `config` (`MODELS_SETTING`, `model_hint`),
  `painter.settings` (the override round-trip)
- [Themed Widget Toolkit](widgets.md) — `rounded_button`/
  `rounded_combo`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `ModelPickerRow`
- [Image Checker Panel](../tool_panels/__about/image_checker.md) —
  the VISION purpose row
- [Sheet Generator Panel](sheetgen_panel.md) — the TEXT purpose row

## Classes

### ModelPickerRow
See Purpose above. Public surface: `model_var` (the picked name).

## Design Decisions
- **Purpose-scoped, one row per host panel** — the F5 "one picker
  configures three purposes" row on the API panel confused the owner
  (UV tačka 5); each purpose now lives beside the feature that spends
  it, reading/writing the same `MODELS_SETTING` override as before —
  no migration needed, the settings shape never changed.
