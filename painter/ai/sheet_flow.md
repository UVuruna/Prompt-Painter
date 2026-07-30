# Sheet-Generator Flow

**Script:** [Sheet-Generator Flow (script)](sheet_flow.py)

## Purpose
The owner's #2: turn a free-form request into a VALIDATED prompt sheet
— clarifying questions first, then the sheet itself, held to the real
contract and saved under `sheets/`. Split out of the single-file
`painter/ai.py` (root Rule #20, 2026-07-30).

## Connections

### Uses
- [Gemini REST Client](client.md) — `generate_text` (the default
  `gen`, resolved at CALL time so a test can inject its own)
- [Sheet Parser](../sheet_parser.md) — `parse_sheet`, the REAL
  contract validation
- [Config (subfolder)](../config/___config.md) — `AI_SHEET_SYSTEM`,
  `AI_QUESTIONS_SYSTEM`, `AI_REPAIR_PROMPT`, `AI_MAX_QUESTIONS`,
  `PROJECT_ROOT`

### Used by
- [AI (subfolder)](___ai.md) — `__init__.py` re-exports it
- [GUI](../../gui.md) — the New-collection (AI) dialog

## Functions

- `contract_text()` — `instructions.md` verbatim (both system
  prompts embed it).
- `ask_questions(request, contract, gen=None) -> list[str]` — the
  FIRST call (contract + "questions only"); parsed by
  `parse_questions` (numbered / bulleted lines, capped at
  `AI_MAX_QUESTIONS`; a poll-less answer returns `[]` and the
  caller generates directly).
- `generate_sheet(request, questions, answers, contract, work_dir,
  gen=None, log=print) -> (md, problems, theme)` — the SECOND call
  + at most ONE automatic repair round: the produced md (a
  whole-file code fence is unwrapped by `strip_md_fence`, inner
  prompt fences survive) is validated by `validate_sheet_md` with
  the REAL parser on a scratch file; problems are sent back once
  via `AI_REPAIR_PROMPT`. `problems == []` means loadable;
  otherwise the caller must NOT load the md (the GUI shows it for
  manual fixing).
- `save_sheet(md, theme, sheets_dir) -> Path` — writes a VALIDATED
  sheet under `sheets/` (created on demand) as
  `<slug_for(theme)>.md`, `_2`/`_3`… on collision.

## Design Decisions
- **Validation is the real parser.** The AI's sheet is held to the
  same contract as a hand-written one — `parse_sheet` on a scratch
  file, problems fed back for exactly ONE repair round, and a still
  broken sheet is NEVER loaded.
- **`gen` is resolved at call time, not bound as a default argument**
  — the tests inject a fake generator per call, and the flow never
  freezes a reference at import time.
