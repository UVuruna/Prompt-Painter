"""Gemini API client + the AI features' engine (owner 2026-07-20).

Three cohesive parts, all offline-testable with a mocked HTTP layer
(the tests monkeypatch ``_urlopen`` — no SDK, no live calls):

* the MINIMAL REST CLIENT over urllib against the free AI Studio key:
  ``generate_text`` and ``check_image`` POST ``v1beta
  models/<model>:generateContent`` with the key in the
  ``x-goog-api-key`` header. Every HTTP error, refusal/block and
  malformed response raises a loud ``AiError`` (Rule #1); a missing
  key raises the specific ``NoKey`` so the GUI can open its guided
  wizard. Consecutive calls are PACED ``AI_CALL_PAUSE_S`` apart (the
  free tier is ~10 requests/minute).
* the SHEET-GENERATOR flow helpers (owner's #2): parse the model's
  numbered clarifying questions, build the two calls from the sheet
  contract (instructions.md), validate a produced ``.md`` with the
  REAL sheet parser and drive ONE automatic repair round, then save
  the clean sheet under ``sheets/`` with a slugged filename.
* the FLAG MEMORY (owner's #3): ``<out>/_state/ai_flags.json`` keyed
  by the image's path RELATIVE to the out base; each entry carries the
  defects, the check time, the model and the file's mtime — a changed
  mtime (the image was REGENERATED) invalidates the flag on the next
  prune. ``drop_and_site_for`` reverses ``dest_for`` so a flagged
  image can be re-sent to the SITE that generated it.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path, PurePosixPath

from painter.config import (
    AI_CALL_PAUSE_S,
    AI_FLAGS_FILENAME,
    AI_FIX_NOTE,
    AI_MAX_QUESTIONS,
    AI_QUESTIONS_SYSTEM,
    AI_REPAIR_PROMPT,
    AI_SHEET_REQUEST,
    AI_SHEET_SYSTEM,
    AI_TIMEOUT_S,
    GEMINI_API_BASE,
    GEMINI_KEY_SETTING,
    GEMINI_TEXT_MODEL,
    GEMINI_VISION_MODEL,
    PROJECT_ROOT,
    SITES,
    STATE_DIRNAME,
)
from painter.settings import load_settings
from painter.sheet_parser import SheetError, parse_sheet


class AiError(Exception):
    """A Gemini API call failed — HTTP error, refusal/block or a
    malformed response. Loud (Rule #1); the CALLER decides whether one
    failure skips an image or stops a flow — it is never swallowed."""


class NoKey(AiError):
    """settings.json holds no Gemini API key — the GUI reacts by
    opening the guided key wizard (the documented auto-open path)."""


# ---------------------------------------------------------------------
# The REST client
# ---------------------------------------------------------------------

# module alias so tests can monkeypatch the HTTP layer in ONE place
_urlopen = urllib.request.urlopen

# image suffix -> request mime type (the checker feeds saved outputs)
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_last_call_t: float | None = None  # monotonic time of the last API call


def api_key() -> str:
    """The Gemini key from settings.json; ``NoKey`` when absent/blank."""
    key = str(load_settings().get(GEMINI_KEY_SETTING, "") or "").strip()
    if not key:
        raise NoKey(
            "no Gemini API key in settings.json — run the 'AI key…'"
            " wizard (a free key from aistudio.google.com)"
        )
    return key


def _pace() -> None:
    """Keep consecutive API calls ``AI_CALL_PAUSE_S`` apart (free-tier
    requests-per-minute); the FIRST call of a session never waits."""
    global _last_call_t
    if _last_call_t is not None:
        wait = _last_call_t + AI_CALL_PAUSE_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
    _last_call_t = time.monotonic()


def _payload_text(prompt: str, system: str | None) -> dict:
    payload: dict = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    return payload


def _payload_image(image_bytes: bytes, mime: str, instructions: str) -> dict:
    return {
        "contents": [
            {
                "parts": [
                    {"text": instructions},
                    {
                        "inlineData": {
                            "mimeType": mime,
                            "data": base64.b64encode(image_bytes).decode(
                                "ascii"
                            ),
                        }
                    },
                ]
            }
        ]
    }


def _http_detail(exc: urllib.error.HTTPError) -> str:
    """The API's own error message when the body carries the standard
    ``{"error": {"message": ...}}`` JSON, else the plain HTTP reason —
    a best-effort DETAIL extractor for the loud AiError, never a
    swallow (the AiError is raised either way)."""
    try:
        return json.loads(exc.read())["error"]["message"]
    except Exception:
        return str(exc.reason)


def _response_text(data: dict, model: str) -> str:
    """The first candidate's concatenated text parts.

    Tolerates the candidates/parts structure (empty candidates are
    skipped); LOUD on prompt blocks, non-STOP stops with no text, and
    any shape carrying no text at all.
    """
    if not isinstance(data, dict):
        raise AiError(f"{model}: malformed response (not a JSON object)")
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise AiError(f"{model}: prompt blocked by the API ({block})")
    for cand in data.get("candidates") or ():
        if not isinstance(cand, dict):
            continue
        parts = (cand.get("content") or {}).get("parts") or ()
        text = "".join(
            p.get("text", "") for p in parts if isinstance(p, dict)
        )
        if text.strip():
            return text
        finish = cand.get("finishReason")
        if finish and finish != "STOP":
            raise AiError(
                f"{model}: generation stopped ({finish}) with no text"
            )
    raise AiError(
        f"{model}: response carries no text (keys: {sorted(data)})"
    )


def _call(model: str, payload: dict, key: str) -> str:
    """POST one generateContent request; returns the response TEXT."""
    _pace()
    req = urllib.request.Request(
        f"{GEMINI_API_BASE}/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    try:
        with _urlopen(req, timeout=AI_TIMEOUT_S) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise AiError(
            f"Gemini API HTTP {exc.code} on {model}: {_http_detail(exc)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise AiError(f"Gemini API unreachable: {exc.reason}") from exc
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AiError(
            f"Gemini API returned non-JSON: {raw[:200]!r}"
        ) from exc
    return _response_text(data, model)


def generate_text(
    prompt: str,
    system: str | None = None,
    *,
    key: str | None = None,
    model: str = GEMINI_TEXT_MODEL,
) -> str:
    """One text generation; ``key=None`` reads settings.json (NoKey
    when absent) — the wizard's Test passes its candidate explicitly."""
    return _call(model, _payload_text(prompt, system), key or api_key())


def check_image(
    image_path: Path,
    instructions: str,
    *,
    key: str | None = None,
    model: str = GEMINI_VISION_MODEL,
) -> str:
    """One vision call over a saved image file; returns the raw text."""
    image_path = Path(image_path)
    mime = _MIME.get(image_path.suffix.lower())
    if mime is None:
        raise AiError(
            f"{image_path.name}: unsupported image type for the checker"
        )
    payload = _payload_image(image_path.read_bytes(), mime, instructions)
    return _call(model, payload, key or api_key())


# ---------------------------------------------------------------------
# The sheet-generator flow (owner's #2)
# ---------------------------------------------------------------------

# "1. q" / "1) q" / "- q" / "* q" — the poll lines the model returns
_QUESTION_LINE = re.compile(r"^\s*(?:\d+[.)]\s*|[-*•]\s+)(.+?)\s*$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def contract_text() -> str:
    """instructions.md verbatim — the authoring contract both system
    prompts embed (the same doc the Instructions button shows)."""
    return (PROJECT_ROOT / "instructions.md").read_text(encoding="utf-8")


def parse_questions(text: str) -> list[str]:
    """The model's clarifying questions, capped at ``AI_MAX_QUESTIONS``.

    Accepts numbered ('1.' / '1)') and dash/star bullet lines; plain
    prose lines are ignored. An answer with NO parseable question
    lines returns [] — the caller then skips the poll and generates
    from the request alone.
    """
    questions: list[str] = []
    for line in text.splitlines():
        m = _QUESTION_LINE.match(line)
        if m and m.group(1).strip():
            questions.append(m.group(1).strip())
    return questions[:AI_MAX_QUESTIONS]


def ask_questions(request: str, contract: str, gen=None) -> list[str]:
    """FIRST call: the contract + 'questions only' system prompt.

    ``gen`` defaults to THIS module's ``generate_text`` resolved at
    CALL time, so tests (and a mocked GUI run) can monkeypatch
    ``ai.generate_text`` and the flow follows."""
    gen = gen or generate_text
    system = AI_QUESTIONS_SYSTEM.format(
        contract=contract, max_q=AI_MAX_QUESTIONS
    )
    return parse_questions(gen(request, system))


def qa_block(questions: list[str], answers: list[str]) -> str:
    """The answered poll as Q/A lines; a skipped (blank) answer is an
    explicit 'no preference' so the model still decides something."""
    lines: list[str] = []
    for question, answer in zip(questions, answers):
        lines.append(f"Q: {question}")
        lines.append(f"A: {answer.strip() or '(no preference — your choice)'}")
    return "\n".join(lines) or "(no questions were asked)"


def strip_md_fence(text: str) -> str:
    """Unwrap a whole-file ``` fence pair (models wrap the sheet in one
    despite instructions). ONLY the exact wrapper case is touched — a
    body not starting with a fence, or not ending with a bare closing
    fence, passes through byte-identical so the sheet's own inner
    prompt fences always survive."""
    body = text.strip()
    if not body.startswith("```"):
        return text
    lines = body.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return text
    return "\n".join(lines[1:-1])


def validate_sheet_md(md: str, work_dir: Path) -> tuple[list[str], str | None]:
    """Parse ``md`` with the REAL parser (on a scratch file under
    ``work_dir``) and return ``(problem strings, theme)`` — an empty
    problem list means the sheet is contract-clean and loadable."""
    tmp = Path(work_dir) / "_ai_sheet_validate.md"
    tmp.write_text(md, encoding="utf-8")
    try:
        sheet = parse_sheet(tmp)
    except SheetError:
        return ["no '# ' H1 theme heading — not a prompt sheet"], None
    return (
        [f"L{p.line}: {p.message}" for p in sheet.problems],
        sheet.theme,
    )


def generate_sheet(
    request: str,
    questions: list[str],
    answers: list[str],
    contract: str,
    work_dir: Path,
    gen=None,
    log=print,
) -> tuple[str, list[str], str | None]:
    """SECOND call + at most ONE automatic repair round.

    Returns ``(md, problems, theme)``: ``problems == []`` means the md
    passed the real parser and may be saved/loaded; otherwise ``md`` is
    the best (repaired) attempt for the owner to fix manually — the
    caller must NOT load it. ``gen`` resolves to ``generate_text`` at
    CALL time (monkeypatch-friendly, like ``ask_questions``).
    """
    gen = gen or generate_text
    system = AI_SHEET_SYSTEM.format(contract=contract)
    user = AI_SHEET_REQUEST.format(
        request=request, qa=qa_block(questions, answers)
    )
    md = strip_md_fence(gen(user, system))
    problems, theme = validate_sheet_md(md, work_dir)
    if problems:
        log(
            f"AI sheet fails the parser ({len(problems)} problem(s)) —"
            " one automatic repair round"
        )
        repair = AI_REPAIR_PROMPT.format(
            problems="\n".join(problems), md=md
        )
        md = strip_md_fence(gen(repair, system))
        problems, theme = validate_sheet_md(md, work_dir)
    return md, problems, theme


def slug_for(theme: str) -> str:
    """A filesystem-safe stem from the sheet's H1 theme."""
    slug = _SLUG_STRIP.sub("_", theme.lower()).strip("_")
    return slug or "ai_sheet"


def save_sheet(md: str, theme: str, sheets_dir: Path) -> Path:
    """Write a VALIDATED sheet under ``sheets_dir`` (created on demand)
    with a slugged, collision-free filename; returns the path."""
    sheets_dir = Path(sheets_dir)
    sheets_dir.mkdir(parents=True, exist_ok=True)
    base = slug_for(theme)
    path = sheets_dir / f"{base}.md"
    n = 2
    while path.exists():
        path = sheets_dir / f"{base}_{n}.md"
        n += 1
    path.write_text(md, encoding="utf-8")
    return path


# ---------------------------------------------------------------------
# The image checker + flag memory (owner's #3)
# ---------------------------------------------------------------------


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


def flags_path(out_base: Path) -> Path:
    return Path(out_base) / STATE_DIRNAME / AI_FLAGS_FILENAME


def flag_key(image_path: Path, out_base: Path) -> str:
    """The flag dict's key for one image: its POSIX path RELATIVE to
    the out base. An image OUTSIDE the base keys by its absolute POSIX
    path — the flag still persists, but ``drop_and_site_for`` cannot
    match it to a queued collection (the re-send logs and skips it)."""
    resolved = Path(image_path).resolve()
    try:
        return resolved.relative_to(Path(out_base).resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _flag_file(key: str, out_base: Path) -> Path:
    """The image file a flag key points at (relative or absolute)."""
    path = Path(key)
    return path if path.is_absolute() else Path(out_base) / path


def load_flags(out_base: Path, log=print) -> dict:
    """The saved flags dict; {} on a missing file. A corrupt file is
    reported LOUDLY and treated as empty — flags are derived data (a
    re-check rebuilds them), so losing them never loses work."""
    path = flags_path(out_base)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log(f"AI FLAGS: cannot read {path} ({exc}) — starting empty")
        return {}
    if not isinstance(data, dict):
        log(
            f"AI FLAGS: {path} does not hold a JSON object — starting"
            " empty"
        )
        return {}
    return data


def save_flags(out_base: Path, flags: dict) -> Path:
    """Atomic write (tmp + replace), mirroring settings.py."""
    path = flags_path(out_base)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(flags, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)
    return path


def record_flag(
    out_base: Path,
    image_path: Path,
    defects: list[str],
    model: str,
    log=print,
) -> str:
    """Load-merge-save one image's flag entry; returns its key. The
    stored mtime is the file's AT CHECK TIME — a later regeneration
    changes it and ``prune_stale_flags`` drops the entry."""
    flags = load_flags(out_base, log)
    key = flag_key(image_path, out_base)
    flags[key] = {
        "defects": list(defects),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "mtime": Path(image_path).stat().st_mtime,
    }
    save_flags(out_base, flags)
    return key


def clear_flag_keys(out_base: Path, keys: list[str], log=print) -> int:
    """Drop the given flag ENTRIES by key (the panel's Clear-flags
    action); returns the number actually removed."""
    flags = load_flags(out_base, log)
    removed = sum(1 for key in keys if flags.pop(key, None) is not None)
    if removed:
        save_flags(out_base, flags)
    return removed


def clear_flag(out_base: Path, image_path: Path, log=print) -> bool:
    """Drop one image's entry (an OK re-check clears the old flag);
    True when an entry existed."""
    return clear_flag_keys(
        out_base, [flag_key(image_path, out_base)], log
    ) == 1


def prune_stale_flags(out_base: Path, log=print) -> int:
    """Drop every entry whose file is GONE or whose mtime CHANGED since
    the check (the image was regenerated / retouched) — run before a
    check batch so the memory never asserts stale defects. Returns the
    number dropped."""
    flags = load_flags(out_base, log)
    keep: dict = {}
    dropped = 0
    for key, entry in flags.items():
        file = _flag_file(key, out_base)
        try:
            same = file.stat().st_mtime == float(entry.get("mtime", -1.0))
        except (OSError, TypeError, ValueError):
            same = False  # gone or malformed entry -> stale
        if same:
            keep[key] = entry
        else:
            dropped += 1
    if dropped:
        save_flags(out_base, keep)
        log(
            f"AI FLAGS: {dropped} stale flag(s) cleared (file changed"
            " or gone since the check)"
        )
    return dropped


def drop_and_site_for(rel: str) -> tuple[str, str] | None:
    """Reverse ``config.dest_for``: the (drop_path, site) one
    out-relative save path came from.

    Assets mirror ``<category>/<site>/<rest>`` ->
    ``('assets/<category>/<rest>', site)``; legacy ``<site>/<drop>`` ->
    ``(drop, site)``. ``None`` when no segment names a site (an
    absolute flag key, or a folder that was never a generator output).
    """
    parts = PurePosixPath(rel).parts
    if len(parts) >= 3 and parts[1] in SITES:
        return "assets/" + "/".join((parts[0], *parts[2:])), parts[1]
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
