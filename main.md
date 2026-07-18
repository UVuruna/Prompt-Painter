# Main (Entry Point)

**Script:** [Main (script)](main.py)

## Purpose
THE way into the application. With no arguments it opens the
[GUI](gui.md); with a sheet argument it is the single-site CLI:
parse the sheet, print the full report, refuse contract-violating
sheets, guarantee a debuggable Chrome, and hand off to the run
loop.

## Usage

```bash
# the front door — opens the GUI
python main.py

# validate sheets offline (no browser, no playwright needed)
python main.py "path/to/theme_prompts.md" --dry-run

# the supervised single-site run over one or more sheets, in order;
# if no debuggable Chrome answers, the tool opens the automation
# Chrome itself (log in once, rerun)
python main.py sheet1.md sheet2.md --site gemini
```

Options: `--site {chatgpt,gemini}`, `--out DIR` (images save
directly at `<out>/<site>/<drop-path>`), `--background
{transparent,white,none}` (default: the site's own — transparent
on ChatGPT, white on Gemini; Gemini's three laws always ride
along), `--pause MIN [MAX]` (one value = fixed, two = a random
range), `--cdp URL`, `--no-bgfix` (skip the background remover),
`--no-crop` (skip the transparent autocrop), `--upscale` /
`--no-upscale` (Real-ESRGAN on small near-square badge images —
default on; the three postprocess steps compose into ONE
`post_save` hook per the flags), `--no-report` (skip the per-theme
report txt), `--safer-retry` (one allegory-framed retry on a
safety refusal), `--dry-run`.

Broken sheets are reported and skipped; the rest run. Sheets are
driven in the given order — each closes fully (images + progress +
report) before the next starts, so a quota stop costs nothing.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | clean run, clean dry-run, or "Chrome opened — log in, rerun" |
| 1 | driver/Chrome error — rerun to resume once fixed |
| 2 | a sheet was skipped (unreadable/contract) / bad arguments / postprocess deps missing |
| 3 | terminal site state (quota) — resume later; the parsed quota reset time is printed when the site named one |
| 130 | interrupted — progress saved |

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md)
- [Chrome Launcher](painter/chrome.md),
  [CDP Driver](painter/driver.md),
  [Postprocess](painter/postprocess.md),
  [Upscale](painter/upscale.md) — imported lazily, so `--dry-run`
  works without playwright
- [Run Loop](painter/runner.md)
- [Config](painter/config.md)
