# Sheet Parser

**Script:** [Sheet Parser (script)](sheet_parser.py)

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
3. The FIRST fenced code block after the entry is the prompt,
   byte-identical.
4. Skip markers (`REUSE`, `SUPERSEDED`, `DO NOT GENERATE` —
   case-insensitive, only inside bold spans) mark one entry, poison
   the rest of a section (a standalone marked note), or skip a whole
   marked section heading.
5. Reported as problems: unpaired headings, drop paths that escape
   the out folder or name no image file, duplicate drop paths,
   unterminated fences, sheets with no entries at all.

## Connections

### Uses
- [Config](config.md) — `IMAGE_EXTENSIONS`, `SKIP_MARKER_PATTERN`

### Used by
- [Run Loop](runner.md) — consumes `Sheet`
- [Main (CLI)](../main.md) — parses and reports
- [Tests (folder)](../tests/___tests.md) — golden tests

## Classes

### PromptItem
One image to generate: `title`, `drop_path` (POSIX-relative, becomes
`out/<drop_path>`), `prompt` (byte-identical), `line`.

### SkippedItem
An entry the sheet marks as not-to-generate: `title`, `reason` (the
marker span or section note), `line`.

### Problem
A contract violation: `message`, `line`.

### Sheet
The parse result: `theme`, `source`, `items`, `skipped`, `problems`.

### SheetError
Raised when the file is not a prompt sheet at all (no H1).

## Functions

- `parse_sheet(path) -> Sheet` — the only entry point.
