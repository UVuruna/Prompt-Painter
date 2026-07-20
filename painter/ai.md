# AI Client & Flows

**Script:** [AI Client & Flows (script)](ai.py)

## Purpose

The engine behind the three AI features (owner 2026-07-20): a
MINIMAL Gemini REST client over `urllib` (no SDK, free AI Studio
key), the SHEET-GENERATOR flow helpers (clarifying questions →
final `.md` → real-parser validation + one repair round), and the
image checker's FLAG MEMORY (`<out>/_state/ai_flags.json`). All of
it is offline-testable: the HTTP layer is one monkeypatchable alias
(`_urlopen`) and the flow helpers take a `gen` callable resolved at
call time.

Loud failure taxonomy (Rule #1): every HTTP error, API refusal/block
and malformed response raises `AiError`; a missing key raises the
specific `NoKey`, which the GUI answers by AUTO-OPENING the guided
key wizard. Consecutive API calls are PACED `AI_CALL_PAUSE_S` apart
— the free tier allows roughly 10 requests/minute.

## Connections

### Uses
- [Config](config.md) — the whole `GEMINI_*` / `AI_*` block,
  `SITES`, `STATE_DIRNAME`, `PROJECT_ROOT`
- [Settings](settings.md) — `load_settings` (the key lives in
  `settings.json` under `gemini_api_key`)
- [Sheet Parser](sheet_parser.md) — `parse_sheet` validates every
  AI-produced sheet with the REAL contract rules

### Used by
- [GUI](../gui.md) — the key wizard's Test, the New-collection
  dialog, the AI-check job, the re-send mapping
- [Tests (folder)](../tests/___tests.md) — mocked-HTTP client tests,
  flow tests, flag round-trips

## Classes

### AiError
A Gemini API call failed — HTTP error, refusal/block or malformed
response. Loud; the CALLER decides whether one failure skips an
image (the checker's per-item convention) or stops a flow.

### NoKey
`AiError` subclass: `settings.json` holds no key. The GUI's
documented reaction is opening the guided wizard.

## Functions — the REST client

- `api_key() -> str` — the key from `settings.json`
  (`GEMINI_KEY_SETTING`); `NoKey` when absent/blank.
- `generate_text(prompt, system=None, *, key=None, model=...)` —
  one `models/<model>:generateContent` POST (key in the
  `x-goog-api-key` header, `systemInstruction` when given); returns
  the response text. `key=None` reads settings — the wizard's Test
  passes its candidate explicitly.
- `check_image(image_path, instructions, *, key=None, model=...)` —
  the vision call: the instructions text part + the image as
  base64 `inlineData` (png/jpg/webp by suffix).
- Response parsing tolerates the candidates/parts structure (empty
  candidates skipped, parts concatenated) and is LOUD on
  `promptFeedback.blockReason`, a non-STOP `finishReason` with no
  text, and any shape carrying no text.

## Functions — the sheet-generator flow (owner's #2)

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

## Functions — the checker + flag memory (owner's #3)

- `parse_check_response(text) -> list[str]` — the strict format:
  `OK` → `[]`; `DEFECTS:` + dash lines → the list; anything else is
  a loud `AiError` (never guessed).
- `fix_note(defects)` — the re-send's per-item extra suffix
  (`AI_FIX_NOTE`, "; "-joined defects).
- Flags file `<out>/_state/ai_flags.json`, atomic writes, keyed by
  `flag_key(image, out_base)` — the image's POSIX path RELATIVE to
  the out base (absolute when the image lives outside it; such keys
  persist but can never match a queued collection):
  `load_flags` / `save_flags` / `record_flag` (defects, checked_at,
  model, the file's mtime AT CHECK TIME) / `clear_flag` /
  `clear_flag_keys` / `prune_stale_flags` — the prune drops every
  entry whose file is gone or whose mtime changed (the image was
  REGENERATED), run before each check batch. A corrupt flags file
  is reported loudly and treated as empty (flags are derived data —
  a re-check rebuilds them).
- `drop_and_site_for(rel) -> (drop_path, site) | None` — the
  `config.dest_for` REVERSE: `<category>/<site>/<rest>` →
  `('assets/<category>/<rest>', site)`; legacy `<site>/<drop>` →
  `(drop, site)`; `None` when no segment names a site.
- `plan_resend(flagged, drop_to_source) -> (plans, notes,
  unmatched)` — the whole re-send plan, pure and GUI-free:
  `plans[site][sheet-source]` is the drop set that site runs
  (`only=`), `notes[site][drop]` each item's fix note
  (`extra_suffix`), `unmatched` the `(key, reason)` pairs the caller
  logs loudly (no site in the path / not in any queued collection).

## Design Decisions

- **No SDK.** The two calls the features need are one POST each;
  `urllib` keeps the dependency set unchanged and the HTTP layer
  mockable in one line.
- **Model names are config data** (`GEMINI_TEXT_MODEL`,
  `GEMINI_VISION_MODEL`) — Google rotates them; the owner bumps a
  string, not code.
- **Validation is the real parser.** The AI's sheet is held to the
  same contract as a hand-written one — `parse_sheet` on a scratch
  file, problems fed back for exactly ONE repair round, and a still
  broken sheet is NEVER loaded.
- **The flag mtime is the invalidation.** A regenerated image gets
  a new mtime, so its stale defects can never be asserted again —
  no separate bookkeeping when the re-send overwrites a file.
