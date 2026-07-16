# Main (CLI)

**Script:** [Main (script)](main.py)

## Purpose
The entry point: parse the sheet, print the full report (items,
skips, problems), refuse contract-violating sheets, and — unless
`--dry-run` — attach over CDP and hand off to the run loop.

## Usage

```bash
# validate a sheet offline (no browser, no playwright needed)
python main.py "path/to/theme_prompts.md" --dry-run

# the supervised run (Chrome already started with
#   chrome.exe --remote-debugging-port=9222)
python main.py "path/to/theme_prompts.md" --site gemini
```

Options: `--site {chatgpt,gemini}`, `--out DIR`, `--pause SECONDS`,
`--cdp URL`, `--dry-run`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | clean run (or clean dry-run) |
| 1 | driver error — rerun to resume once fixed |
| 2 | sheet unreadable / violates the contract / bad arguments |
| 3 | terminal site state (quota/refusal) — resume later |
| 130 | interrupted — progress saved |

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md)
- [CDP Driver](painter/driver.md) — imported lazily, so `--dry-run`
  works without playwright
- [Run Loop](painter/runner.md)
- [Config](painter/config.md)
