# Sheet Parser

**Script:** [Sheet Parser (script)](../sheet_parser.py) ·
**Flow:** [diagram](../__flow/sheet_parser.md)

## Purpose

Turns one prompt-sheet `.md` into the run queue. Pure and offline
(stdlib only), strict on the contract: what it cannot pair or place,
it reports loudly — the fix belongs in the sheet, never in parser
leniency.

## The contract it enforces

1. The `# H1` names the theme; a file without one raises
   `SheetError`.
2. An entry is a paragraph opening with a `**bold heading**` that
   carries `→ \`drop/path.png\`` — headings and paths may wrap
   across lines, plain text may sit between the bold span and the
   arrow, and the heading itself may contain single backticks.
   An arrow whose target is not an image file, or whose bold title
   ends with `:`, is prose (the weekday "Drop dirs" pointers).
2b. An entry may ALSO carry OPTIONAL input-image reference(s)
   (owner 2026-07-23; MULTI faza 2 2026-08-03): one or more
   `← \`refs/photo.png\`` lines in the same paragraph (mirror of the
   `→` output arrow), LINE ORDER = ATTACH ORDER (a dual plate's
   prompt says "the FIRST/SECOND attached image"). They fill
   `PromptItem.input_images` (a tuple of the RAW strings) — read-only
   source photos the runner attaches into the chat before the prompt,
   resolved on disk at run time (sheet folder → the run's Reference
   folder → absolute — `resolve_input_images`, which lives HERE (a
   sheet entry's references are a sheet concern); never touched
   here, the parser stays pure and offline). Any of
   `TOOL_IMAGE_EXTENSIONS` (png/jpg/jpeg/webp — a reference photo may
   be a jpg). A `←` on a real entry naming a non-image file is
   reported loudly (the entry keeps its other, valid refs).

## The legacy forms it also reads (best-effort, never loud)

The pre-convention sheets carry three older entry shapes; all
three LOAD, but their oddities (unpaired mentions, duplicate or
escaping paths — the REUSE pointers) are silently ignored instead
of reported, so old sheets never block a batch:

- **Heading entry** — `### Sun — Ancient of Days (\`file.png\`)`:
  a `##`/`###` heading carrying exactly ONE backticked image name.
- **Bold token** — `**Sun** — \`sun.png\``: the whole paragraph is
  the bold name plus one backticked image name.
- **Bare bold under a dir section** — `**Aries**` alone below
  `## SIGN look (\`assets/zodiac/astrology/sign/\`)`: the drop
  path becomes `sign/Aries.png`.

3. The FIRST fenced code block after the entry is the prompt,
   byte-identical.
4. Skip markers (`REUSE`, `SUPERSEDED`, `DO NOT GENERATE` —
   case-insensitive, only inside bold spans) are ADVICE: an entry
   that still carries a path + prompt loads as an item with
   `advice` set (default-unticked downstream); a standalone marked
   note or a marked section heading advises everything until the
   next heading; marked entries with no prompt become
   informational `SkippedItem`s.
5. Reported as problems: unpaired headings, drop paths that escape
   the out folder or name no image file, duplicate drop paths,
   unterminated fences, sheets with no entries at all.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`, `TOOL_IMAGE_EXTENSIONS` (the input-image
  reference accepts any of these)

### Used by
- [Run Loop](runner.md) — consumes `Sheet`
- [Main (Entry Point)](../../__about/main.md) — parses and reports
- [Sheet-Generator Flow](../ai/__about/sheet_flow.md) — validates
  every AI-produced sheet with the REAL contract rules
- [Tests (folder)](../../tests/___tests.md) — golden tests

## Classes

### PromptItem
One image to generate: `title`, `drop_path` (POSIX-relative, becomes
`out/<drop_path>`), `prompt` (byte-identical), `line`, `advice`
(the skip-marker text when the sheet advises against it, else None),
`input_images` (a tuple of the raw `← \`...\`` references in line
order — read-only source photos attached before the prompt, resolved
by the runner at run time; empty when the entry has no input lines).

### SkippedItem
A marked entry with NO prompt in the sheet (nothing to load):
`title`, `reason` (the marker span or section note), `line`.

### Problem
A contract violation: `message`, `line`.

### Sheet
The parse result: `theme`, `source`, `items`, `skipped`, `problems`.

### SheetError
Raised when the file is not a prompt sheet at all (no H1).

## Functions

- `parse_sheet(path) -> Sheet` — the only entry point.
