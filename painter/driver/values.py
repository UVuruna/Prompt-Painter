"""The driver's PURE, page-free vocabulary — value types and helpers
that touch no Playwright object at all.

``Baseline`` is the pre-submit snapshot every ``await_done`` /
``extract_image`` judges against; ``normalize_text`` is the one text
normalisation every anchor comparison uses (the F1b prompt anchoring);
``sniff_format`` reads an image's magic bytes. Nothing here needs a
``Page``, which is exactly why they live apart from the five mixins:
they are importable, and testable, without a browser.

``painter/runner.py`` reads ``sniff_format`` from here through the
package's public surface.
"""

from __future__ import annotations

from dataclasses import dataclass


_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF8", "gif"),
    (b"RIFF", "webp"),  # RIFF....WEBP, checked further below
)

def normalize_text(text: str) -> str:
    """Whitespace-collapsed, lowercased text for DOM comparisons.

    ProseMirror/Quill editors reflow whitespace and newlines, so the
    F1 protocol's "does the composer / user turn hold OUR prompt"
    checks compare normalized forms, never raw strings."""
    return " ".join(text.split()).lower()


@dataclass(frozen=True)
class Baseline:
    """The page state snapshot taken BEFORE a submit (F1 protocol,
    owner 2026-07-29): everything after the send is judged RELATIVE to
    it — a result is accepted only from an assistant turn NEWER than
    ``turn_count``, holding an image whose src differs from
    ``last_img_src``. This is what makes "grab the last visible image"
    (root cause of the duplicate-save bug) impossible.

    ``user_turn_count`` (F1b, owner 2026-08-04) is the number of USER
    turns before the submit — our sent prompt must ADD one; when the
    count falls back to (or below) this value the site DROPPED our
    message (``SendVanished``).

    ``error_turn_count`` (owner 2026-08-11) is the number of the
    site's native thread-error turns before the submit — ChatGPT's
    "Something went wrong. Please try again." + Retry face renders
    INSIDE the user turn and creates NO assistant turn at all, so it
    is invisible to every other signal here; only a RISE above this
    count proves the error belongs to OUR send rather than to an
    earlier item still sitting in the chat."""

    turn_count: int
    last_img_src: str | None
    user_turn_count: int = 0
    error_turn_count: int = 0


def sniff_format(data: bytes) -> str | None:
    """Best-effort image format from magic bytes; None if unknown."""
    for magic, name in _MAGIC:
        if data.startswith(magic):
            if name == "webp" and data[8:12] != b"WEBP":
                continue
            return name
    return None
