# Main (CLI)

**Script:** [Main (script)](main.py)

## Purpose
The single-site command-line entry point ([GUI](gui.md) is the
usual front door): parse the sheet, print the full report, refuse
contract-violating sheets, guarantee a debuggable Chrome, and hand
off to the run loop.

## Usage

```bash
# validate a sheet offline (no browser, no playwright needed)
python main.py "path/to/theme_prompts.md" --dry-run

# the supervised run; if no debuggable Chrome answers, the tool
# opens the automation Chrome itself (log in once, rerun)
python main.py "path/to/theme_prompts.md" --site gemini
```

Options: `--site {chatgpt,gemini}`, `--out DIR` (generation stages
at `<out>/_staging/<site>/`; approval moves images to
`<out>/<site>/<drop-path>`), `--background {auto,transparent,
white,none}`, `--approve-all` (skip the review phase for this
run), `--pause SECONDS`, `--cdp URL`, `--no-bgfix` (skip the
background remover), `--dry-run`.

Without `--approve-all` the run ends with the images STAGED; review
them in the GUI ("Review staged") or rerun with `--approve-all`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | clean run, clean dry-run, or "Chrome opened — log in, rerun" |
| 1 | driver/Chrome error — rerun to resume once fixed |
| 2 | sheet unreadable / violates the contract / bad arguments / bgfix deps missing |
| 3 | terminal site state (quota/refusal) — resume later |
| 130 | interrupted — progress saved |

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md)
- [Chrome Launcher](painter/chrome.md),
  [CDP Driver](painter/driver.md),
  [Postprocess](painter/postprocess.md) — imported lazily, so
  `--dry-run` works without playwright
- [Run Loop](painter/runner.md), [Review](painter/review.md)
- [Config](painter/config.md)
