# Driver Recovery

**Script:** [Driver Recovery (script)](../recovery.py) ·
**Flow:** [diagram](../__flow/recovery.md) ·
**Folder:** [driver/](../___driver.md)

## Purpose
One rung of the recovery ladder at a time. Each rung is a separate
public step so the RUNNER decides how far to climb
([Recovery Ladder](../../__about/recovery.md) owns that policy); this
mixin only knows how to perform one rung on the DOM.

3. `click_error_retry(log) -> bool` — the first rung of the recovery
   ladder: click the site's native Retry button
   (`image_error_retry_button`) if present; True when clicked. Never
   loud — a missing button is a normal branch.
4. `refresh(log)` — reload the page and wait for the composer back (a
   last-resort ladder rung); the login lives in the profile on disk. A
   composer that does not come back in time earns ONE more reload with
   a doubled budget (owner 2026-08-11, the 14:52:32 stop: a single slow
   reload ended a ChatGPT run at 38/69 collections) — a composer that
   is gone after that is still loud.
2b. `new_chat(log)` — clicks the sidebar's New-chat control and waits
   for the fresh composer; re-anchors the baseline to nothing (a fresh
   conversation restarts turn numbering).

`_retry_send()` re-sends the last confirmed prompt — the one try the
`SendVanished`/`SendNotConfirmed` handler is allowed.

## Connections

### Uses
- [Driver Errors](errors.md) — `DriverError`
- [Driver Values](values.md) — `Baseline` (a new chat re-anchors to
  nothing)

### Used by
- [CDP Driver — the package's public surface](__init__.md) — mixed into
  `SiteDriver`
- [Recovery Ladder](../../__about/recovery.md) — the policy that decides
  which rung to climb next

## Classes

### DriverRecoveryMixin
`new_chat`, `click_error_retry`, `refresh`, `_retry_send`. Never
instantiated alone.
