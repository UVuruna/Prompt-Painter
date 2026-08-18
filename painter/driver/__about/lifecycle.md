# Driver Lifecycle

**Script:** [Driver Lifecycle (script)](../lifecycle.py) ·
**Folder:** [driver/](../___driver.md)

## Purpose
The attached tab: connect over CDP, adopt (or open) the site's tab, wait
out a login, close — plus the selector plumbing (`_query`/`_require`)
that turns a config block's fallback tuple into a locator.

This is the ONLY mixin with an `__init__`; the other four run on the
attributes it sets, via `self.` (the same arrangement `gui/app.py`'s
`BuildMixin` already has for `PainterGui`).

`attach()` finds the tab by URL fragment — several tabs -> the last one;
a MISSING tab is opened by the driver itself, since the caller has
already ensured Chrome via [Chrome Launcher](../../__about/chrome.md)'s
`ensure_chrome`. `wait_for_login()` polls for the composer while the
owner logs in by hand (status every 15 s, loud after
`login_wait_timeout_s`). `close()` detaches and NEVER closes the owner's
browser.

All required-element lookups poll up to the selector timeout before
failing loudly — SPAs morph elements a beat after input events.

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) — `SiteConfig`, `Timing`
- [Driver Errors](errors.md) — `SelectorRot`, `DriverError`
- [Driver Values](values.md) — `Baseline` (the `__init__` state)
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [CDP Driver — the package's public surface](__init__.md) — mixed into
  `SiteDriver`

## Classes

### DriverLifecycleMixin
`__init__`, `attach`, `wait_for_login`, `close`, `_query`, `_require`.
Never instantiated alone.
