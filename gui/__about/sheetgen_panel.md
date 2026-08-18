# Sheet Generator Panel

**Script:** [Sheet Generator Panel (script)](../sheetgen_panel.py)

## Purpose
`SheetGenPanel` — New Collection (AI) as a REAL setup panel (faza 4,
owner 2026-08-03, UV tačka 4 + predlog P2=A: the wizard ① Zahtev →
② Pitanja → ③ Draft & Save), replacing the retired `AiSheetDialog`
popup. Menu-hosted like every other functionality
(`PainterGui._tool_panels["ai_sheet_gen"]`, reached via
`_open_tool_panel`; `TILE_JOB_KINDS["ai_sheet_gen"]` stays `()` — no
dashboard job, its actions live inside the panel).

LEFT (the SETUP, visible through every step): the request text, where
the `.md` saves (default `SHEETS_DIR`), the TEXT-GEN
[Model Picker Row](model_picker.md) (moved HERE from the API panel —
owner: "podešavanje tamo ko to KORISTI") and **Ask questions** (the
Gemini-key gate runs on THIS action, not on opening the panel).
RIGHT (the working surface): ② the model's clarifying questions with
answer entries + **Generate sheet**; ③ the draft — EDITABLE — with
**Regenerate** / **Save .md** / **Save + Add to queue**. The step
indicator in the header accents the current step.

The ENGINE is unchanged (`painter.ai`: `contract_text` /
`ask_questions` / `generate_sheet` / `save_sheet` — the same two-call
flow + one automatic repair round the dialog drove); workers run on
background threads with the private queue + `self.after` poll
convention. Every worker result ENDS the busy state — `_show_questions`
clears it too (owner 2026-08-04: **Generate sheet** did nothing,
because `_busy` was still True from `_ask` and `_generate`'s first
line returns on it). **Save re-validates whatever is in the draft box with the
REAL parser** — problems are listed and BLOCK the save (the owner
fixes the draft right there; no DocWindow detour anymore); a clean
save lands under the picked folder and "+ Add to queue" also queues
it into the ONE shared Collections queue (faza 3 unified the
website/API queues, so the owner's "Website or API queue?" question
answers itself — both hosts render the same queue).

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`SHEETS_DIR`, `theme_pair`); `painter.ai` (lazy, in the workers);
  `painter.sheet_parser` (`parse_sheet` — the Save re-validation)
- [Model Picker Row](model_picker.md) — the TEXT purpose's picker
- [Worker Queue Poll](worker_poll.md) — `poll_worker_queue`, the
  shared loop behind `_arm_poll`
- [Icons](icons.md) — `icon("sheetgen")` (the header logo — its OWN
  mark since owner 2026-08-04; it used to share `ai.png` with the
  image checker, so nothing on screen told the two AI doors apart)
- [The Theme Engine](theme.md) — `skin_text` (the request/draft boxes)
- [Themed Widget Toolkit](widgets.md) — `rounded_button`/
  `rounded_entry`/`tk_font`
- `PainterGui` (duck-typed host) — `_ensure_ai_key`, the `_q` log
  queue, `add_generated_sheet`, `_scroll.refresh`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports
  `SheetGenPanel`
- [Build Mixin](app_build.md) — `_tool_panels["ai_sheet_gen"]`
- [Settings Mixin](app_settings.md) — `_new_collection_ai` opens this
  panel; the generic `tool_panels` round-trip persists `save_dir`
- [View Mixin](app_views.md) — `_tile_handler`/`_open_tool_panel`
  routing, same as every panel tile

## Classes

### SheetGenPanel
See Purpose above. Key methods: `_ask` (key-gated; FIRST call →
questions), `_show_questions`, `_generate` (SECOND call + repair
round), `_show_draft`, `_save(queue_it)` (parser-validated),
`get_settings`/`apply_settings` (the standard
`(stored, conditions=...)` shape — `conditions` unused, accepted for
the generic loop).

## Design Decisions
- **The draft is editable and Save re-validates.** The dialog's old
  failure path (DocWindow + manual copy/fix/re-add) collapsed into
  the panel itself: whatever is in the box goes through the REAL
  parser before touching disk — one loop, no detour, never a saved
  sheet that fails the contract.
- **No Start/Pause/Stop trio.** This panel runs no JOB_ORDER job —
  its two API calls are short, self-reporting actions; the generic
  running-view machinery treats it as a pure settings surface.
