"""CDP driver — drives the owner's already-open, logged-in tab.

Chrome runs with ``--remote-debugging-port=9222`` (the launcher opens it
with the dedicated automation profile); the driver attaches over CDP and
works the DOM. No Download clicks: when the generated <img> appears, its
bytes are read straight from the DOM (fetch inside the page, base64
back) — the tool names and saves files itself.

Every DOM hook comes from the site's config block; when no fallback
selector matches, the driver fails LOUDLY (``SelectorRot``) instead of
guessing. Quota/refusal responses are TERMINAL (``TerminalState``) —
reported and stopped, never blind-retried.

**Composed from five responsibility mixins** (audit
``docs/AUDIT-OOP-2026-08-18.md`` → R4, owner pre-approved 2026-07-30 —
the file had reached 1,599 lines with five unrelated jobs in it). It
mirrors ``gui/app.py``'s proven ``PainterGui`` arrangement: ``SiteDriver``
is MRO glue and contributes no code of its own; every method it exposes
is defined on exactly one mixin, and ``DriverLifecycleMixin`` is the ONLY
one with an ``__init__`` — the other four run on the attributes it sets.

| Module | Owns |
|--------|------|
| [`lifecycle`](lifecycle.py) | attach / adopt the tab, wait for login, close, selector plumbing |
| [`protocol`](protocol.py) | one prompt into the composer, provably sent |
| [`wait`](wait.py) | the turn-based done edge, the F1b anchor, the image bytes |
| [`recovery`](recovery.py) | one rung of the recovery ladder (retry / refresh / re-send / new chat) |
| [`classify`](classify.py) | page text → a typed error (refusal, degrade, image-failed) |
| [`errors`](errors.py) | the typed error vocabulary |
| [`values`](values.py) | the pure, page-free value types and helpers |

This module re-exports the FULL public API so every existing
``from painter.driver import X`` call site keeps working unchanged. It IS
the package's public interface, not a temporary bridge — the same
arrangement (and the same reasoning) as ``painter/config/__init__.py``.
"""

from __future__ import annotations

from .classify import DriverClassifyMixin
from .errors import (
    AttachNotConfigured,
    DriverError,
    GenerationTimeout,
    ImageGenFailed,
    ItemRefused,
    ModelDegraded,
    NoImage,
    SelectorRot,
    SendNotConfirmed,
    SendVanished,
    TerminalState,
)
from .lifecycle import DriverLifecycleMixin
from .protocol import DriverProtocolMixin
from .recovery import DriverRecoveryMixin
from .values import Baseline, normalize_text, sniff_format
from .wait import DriverWaitMixin


class SiteDriver(
    DriverLifecycleMixin, DriverProtocolMixin, DriverWaitMixin,
    DriverRecoveryMixin, DriverClassifyMixin,
):
    """One attached tab of one site, driven through its config block —
    see the five mixins above for what each part actually does."""
