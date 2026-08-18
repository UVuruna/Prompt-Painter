# Main (Entry Point)

**Script:** [Main (script)](../main.py) ·
**Flow:** [diagram](../__flow/main.md)

## Purpose

THE way into the application. With no arguments it opens the
[GUI](../gui/___gui.md); with one or more sheet arguments it is the
single-site CLI: parse the sheets, print each report, refuse
contract-violating sheets, guarantee a debuggable Chrome, and hand
off to the run loop.

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

Options: `--site {chatgpt,gemini}`, `--out DIR` (images save directly
at `<out>/<site>/<drop-path>`), `--background {transparent,white,none}`
(default: the site's own — transparent on ChatGPT, white on Gemini),
`--pause MIN [MAX]` (one value = fixed, two = a random range), `--cdp
URL`, `--no-bgfix` (skip the background remover), `--no-crop` (skip
the transparent autocrop), `--upscale` / `--no-upscale` (Real-ESRGAN
on small near-square badge images — default on; the three postprocess
steps compose into ONE `post_save` hook per the flags), `--no-report`
(skip the per-sheet report txt), `--new-chat
{collection,folder,never}` (default `collection`), `--safer-retry`
(one allegory-framed retry on a safety refusal), `--no-continue-nudge`
(suppress the ChatGPT stall nudge), `--dry-run`.

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
- [Sheet Parser](../painter/__about/sheet_parser.md)
- [Chrome Launcher](../painter/__about/chrome.md),
  [CDP Driver](../painter/driver/___driver.md),
  [Postprocess](../painter/__about/postprocess.md),
  [Upscale](../painter/__about/upscale.md) — imported lazily, so
  `--dry-run` works without playwright
- [Run Loop](../painter/__about/runner.md)
- [Config (subfolder)](../painter/config/___config.md)
- [GUI (folder)](../gui/___gui.md) — `import gui; gui.main()` when no
  sheet arguments are given

### Used by
- The owner, directly (`python main.py ...`) — no other module in the
  project imports `main.py`
