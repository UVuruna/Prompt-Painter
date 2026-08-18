# driver/

The CDP driver — it drives the owner's already-open, logged-in site tab.

Chrome runs with `--remote-debugging-port=9222` (see
[Chrome Launcher](../__about/chrome.md) for the dedicated automation
profile); the driver attaches with Playwright's `connect_over_cdp` — no
extension, no OCR, no virtual mice. It never clicks Download: the
generated image's bytes are fetched from the DOM (inside
`page.evaluate`) and handed back for the runner to save under the
sheet's own name.

Every DOM hook comes from the site's config block; when no fallback
selector matches, the driver fails LOUDLY (`SelectorRot`) instead of
guessing. Quota/refusal responses are TERMINAL (`TerminalState`) —
reported and stopped, never blind-retried.

**Composed from five responsibility mixins.** Was one 1,599-line
`painter/driver.py` carrying five unrelated jobs; split 2026-08-18
(audit [AUDIT-OOP-2026-08-18](../../docs/AUDIT-OOP-2026-08-18.md) → R4,
owner pre-approved 2026-07-30), mirroring `gui/app.py`'s proven
`PainterGui` arrangement. `SiteDriver` is MRO glue and contributes NO
code of its own; every method it exposes is defined on exactly one mixin,
and `DriverLifecycleMixin` is the ONLY one with an `__init__` — the other
four run on the attributes it sets, via `self.`.

`__init__.py` re-exports the FULL public API, so every existing
`from painter.driver import X` call site kept working UNCHANGED — the
same arrangement, and the same reasoning, as
[`painter/config/`](../config/___config.md).

## Files

| File | Tier | One line |
|------|------|----------|
| `__init__.py` | Standard | `SiteDriver`'s MRO glue + the full public-API re-export — [about](__about/__init__.md) |
| `errors.py` | Standard | the typed error vocabulary — what the runner catches — [about](__about/errors.md) |
| `values.py` | Standard | the PURE, page-free value types and helpers (`Baseline`, `normalize_text`, `sniff_format`) — [about](__about/values.md) |
| `lifecycle.py` | Standard | attach / adopt the tab, wait for login, close, selector plumbing; the one `__init__` — [about](__about/lifecycle.md) |
| `protocol.py` | Algorithmic | one prompt into the composer, provably sent — [about](__about/protocol.md) · [flow](__flow/protocol.md) |
| `wait.py` | Algorithmic | the turn-based done edge, the F1b anchor, the image bytes — [about](__about/wait.md) · [flow](__flow/wait.md) |
| `recovery.py` | Algorithmic | one rung of the recovery ladder (retry / re-send / refresh / new chat) — [about](__about/recovery.md) · [flow](__flow/recovery.md) |
| `classify.py` | Algorithmic | page text → a typed error (refusal, degrade, image-failed) — [about](__about/classify.md) · [flow](__flow/classify.md) |

## The split boundary

| Question | Module |
|----------|--------|
| How do I reach the page at all? | `lifecycle` |
| How does a prompt get IN, and how do I know it landed? | `protocol` |
| WHEN is the answer finished, and what are its bytes? | `wait` |
| What does this turn MEAN? | `classify` |
| The last step failed — what do I do about it, once? | `recovery` |

`wait` decides WHEN a turn is finished; `classify` decides WHAT it
means. Keeping those apart is the point: a quota wall must never be
blind-retried as if it were a timeout.

## Connections

### Uses
- [Config (subfolder)](../config/___config.md) — `SiteConfig`, `Timing`,
  `MIN_IMAGE_PX`, `SEND_RELOAD_RECOVERY`, `parse_quota_reset`
- Playwright (`playwright.sync_api`) — the CDP session

### Used by
- [Run Loop](../__about/runner.md) — the per-item protocol
- [Recovery Ladder](../__about/recovery.md) — which rung to climb next
- [Transcript](../__about/transcript.md) — `last_response_text`
- [Main (Entry Point)](../../__about/main.md) — the attach/close lifecycle
- `gui/app_jobs.py` and `gui/app_checker_fixer.py` — the GUI's run and
  fixer jobs ([GUI (folder)](../../gui/___gui.md))

## Tests

`tests/test_driver_protocol.py` · `tests/test_driver_wait.py` ·
`tests/test_driver_classify.py` · `tests/test_driver_recovery.py`, over
the shared fake Playwright surface in `tests/driver_fakes.py` — the
suite split alongside this package in the same commit (see
[tests/](../../tests/___tests.md)).
