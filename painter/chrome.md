# Chrome Launcher

**Script:** [Chrome Launcher (script)](chrome.py)

## Purpose
Guarantees an attach point: probes the CDP endpoint, and when
nothing answers, launches the automation Chrome itself — one tab
per requested site — and waits for the endpoint.

**Why a dedicated profile:** Chrome 136+ ignores
`--remote-debugging-port` on the DEFAULT user profile, so the
launcher runs Chrome with the project's own `chrome-profile/`
folder (gitignored). The owner logs in there ONCE (Google +
OpenAI); cookies persist, every later run is already logged in, and
his normal Chrome profile is never touched. The folder holds live
session cookies — treat it as a credential store.

## Connections

### Uses
- [Config (subfolder)](config/___config.md) — `CDP_PORT`, `CDP_URL`, `CHROME_CANDIDATES`,
  `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`

### Used by
- [Main (CLI)](../main.md) — pre-run guarantee
- [GUI](../gui.md) — the "Open Chrome (login)" button

## Functions

- `cdp_alive(cdp_url) -> bool` — does a debuggable Chrome answer?
- `find_chrome() -> Path` — first existing `CHROME_CANDIDATES`
  entry; `ChromeError` with instructions when none exist.
- `ensure_chrome(site_urls, cdp_url) -> str` — returns
  `'already-running'` or `'launched'`; raises `ChromeError` when
  the endpoint never answers after a launch.
