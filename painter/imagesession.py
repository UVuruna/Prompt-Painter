#!/usr/bin/env python3
"""DECODE ONCE, ENCODE ONCE for a chain of in-place image steps.

THE PROBLEM (owner decree 2026-08-07 — "svaku milisekundu ćemo ako
možemo"; root CLAUDE.md Priority A, Performance). Every post-save step —
``postprocess.remove_background``, ``postprocess.crop_transparent``,
``aspect.change_aspect``, ``upscale`` — takes a PATH: it opens the file,
transforms the pixels, and writes a full PNG back. Chained, each step
therefore re-decodes what the previous one just encoded. On the owner's
1664x2550 plate one such round trip measured **1.46 s** (0.08 s decode +
1.38 s encode) against ~0.3 s of actual pixel work, so a BG -> Crop ->
Aspect run spent ~2.9 s per image encoding bytes nobody ever looks at.

THE FIX. A thread-local SESSION that sits between the steps and the
disk:

* ``load(path)``   — the decoded image, from the session when the last
                     step left one there, otherwise off disk.
* ``store(path, img)`` — hand the result BACK to the session. Inside a
                     session this only marks it dirty; outside one it
                     writes immediately.
* ``flush()``      — write the dirty image, once.
* ``invalidate()`` — the file changed under us (an external tool wrote
                     it); drop the cache so the next ``load`` re-reads.

THREAD-LOCAL, not global: ChatGPT and Gemini run as parallel worker
THREADS over their own images, and one site's half-finished image must
never be visible to the other. Each thread gets its own session or none.

OUTSIDE A SESSION EVERYTHING BEHAVES EXACTLY AS BEFORE — ``load`` reads
the file, ``store`` writes it. That is what keeps the four standalone
tool jobs, the CLI and every existing test byte-identical: only a caller
that deliberately opens a session (``gui.logic._run_pipeline_steps``)
gets the chaining, and it flushes before anything else may look at the
file on disk.

WHAT THIS DOES NOT DO. When the owner keeps every pipeline step
(``keep_all_steps``, default ON) the intermediate bytes are the FEATURE
— each step's pre-state is a real restore point on disk — so the runner
flushes before each backup and the encode count is unchanged; the saved
decodes remain. With that toggle off, N steps collapse to ONE encode.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

try:
    from painter.config import PNG_SAVE_KWARGS
except ImportError:  # standalone: script's own dir is on sys.path
    from config import PNG_SAVE_KWARGS  # type: ignore[no-redef]

_local = threading.local()


class _Session:
    """One chain's in-flight image. At most ONE path is ever cached: a
    pipeline works on a single file at a time, and holding more would
    only risk serving a stale image for some other path."""

    __slots__ = ("path", "img", "dirty")

    def __init__(self) -> None:
        self.path: Path | None = None
        self.img: Image.Image | None = None
        self.dirty = False

    def holds(self, path: Path) -> bool:
        return self.img is not None and self.path == path

    def flush(self) -> None:
        if self.dirty and self.img is not None and self.path is not None:
            self.img.save(self.path, "PNG", **PNG_SAVE_KWARGS)
            self.dirty = False

    def drop(self) -> None:
        self.path = None
        self.img = None
        self.dirty = False


def _current() -> _Session | None:
    return getattr(_local, "session", None)


@contextmanager
def session():
    """Chain every ``load``/``store`` in this thread through ONE decoded
    image, written once on exit.

    Nests safely: an inner session restores the outer one afterwards.
    The image is flushed on the way out EVEN IF the body raised, because
    a step that failed halfway must not silently discard the work of the
    steps that already succeeded — the file on disk stays the truth."""
    previous = _current()
    if previous is not None:
        previous.flush()  # the outer chain's state must be on disk first
    current = _Session()
    _local.session = current
    try:
        yield current
    finally:
        try:
            current.flush()
        finally:
            _local.session = previous


def load(path: Path) -> Image.Image:
    """The decoded RGBA-capable image at ``path``.

    Inside a session this is the image the previous step stored, with no
    decode at all. The caller must NOT close the returned image or use
    it as a context manager — the session owns its lifetime (outside a
    session the image is freshly opened and the caller may do as it
    likes, but not closing it is always safe: it is dropped with the
    last reference)."""
    current = _current()
    if current is not None and current.holds(path):
        return current.img  # type: ignore[return-value]
    img = Image.open(path)
    img.load()  # decode NOW: the file handle must not outlive this call
    if current is not None:
        current.flush()      # a different path was in flight — write it
        current.path = path
        current.img = img
        current.dirty = False
    return img


def store(path: Path, img: Image.Image) -> None:
    """Hand a step's RESULT back.

    Inside a session: cached and marked dirty, written by ``flush``.
    Outside one: written straight through, exactly as the step used to
    do itself."""
    current = _current()
    if current is None:
        img.save(path, "PNG", **PNG_SAVE_KWARGS)
        return
    if current.path is not None and current.path != path:
        current.flush()
    current.path = path
    current.img = img
    current.dirty = True


def flush() -> None:
    """Write the in-flight image now — call before ANYTHING else reads
    the file from disk (a JobTemp backup, an external upscaler binary,
    a size check by another process)."""
    current = _current()
    if current is not None:
        current.flush()


def invalidate() -> None:
    """Forget the cached image: the file on disk was replaced by
    something other than ``store`` (the Real-ESRGAN binary writes its
    own output), so the next ``load`` must re-read it."""
    current = _current()
    if current is not None:
        current.drop()
