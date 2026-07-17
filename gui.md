# GUI

**Script:** [GUI (script)](gui.py)

## Purpose
The owner's front door — a small tkinter window over the same
engine the CLI uses. Nothing more than the workflow needs: pick the
sheet, pick the output folder, tick the sites, open Chrome, check,
start, stop.

## The window

- **Sheet / Output** — file and folder pickers.
- **Sites** — Gemini / ChatGPT checkboxes; both ticked = both run
  IN PARALLEL, one thread and one tab each, each at its own pace.
- **Background fix** — runs the DOMY tool after every save
  (unticking skips it; the dependency check runs before start).
- **Pause** — seconds between prompts per site.
- **Open Chrome (login)** — launches the automation Chrome with
  one tab per ticked site (dedicated `chrome-profile/`; log in
  once, sessions persist). With Chrome already answering on CDP it
  just reports ready.
- **Check sheet** — the dry-run report (items, skips, problems)
  into the log; a sheet with problems refuses to start.
- **Start / Stop** — Stop is graceful: each site finishes its
  current item, progress is already saved, nothing is lost.
- **Log** — both sites interleaved with `[gemini]` / `[chatgpt]`
  prefixes; terminal states and driver errors land here loudly.

## Threading
One worker thread per site; each creates its own Playwright
instance and `SiteDriver` (sync Playwright is per-thread). Workers
talk to the window only through a queue drained on the tk timer —
no widget is ever touched from a worker.

## Connections

### Uses
- [Sheet Parser](painter/sheet_parser.md), [CDP Driver](painter/driver.md),
  [Run Loop](painter/runner.md), [Chrome Launcher](painter/chrome.md),
  [Postprocess](painter/postprocess.md), [Config](painter/config.md)

### Used by
- The owner (`python gui.py`).
