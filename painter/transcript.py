"""The per-site AI RESPONSE TRANSCRIPT (owner 2026-08-11) — every text
the site answered, written down as it happened, so a NEW unknown
situation is diagnosed from the record instead of by re-provoking the
same failure live.

``Transcript`` appends ``<out>/_state/<site>/transcript.jsonl`` — one
JSON object per line, append-only, alongside the report txt (out of the
copy-ready tree). Each row carries the moment, the sheet + item, the
EVENT (refused / no_image / diagnosis / saved ...), the FULL raw
response text the driver read (``SiteDriver.last_response_text`` — the
exceptions truncate it, the transcript never does), the marker category
that matched (``matched: null`` = the site said something our
recognition system does not know — the rows new markers are mined
from), and what the runner did about it (``action``).

Writing is best-effort by design: a transcript line must NEVER kill a
run over a disk hiccup — failures are reported through the run log
(loud), then the run continues. That is deliberate scaling of No Error
Masking: the transcript is diagnostics ABOUT the run, not the run.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# a callable matching painter.runner.Log — kept structural (str -> None)
# to avoid importing the runner from this leaf module


class Transcript:
    """Append-only JSONL writer for one site's run transcript."""

    def __init__(self, path: Path):
        self.path = path

    def record(
        self,
        event: str,
        *,
        sheet: str = "",
        item: str = "",
        raw_text: str = "",
        matched: str | None = None,
        action: str = "",
        log=print,
    ) -> None:
        """Append one row; loud but NON-FATAL on any write failure."""
        row = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sheet": sheet,
            "item": item,
            "event": event,
            "raw_text": raw_text,
            "matched": matched,
            "action": action,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as exc:
            log(f"    TRANSCRIPT WRITE FAILED (run continues): {exc}")
