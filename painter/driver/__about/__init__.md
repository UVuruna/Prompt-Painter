# CDP Driver — the package's public surface

**Script:** [CDP Driver (script)](../__init__.py) ·
**Folder:** [driver/](../___driver.md)

## Purpose
`SiteDriver`, composed from the package's five responsibility mixins,
plus the FULL public-API re-export so every existing
`from painter.driver import X` call site kept working UNCHANGED across
the split (audit `docs/AUDIT-OOP-2026-08-18.md` -> R4, owner pre-approved
2026-07-30 — the file had reached 1,599 lines with five unrelated jobs
in it).

That re-export IS this package's interface, not a temporary bridge — the
same arrangement, and the same reasoning, as
[`painter/config/__init__.py`](../../config/__about/__init__.md).

`SiteDriver` itself is MRO glue and contributes NO code of its own:
every method it exposes is defined on exactly one mixin, and
[`DriverLifecycleMixin`](lifecycle.md) is the ONLY one with an
`__init__` — the other four run on the attributes it sets, via `self.`.
It mirrors `gui/app.py`'s proven `PainterGui` arrangement.

Drives the open, logged-in site tab. Chrome runs with
`--remote-debugging-port=9222` (see [Chrome Launcher](../../__about/chrome.md) for
the dedicated automation profile); the driver attaches with
Playwright's `connect_over_cdp` — no extension, no OCR, no virtual
mice. It never clicks Download: the generated image's bytes are
fetched from the DOM (inside `page.evaluate`) and handed back for the
runner to save under the sheet's own name.

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) — `SiteConfig`,
  `Timing`, `MIN_IMAGE_PX`, `SEND_RELOAD_RECOVERY`
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [Run Loop](../../__about/runner.md) — per-item protocol
- [Main (Entry Point)](../../../__about/main.md) — attach/close lifecycle

## Classes

### SiteDriver
`attach()` (find the tab by URL fragment; several tabs → the last
one; a MISSING tab is opened by the driver itself — the caller has
already ensured Chrome via [Chrome Launcher](../../__about/chrome.md)'s
`ensure_chrome`), `wait_for_login()` (poll for the composer while the
owner logs in by hand — status every 15 s, loud after
`login_wait_timeout_s`), `submit_prompt()`, `submit_with_image()`
(image + text, GATED by `attach_menu_path`), `await_done()`,
`extract_image()`, `close()` (detaches; never closes the owner's
browser).
