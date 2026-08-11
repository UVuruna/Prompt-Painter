# Recovery

**Script:** [Recovery (script)](../recovery.py)

## Purpose
The image-failure RECOVERY LADDER (BUG 3, owner 2026-07-21 +
escalation 2026-07-23) — its own responsibility, split out of
`painter/runner.py` on 2026-08-11 when the run loop crossed the
god-file line guard (THE STRUCTURE LAW). Moved whole: the ladder's
behavior is byte-identical to its pre-split runner home; only the
public names changed (`recover_image_failed`, `interruptible_sleep`).

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — the ladder's knobs
  (`IMAGE_FAILED_RETRY_MAX`, `IMAGE_FAILED_RETRY_DELAY_RANGE_S`,
  `IMAGE_FAILED_ESCALATION_DELAYS_S`, `IMAGE_RETRY_NUDGE`)
- [CDP Driver](driver.md) — `ImageGenFailed`, and the driver instance
  it drives (`click_error_retry`, `await_done`, `extract_image`,
  `refresh`, `new_chat`)

### Used by
- [Run Loop](runner.md) — the `ImageGenFailed` handler calls
  `recover_image_failed`; the paced `_pause` shares
  `interruptible_sleep`

## Functions

### interruptible_sleep(seconds, should_stop, log) -> bool
Sleep waking every half-second to honour Stop — the ladder's rounds
wait MINUTES (up to ~36), so a Stop must never hang behind them.
Returns True when Stop cut the wait short.

### recover_image_failed(exc, driver, generate_one, base, ...) -> (bytes, float)
Walk the ladder, cheapest rung first: ① the site's native Retry
button, ② paced `IMAGE_RETRY_NUDGE` resends, ③ escalation rounds
(wait → refresh → new session → resend the WHOLE prompt, re-attaching
input images). First rung that yields an image returns; every rung
spent re-raises `ImageGenFailed` — the worker STOPS (owner's "GASI"),
files on disk resume. Only `ImageGenFailed` is caught per rung; a
quota/refusal mid-recovery propagates loudly.

## Design Decisions
- **No import back into the runner.** The runner imports THIS module,
  never the reverse — the `Log`/`ShouldStop`/`OnEvent` aliases are
  duplicated locally to keep the dependency one-way.
- **Tests patch the knobs HERE.** The runner suites' autouse
  `_fast_recovery` fixtures zero the waits on `painter.recovery`'s
  copies (they moved with the code).
