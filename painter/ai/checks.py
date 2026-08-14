"""The image CHECKER's own logic (owner's #3) — split out of the
single-file ``painter/ai.py`` (root Rule #20, 2026-07-30).

The checker's response format and the fix prompt built from it
(``parse_check_response``/``fix_note``/``build_fix_prompt``), the
per-image driver the GUI worker loops over (``check_one_image``, which
pairs one vision call with the [Flag Memory](flags.md)), and the two
resend helpers: ``drop_and_site_for`` reverses ``config.dest_for`` so
a flagged image can be re-sent to the SITE that generated it, and
``plan_resend`` turns a flag list into that plan.
"""

from __future__ import annotations

import re
import time
from pathlib import Path, PurePosixPath

from painter.config import (
    AI_FIX_NOTE,
    AI_FIX_PROMPT_NO_DEFECTS,
    AI_FIX_PROMPT_RAW_SUFFIX,
    AI_FIX_PROMPT_WITH_DEFECTS,
    SITES,
)

from .client import AiError, check_image, model_for
from .flags import clear_flag, flag_key, record_flag




def parse_check_response(text: str) -> list[str]:
    """The checker's strict format -> the defect list ([] = clean).

    'OK' (alone on the first line, any case, trailing '.' tolerated)
    means clean; 'DEFECTS:' followed by dash lines lists them. Any
    OTHER shape is a malformed model answer — loud, never guessed.
    """
    body = text.strip()
    if not body:
        raise AiError("empty check response")
    first, _, rest = body.partition("\n")
    head = first.strip().rstrip(".").upper()
    if head == "OK":
        return []
    if head.startswith("DEFECTS"):
        defects = [
            stripped
            for line in rest.splitlines()
            if (stripped := line.strip().lstrip("-*• ").strip())
        ]
        if not defects:
            # everything on the header line: "DEFECTS: subject cut"
            after = first.split(":", 1)[1].strip() if ":" in first else ""
            if after:
                return [after]
            raise AiError(
                f"check response names no defects: {body[:120]!r}"
            )
        return defects
    raise AiError(f"unexpected check response: {body[:120]!r}")


def fix_note(defects: list[str]) -> str:
    """The per-item extra suffix for a re-sent flagged image."""
    return AI_FIX_NOTE.format(defects="; ".join(defects))


def build_fix_prompt(defects: list[str], raw: str | None = None) -> str:
    """The Fixer AI's instruction (GUI rework Phase 20, owner's
    UV/prompt.txt item 2: "u oba slucaja kreira PROMPT koji salje uz
    sliku") — turns one checked image's parsed defect list (+ its
    VERBATIM raw response, for extra context the parsed bullets can
    lose) into the text sent ALONGSIDE the flagged image. PURE: no I/O,
    no network — offline-testable.

    Shared by every fixer surface (Rule #5, one prompt-builder instead
    of several near-copies): the manual IMAGE FIX / WEBSITE FIX buttons
    in the checker's report viewer (both call ``ai.edit_image``/
    ``driver.submit_with_image`` with THIS text) and the API-mode
    auto-fixer (``PainterGui._run_fixer_api``).

    An EMPTY ``defects`` list still returns a sensible, non-blank
    instruction (``AI_FIX_PROMPT_NO_DEFECTS``) rather than raising or
    returning "" — ``edit_image``/``submit_with_image`` always need SOME
    instruction text, and this function stays honest about ANY input
    regardless of whether the caller already gates on defects existing
    (root Rule #1: never assume an upstream gate held). ``raw`` — when
    given and non-blank — is appended VERBATIM after the instruction,
    never in place of it (the parsed bullets are the actionable part;
    the raw response is grounding context alongside them).
    """
    if defects:
        bullets = "\n".join(f"- {d}" for d in defects)
        instruction = AI_FIX_PROMPT_WITH_DEFECTS.format(bullets=bullets)
    else:
        instruction = AI_FIX_PROMPT_NO_DEFECTS
    if raw and raw.strip():
        instruction += AI_FIX_PROMPT_RAW_SUFFIX.format(raw=raw.strip())
    return instruction


def check_one_image(
    src: Path,
    out_base: Path,
    instructions: str,
    *,
    prompt: str | None = None,
    model: str | None = None,
    log=print,
    check=None,
) -> dict:
    """Drive ONE image through the vision checker and the flag memory —
    the pure core the GUI worker loops over (Rule #5, and offline-
    testable: ``check`` defaults to ``client.check_image``, so a
    test injects a per-image mock).

    ``model=None`` resolves via ``model_for("vision")`` (F5) BEFORE
    the call, not left for ``check_image`` to default itself — the
    RESOLVED name is what ``record_flag`` persists, so a flag entry
    never stores the literal string "None".

    ``prompt`` (F6, REWORK.md) passes straight through to ``check`` —
    ``None`` (the default) is NOT forwarded at all, so an older/simpler
    ``check`` double with no ``prompt`` parameter of its own (existing
    tests, callers) keeps working unchanged; only a caller that actually
    supplies a prompt needs ``check`` to accept it.

    Times the call, parses the strict OK/DEFECTS answer, MERGES a flag
    (or CLEARS a fixed image's old flag) and returns the row the panel
    renders — the flag ``key`` (``flag_key``, which ``flag_file``
    reverses back to THIS exact file), the ``kind``
    ('flagged'/'ok'/'error'), the parsed ``defects``, the VERBATIM
    ``raw`` model text and the elapsed ``time`` seconds. A per-image
    ``AiError`` (HTTP after the retries, or a malformed answer) is
    CAUGHT and returned as an 'error' row — loud in the log, never
    fatal (the tool-job convention); ``raw`` then carries the model's
    answer when we got one (a parse failure) or the error text (a
    network/HTTP failure), so the viewer always shows what happened."""
    check = check or check_image
    model = model or model_for("vision")
    key = flag_key(src, out_base)
    t0 = time.monotonic()
    raw: str | None = None
    call_kwargs = {"model": model, "log": log}
    if prompt is not None:
        call_kwargs["prompt"] = prompt
    try:
        raw = check(src, instructions, **call_kwargs)
        defects = parse_check_response(raw)
    except AiError as exc:
        op_s = time.monotonic() - t0
        log(f"FAIL {Path(src).name}: {exc}")
        return {
            "rel": key, "kind": "error", "defects": [],
            "raw": raw if raw is not None else str(exc), "time": op_s,
        }
    op_s = time.monotonic() - t0
    if defects:
        record_flag(out_base, src, defects, model, raw, log)
        log(f"FLAGGED {Path(src).name}: {'; '.join(defects)}")
        return {
            "rel": key, "kind": "flagged", "defects": defects,
            "raw": raw, "time": op_s,
        }
    clear_flag(out_base, src, log)  # a fixed image loses its stale flag
    return {"rel": key, "kind": "ok", "defects": [], "raw": raw, "time": op_s}


def drop_and_site_for(rel: str) -> tuple[str, str] | None:
    """Reverse ``config.dest_for``: the (drop_path, site) one
    out-relative save path came from.

    ``<rest>/<File>[_vN]_<sfx>.png`` -> ``('<rest>/<File>.png', site)``
    — the exact inverse of ``dest_for``: drop the generator suffix,
    drop a ``_vN`` (the ticked-redo output, owner 2026-07-27, reverses
    to the SAME canonical drop as its master, so a flagged version
    re-sends through the sheet entry it came from), and KEEP the rest
    of the path untouched. No root is re-attached: the sheet's path is
    the path (owner decree 2026-08-14) — pasting ``assets/`` back on
    was the same wrong assumption as stripping it. The
    pre-RESTRUCTURE ``<category>/<site>/<rest>`` and legacy
    ``<site>/<drop>`` layouts still reverse for old out/ trees.
    ``None`` when nothing names a site (an absolute flag key, or a
    folder that was never a generator output).
    """
    from painter.config import SITE_FILE_SUFFIX

    parts = PurePosixPath(rel).parts
    if parts:
        name = parts[-1]
        stem, dot, ext = name.rpartition(".")
        core = stem if dot else name
        for site, sfx in SITE_FILE_SUFFIX.items():
            if core.endswith(sfx) and len(core) > len(sfx):
                bare = core[: -len(sfx)]
                version = re.fullmatch(r"(.+)_v\d*", bare)
                if version is not None:
                    bare = version.group(1)
                bare += f".{ext}" if dot else ""
                return "/".join((*parts[:-1], bare)), site
    if len(parts) >= 3 and parts[1] in SITES:
        return "/".join((parts[0], *parts[2:])), parts[1]
    if len(parts) >= 2 and parts[0] in SITES:
        return "/".join(parts[1:]), parts[0]
    return None


def plan_resend(
    flagged: dict[str, list[str]],
    drop_to_source: dict[str, str],
) -> tuple[dict, dict, list[tuple[str, str]]]:
    """The re-send plan for a batch of flagged images (owner's #3).

    ``flagged`` maps a FLAG KEY to its defect list; ``drop_to_source``
    maps every QUEUED item's drop path to its sheet source (str).
    Returns ``(plans, notes, unmatched)``:

    * ``plans[site][source]`` — the drop-path set that site must run
      (the ``only=`` regenerate selection, grouped per sheet);
    * ``notes[site][drop]`` — the per-item fix note
      (``run_sheet``'s ``extra_suffix``);
    * ``unmatched`` — ``(flag key, reason)`` pairs the caller reports
      LOUDLY: the path names no site, or no queued collection carries
      the reversed drop path.
    """
    plans: dict[str, dict[str, set]] = {}
    notes: dict[str, dict[str, str]] = {}
    unmatched: list[tuple[str, str]] = []
    for key, defects in flagged.items():
        mapped = drop_and_site_for(key)
        if mapped is None:
            unmatched.append((key, "no site in the path"))
            continue
        drop, site = mapped
        source = drop_to_source.get(drop)
        if source is None:
            unmatched.append((key, "not in any queued collection"))
            continue
        plans.setdefault(site, {}).setdefault(source, set()).add(drop)
        notes.setdefault(site, {})[drop] = fix_note(defects)
    return plans, notes, unmatched
