"""The run loop — queue, done-edge, save, fix, report, resume, pace.

Per pending item: paste (prompt + the site's rule suffix) -> submit
-> await the done edge -> extract bytes -> save DIRECTLY under
``<out_root>/<drop-path>`` -> background fix -> report line -> pause
-> next. A crash or a quota stop costs nothing: "done" is the SAVED
FILE itself, so the next unattended run resumes past every image
already on disk, and the report keeps every finished line.

The loop only ever writes under ``out_root`` (images, report,
background fixes) — sheets are READ ONLY by construction.
"""

from __future__ import annotations

import hashlib
import random
import struct
import time
from pathlib import Path
from typing import Callable

from painter.config import (
    CONTINUE_NUDGE,
    PAUSE_POLL_INTERVAL_S,
    REFUSAL_DIAGNOSTIC_QUESTION,
    REPORT_SUFFIX,
    RETRY_PREAMBLES,
    STATE_DIRNAME,
    TRANSCRIPT_FILENAME,
    Timing,
    dest_for,
    fmt_duration,
    parse_quota_reset,
    versioned_dest_for,
)
from painter.driver import (
    GenerationTimeout,
    ImageGenFailed,
    ItemRefused,
    ModelDegraded,
    NoImage,
    SendVanished,
    SiteDriver,
    TerminalState,
    sniff_format,
)
from painter.recovery import interruptible_sleep, recover_image_failed
from painter.run_report import RunReport
from painter.sheet_parser import Sheet, SkippedItem
from painter.transcript import Transcript

Log = Callable[[str], None]
# GUI stop button etc.; checked between items and during the pause
ShouldStop = Callable[[], bool]
# GUI pause toggle; checked between items — while True the loop blocks
# (poll-wait, see wait_while_paused) until it flips False or should_stop
# fires. Same shape as ShouldStop, kept as its own alias for clarity.
ShouldPause = Callable[[], bool]
# background fix: (saved file) -> action string; exceptions are logged
PostSave = Callable[[Path], str]
# structured progress events for dashboards: receives dicts like
# {"type": "item_done", "gen_s": 41.2} — see run_sheet for the types
OnEvent = Callable[[dict], None]

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> str:
    """WxH from a PNG header (all saved images are PNG), else '?'."""
    if len(data) >= 24 and data.startswith(_PNG_MAGIC):
        width, height = struct.unpack(">II", data[16:24])
        return f"{width}x{height}"
    return "?"


def _pause(timing: Timing, should_stop: ShouldStop | None, log: Log) -> None:
    """A random polite pause between prompts, interruptible by Stop."""
    wait = random.uniform(timing.pause_min_s, timing.pause_max_s)
    log(f"    pause {wait:.2f}s (paced run)")
    interruptible_sleep(wait, should_stop, log)


def wait_while_paused(
    should_pause: ShouldPause | None,
    should_stop: ShouldStop | None,
    log: Log,
    emit: OnEvent,
) -> bool:
    """Block between items/images while a GUI Pause toggle is on.

    Distinct from the timed ``_pause`` above (a fixed random pacing
    wait) and from a plain ``should_stop`` check (a one-way request):
    this is an INDEFINITE wait until the owner clicks Resume. Poll-wait
    only (no busy spin) — ``should_stop`` is re-checked every tick so a
    Stop always wins over a pending/active pause instead of hanging
    until Resume. Emits ``sheet_paused`` / ``sheet_resumed`` on the
    ``emit`` stream exactly ONCE per transition (never once per poll),
    and skips the ``sheet_resumed`` half when a Stop interrupted the
    wait — the run is ending, not continuing. Shared by ``run_sheet``
    (checked between sheet items) and the GUI's tool / AI-check worker
    loops (checked between images) — see runner.md / gui.md.

    Returns True when a Stop interrupted an ACTIVE pause — the caller
    should treat that exactly like its own ``should_stop()`` firing.
    Returns False otherwise, including the common case where
    ``should_pause`` was never True: then ``should_stop`` is never even
    queried here, so a caller that already checked it once this
    iteration never double-counts the call (it may have side effects,
    e.g. a test's call counter, or simply be non-trivial to evaluate).
    """
    if should_pause is None or not should_pause():
        return False
    log("    PAUSED — waiting to resume ...")
    emit({"type": "sheet_paused"})
    while should_pause():
        if should_stop is not None and should_stop():
            return True
        time.sleep(PAUSE_POLL_INTERVAL_S)
    emit({"type": "sheet_resumed"})
    log("    RESUMED")
    return False


def resolve_input_images(
    refs: tuple[str, ...] | list[str],
    sheet_dir: Path,
    reference_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve an entry's "← `ref`" references to real files (faza 2,
    owner 2026-08-03 — the binding resolution order): each ref is tried
    ① relative to the sheet's own folder, ② relative to the run's
    ``reference_dir`` (the GUI Prompt+Image section's Reference
    folder), ③ as an absolute path. Sources are READ ONLY everywhere.

    Returns ``(resolved, missing)`` — resolved absolute path strings in
    the SAME order as ``refs`` (attach order), and the raw refs that
    were found nowhere. Never guesses (no basename search, no fuzzy
    match): a miss is the author's or the folder-picker's to fix, and
    it is reported loudly by every caller."""
    resolved: list[str] = []
    missing: list[str] = []
    for ref in refs:
        candidates = [sheet_dir / ref]
        if reference_dir is not None:
            candidates.append(reference_dir / ref)
        if Path(ref).is_absolute():
            candidates.append(Path(ref))
        hit = next((c for c in candidates if c.is_file()), None)
        if hit is None:
            missing.append(ref)
        else:
            resolved.append(str(hit))
    return resolved, missing


def run_sheet(
    sheet: Sheet,
    driver: SiteDriver,
    out_base: Path,
    site_key: str,
    timing: Timing,
    log: Log = print,
    should_stop: ShouldStop | None = None,
    should_pause: ShouldPause | None = None,
    post_save: PostSave | None = None,
    prompt_suffix: str = "",
    extra_suffix: dict[str, str] | None = None,
    report: bool = True,
    only: set[str] | None = None,
    on_event: OnEvent | None = None,
    safer_retry: bool = False,
    continue_nudge: bool = True,
    image_failed_retry: bool = True,
    new_chat_per_folder: bool = False,
    on_degrade: Callable[[float | None], str] | None = None,
    reference_dir: Path | None = None,
    require_input_image: bool = False,
) -> int:
    """Generate every pending item of a clean sheet; returns the count.

    Saves land at ``out_base / dest_for(drop, site_key)`` — the
    assets-mirroring layout. The report lives under
    ``out_base/_state/<site>/`` so the image tree stays copy-ready.
    The caller has already refused sheets with problems; skipped
    entries are logged here and never driven. ``only`` (the owner's
    ticked drop paths) narrows the queue to those items and NEVER
    overwrites a dest file already on disk — the folder is always the
    source of truth (owner 2026-07-21, after a restart regenerated 18
    already-saved images). A ticked item whose dest file exists is a
    deliberate REDO (owner 2026-07-27): it generates a NEW VERSION
    saved as the next ``_vN`` sibling (``versioned_dest_for`` — the
    DOMY ``<File>[_vN]_<sfx>.png`` rotation convention, canonical =
    v1, so the first redo lands as ``_v2``) while the existing file
    stays untouched. The unattended (``only=None``) resume path still
    skips everything already on disk — versions are made only by an
    explicit tick. Every ``item_progress``/``item_done`` event carries
    ``rel``, the ACTUAL saved out-relative path, so dashboards and the
    parallel checker follow the version file, never the canonical
    guess. ``extra_suffix``
    (owner 2026-07-20, the AI checker's
    re-send) maps a drop path to EXTRA text appended AFTER the site
    suffix for exactly that item (the "previous attempt had these
    flaws" fix note); items absent from the map get no extra text.
    ``should_pause`` (owner 2026-07-21, the GUI Pause toggle) is
    checked at the same item boundary as ``should_stop``: while it
    returns True the loop poll-waits (``wait_while_paused``, no busy
    spin) until it returns False (Resume) or ``should_stop`` fires
    (Stop always wins over a pending pause). Emits ``sheet_paused`` /
    ``sheet_resumed`` on the ``on_event`` stream, once per transition.
    ``image_failed_retry`` (owner 2026-07-21, BUG 3, default on) is the
    ``ImageGenFailed`` recovery: ChatGPT's own "Image generation
    failed" answer is caught by the driver WHILE it is still waiting
    (never a burned hard timeout); the runner resends the driver's
    ``IMAGE_RETRY_NUDGE`` ("retry", the site's own suggested word) into
    the same chat up to ``IMAGE_FAILED_RETRY_MAX`` times, and if it
    still fails, skips the item exactly like a safety refusal (logged,
    counted, added to the report) — never silently. With it off, the
    first ``ImageGenFailed`` propagates and stops the site immediately,
    same shape as ``continue_nudge=False``.

    An item carrying INPUT IMAGE(S) (``PromptItem.input_images``, owner
    2026-07-23; MULTI + the reference folder 2026-08-03, faza 2 — the
    sheet's "← `ref`" line(s), LINE ORDER = ATTACH ORDER) has each
    reference resolved by ``resolve_input_images`` (sheet folder →
    ``reference_dir`` → absolute; sources READ ONLY) and attached into
    the composer before the prompt via ``driver.submit_with_image``; a
    plain item still goes through ``submit_prompt``. A missing
    reference file is a loud per-item SKIP (logged, counted, reported)
    so the rest of the batch still runs.

    ``require_input_image`` (faza 2 — the GUI's PROMPT + IMAGE mode,
    owner: "radi samo one slike koje imaju i PROMPT i PNG u prilogu"):
    when True the queue is narrowed to items that declare at least one
    "←" reference AND whose references ALL resolve right now — load
    every prompt plus one reference file on disk and exactly one item
    runs. Every excluded item is loudly listed and reported, never
    silently dropped.
    """
    state_dir = out_base / STATE_DIRNAME / site_key
    state_dir.mkdir(parents=True, exist_ok=True)
    run_report = (
        RunReport(
            state_dir / (sheet.source.stem + REPORT_SUFFIX),
            sheet.theme,
            driver.site.name,
        )
        if report
        else None
    )
    # the AI response TRANSCRIPT (owner 2026-08-11): every text the
    # site answered, verbatim, beside the report — new/unknown site
    # states are mined from this record instead of re-provoked live
    transcript = Transcript(state_dir / TRANSCRIPT_FILENAME)

    for sk in sheet.skipped:
        log(f"  SKIP {sk.title} — {sk.reason}")

    # "Done" is the SAVED FILE itself, not a sidecar record (owner
    # 2026-07-19): an item is already done exactly when its dest file
    # exists on disk. The folder is ALWAYS the source of truth (owner
    # 2026-07-21): no file on disk is EVER overwritten. An explicit
    # tick on a done item redoes it as a NEW ``_vN`` VERSION instead
    # (owner 2026-07-27) — the canonical file stays untouched.
    def _on_disk(item) -> bool:
        return (out_base / dest_for(item.drop_path, site_key)).exists()

    report_skips = list(sheet.skipped)
    # drop path -> the version rel it saves to, for ticked items whose
    # canonical file already exists; empty on the unattended path
    version_dest: dict[str, str] = {}
    if only is not None:
        # the owner's ticks ARE the queue; a ticked item already on
        # disk is a deliberate redo — it saves as the next _vN version
        ticked = [it for it in sheet.items if it.drop_path in only]
        if len(ticked) != len(sheet.items):
            log(
                f"  SELECTION: {len(ticked)}/{len(sheet.items)}"
                " item(s) ticked for this run"
            )
        queue = ticked
        version_dest = {
            it.drop_path: versioned_dest_for(
                it.drop_path, site_key, out_base
            )
            for it in ticked
            if _on_disk(it)
        }
        if version_dest:
            log(
                f"  NEW VERSION: {len(version_dest)}/{len(ticked)}"
                " ticked item(s) already saved — each redo lands as"
                " its next _vN file; the existing image stays untouched"
            )
    else:
        # no explicit selection: resume by FILE EXISTENCE — skip every
        # item already saved on disk; sheet-advised items sit out too
        queue = [it for it in sheet.items if not _on_disk(it)]
        already = len(sheet.items) - len(queue)
        if already:
            log(
                f"  RESUME: {already}/{len(sheet.items)} already saved"
                f" on disk under {site_key}/"
            )
        for it in (adv := [it for it in queue if it.advice]):
            log(f"  NOT RUN (sheet advice): {it.title} — {it.advice}")
            report_skips.append(
                SkippedItem(it.title, f"advice, not ticked: {it.advice}", it.line)
            )
        if adv:
            log(
                "  (tick them in 'Select images...' to generate them"
                " anyway)"
            )
            queue = [it for it in queue if not it.advice]
    if require_input_image:
        # PROMPT + IMAGE mode (faza 2): only items whose prompt AND
        # every declared "←" reference are both present run — the
        # owner's rule, checked against the CURRENT disk state
        eligible = []
        for it in queue:
            if not it.input_images:
                log(f"  NOT ELIGIBLE (no ← reference): {it.title}")
                report_skips.append(SkippedItem(
                    it.title, "Prompt+Image mode: no ← reference", it.line
                ))
                continue
            _ok, missing = resolve_input_images(
                it.input_images, sheet.source.parent, reference_dir
            )
            if missing:
                log(
                    f"  NOT ELIGIBLE (reference missing): {it.title} —"
                    f" {', '.join(missing)}"
                )
                report_skips.append(SkippedItem(
                    it.title,
                    "Prompt+Image mode: reference missing:"
                    f" {', '.join(missing)}",
                    it.line,
                ))
                continue
            eligible.append(it)
        if len(eligible) != len(queue):
            log(
                f"  PROMPT+IMAGE: {len(eligible)}/{len(queue)} item(s)"
                " have both prompt and reference(s) — only those run"
            )
        queue = eligible
    if run_report is not None:
        run_report.start(len(queue), len(sheet.items), tuple(report_skips))

    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    def generate_one(
        text: str, attach: list[str] | None = None
    ) -> tuple[bytes, float]:
        """Submit one prompt and return (image bytes, send timestamp).

        ``attach`` (owner 2026-07-23; MULTI 2026-08-03) is the resolved
        input-image path list, in the sheet's ← line order: when given,
        the image(s) are attached into the composer BEFORE the text
        (``submit_with_image`` — "put THIS character into that scene");
        otherwise it is a plain text submit. Callers pass ``attach``
        only where a fresh chat needs the image(s): the FIRST send and
        a safer retry (same item, reframed) and the image-failed
        escalation (which opens a NEW session); the same-chat nudges/
        retries stay text-only (the images are already attached there).

        The send timestamp marks when SEND was pressed, so the caller
        can time the pure generation (send -> image) apart from the
        input hesitation inside the submit.

        ``log`` is passed into the SUBMIT calls too (owner 2026-08-04):
        it used to be omitted, so every submit-phase diagnostic — the
        pre-send busy wait, the send retry, the send-button reload
        recovery — went to stdout ``print`` and was INVISIBLE in the GUI
        and the report. A live run showed 7 unexplained silent minutes
        because of exactly that.
        """
        if attach:
            driver.submit_with_image(attach, text, log)
        else:
            driver.submit_prompt(text, log)
        t_send = time.monotonic()
        driver.await_done(log)
        return driver.extract_image(), t_send

    emit(
        {
            "type": "sheet_start",
            "sheet": sheet.source.name,
            "pending": len(queue),
            "total": len(sheet.items),
        }
    )

    start = time.monotonic()
    total = len(queue)
    generated = 0
    refused = 0
    fix_failures = 0
    stopped_why = "all pending items done"
    last_folder: str | None = None
    # F1 duplicate guard (owner 2026-07-29): byte-hash of the LAST
    # saved image this run — a new result identical to it means the
    # site re-served the previous image (the "AI 1s" duplicate bug);
    # one fresh re-submit, then a loud per-item skip
    last_saved_digest: bytes | None = None
    # F2 gap fix (owner 2026-07-29): the degradation banner can be up
    # while images STILL arrive (Flash-Lite renders them) — probed
    # after every save, the owner's choice asked ONCE per run
    degrade_probe = getattr(driver, "degrade_banner_text", None)
    degrade_handled = False
    try:
        for idx, item in enumerate(queue, start=1):
            if should_stop is not None and should_stop():
                stopped_why = "stopped on request"
                log(f"  STOPPED on request — {generated}/{total} this run")
                break
            if wait_while_paused(should_pause, should_stop, log, emit):
                stopped_why = "stopped on request"
                log(f"  STOPPED on request — {generated}/{total} this run")
                break
            if new_chat_per_folder:
                folder = str(Path(item.drop_path).parent)
                if last_folder is not None and folder != last_folder:
                    log(f"  new chat (folder change -> {folder})")
                    try:
                        driver.new_chat(log)
                    except Exception as exc:  # loud, never fatal
                        log(f"  NEW CHAT FAILED (continuing in the"
                            f" old one): {exc}")
                last_folder = folder
            elapsed = time.monotonic() - start
            log(f"[{elapsed:7.1f}s] ({idx}/{total}) {item.title}")
            emit(
                {
                    "type": "item_start",
                    "title": item.title,
                    "idx": idx,
                    "of": total,
                }
            )

            suffix = prompt_suffix
            # a PER-ITEM extra (the AI re-send fix note) rides at the
            # very end, after every site rule — and survives a safer
            # retry, which prepends its preamble to this same base
            extra = extra_suffix.get(item.drop_path) if extra_suffix else None
            if extra:
                suffix += "\n\n" + extra
            base = item.prompt + suffix

            # OPTIONAL input image(s) (owner 2026-07-23; MULTI + the
            # reference folder 2026-08-03): resolve every "← `ref`"
            # (sheet folder → reference_dir → absolute) and attach them
            # into the composer before the prompt, in ← line order.
            # Sources are READ ONLY (never under out_base). A missing
            # file is a loud per-item SKIP — the rest of the batch
            # still runs; the fix is in the sheet, the Reference folder
            # pick, or on disk — not here.
            input_paths: list[str] | None = None
            if item.input_images:
                resolved, missing = resolve_input_images(
                    item.input_images, sheet.source.parent, reference_dir
                )
                if missing:
                    refused += 1
                    reason = f"input image missing: {', '.join(missing)}"
                    log(f"    INPUT IMAGE MISSING — {', '.join(missing)}")
                    log(
                        "    skipping this item; add the file(s), fix the"
                        " '← path' in the sheet, or point the Reference"
                        " folder at them — then rerun"
                    )
                    if run_report is not None:
                        run_report.refused(item.drop_path, reason)
                    emit(
                        {
                            "type": "item_refused",
                            "drop_path": item.drop_path,
                            "reason": reason,
                        }
                    )
                    if idx < total:
                        _pause(timing, should_stop, log)
                    continue
                input_paths = resolved
                log(
                    "    input image(s): "
                    + ", ".join(Path(p).name for p in resolved)
                )

            retried = False  # True when a RETRY path produced the image
            skip_reason: str | None = None
            # the ItemRefused that ENDED in a skip — the trigger for the
            # one text-only diagnostic question (owner 2026-08-11)
            refused_exc: ItemRefused | None = None
            data = None
            t_send = 0.0

            def t_rec(
                event: str, matched: str | None = None, action: str = ""
            ) -> None:
                """One transcript row for THIS item, carrying the FULL
                raw response text the driver last read (the exceptions
                truncate it; the transcript never does)."""
                transcript.record(
                    event, sheet=sheet.source.name, item=item.drop_path,
                    # getattr: duck-typed drivers (tests, the API job)
                    # may not track a last response text
                    raw_text=getattr(driver, "last_response_text", ""),
                    matched=matched, action=action, log=log,
                )

            def try_safer(exc: ItemRefused):
                """One safer retry with the category's preamble (owner
                2026-07-23); returns (data, t_send) or (None, reason).
                Shared by the first-attempt refusal AND a refusal that
                surfaces inside the image-failed ladder (F1 root cause
                3 — that one used to stop the whole site).

                The retry catches EVERY per-item driver verdict, not
                just a second refusal (owner 2026-08-04, the 18:43:46
                stop): a ``NoImage``/``GenerationTimeout``/
                ``SendVanished`` raised INSIDE this handler used to fly
                past the outer per-item catches — Python never routes
                an exception from one ``except`` block to its siblings
                — and killed the WHOLE site over one item's retry.
                Quota (``TerminalState``) still propagates: that stop
                is correct."""
                reason = str(exc)
                preamble = RETRY_PREAMBLES.get(exc.category)
                t_rec(
                    "refused", matched=exc.category,
                    action=(
                        "safer retry"
                        if safer_retry and preamble is not None
                        else "skip (no retry)"
                    ),
                )
                if safer_retry and preamble is not None:
                    log(
                        f"    REFUSED [{exc.category}] — one safer retry"
                        f" ({exc.category} reframing) ..."
                    )
                    emit({"type": "item_retry"})
                    try:
                        out = generate_one(
                            preamble + base, attach=input_paths
                        )
                        log("    safer retry SUCCEEDED")
                        return out, None
                    except (
                        ItemRefused,
                        NoImage,
                        GenerationTimeout,
                        SendVanished,
                    ) as exc2:
                        reason = str(exc2)
                        t_rec(
                            "retry_failed",
                            matched=(
                                exc2.category
                                if isinstance(exc2, ItemRefused)
                                else None
                            ),
                            action="skip",
                        )
                return None, reason

            try:
                data, t_send = generate_one(base, attach=input_paths)
            except ItemRefused as exc:
                result, reason = try_safer(exc)
                if result is None:
                    skip_reason = reason
                    refused_exc = exc
                else:
                    data, t_send = result
                    retried = True
            except NoImage as exc:
                t_rec(
                    "no_image",
                    action=(
                        "skip"
                        if exc.had_text or not continue_nudge
                        else "continue nudge"
                    ),
                )
                # F1 nudge policy (owner 2026-07-29, root cause 2): the
                # continue nudge is allowed ONLY for a truly empty /
                # interrupted answer. A TEXT answer matching no marker
                # is a LOUD per-item skip — nudging after text made
                # Gemini draw an unrelated image that got saved under
                # the item's name (the market-scene incident).
                if exc.had_text or not continue_nudge:
                    skip_reason = f"no image — {exc}"
                else:
                    log(
                        f"    NO RESPONSE - nudging {driver.site.name}"
                        " to continue (1 try) ..."
                    )
                    emit({"type": "item_nudge", "drop_path": item.drop_path})
                    try:
                        data, t_send = generate_one(CONTINUE_NUDGE)
                        log("    continue nudge RECOVERED")
                    except (NoImage, SendVanished) as exc2:
                        skip_reason = f"no image after nudge — {exc2}"
            except SendVanished as exc:
                # F1b (owner 2026-08-04, the Padmé/Qui-Gon incident):
                # the site DROPPED our confirmed message. The recovery
                # is the item's OWN prompt again — never the
                # content-blind continue nudge, which regenerated the
                # PREVIOUS request and saved a Qui-Gon badge as Padmé.
                log(
                    f"    SENT PROMPT VANISHED from the chat — {exc}"
                )
                log(
                    "    re-sending the item's own prompt (1 try) ..."
                )
                emit({"type": "item_retry"})
                try:
                    data, t_send = generate_one(base, attach=input_paths)
                    log("    re-send RECOVERED")
                    retried = True
                except (
                    ItemRefused,
                    NoImage,
                    GenerationTimeout,
                    SendVanished,
                ) as exc2:
                    skip_reason = (
                        f"prompt vanished; re-send failed — {exc2}"
                    )
            except ModelDegraded as exc:
                # F2 (owner 2026-07-29): the site dropped to a weaker
                # model (Gemini's Flash-Lite banner) and OUR turn got
                # no image. The choice is the user's: "wait" behaves
                # like a quota stop (auto-restart at the parsed reset);
                # "continue" keeps the run alive on the degraded model
                # — this item is loud-skipped, the next ones simply
                # succeed if the degraded model still renders images.
                choice = (
                    on_degrade(exc.retry_after_s)
                    if on_degrade is not None
                    else "wait"
                )
                if choice == "continue":
                    log(
                        "    MODEL DEGRADED — continuing on the weaker"
                        " model by choice; this item is skipped"
                    )
                    skip_reason = f"model degraded — {exc}"
                else:
                    log("    MODEL DEGRADED — waiting for the reset")
                    raise TerminalState(
                        str(exc), retry_after_s=exc.retry_after_s
                    ) from exc
            except ImageGenFailed as exc:
                # BUG 3, two faces (owner 2026-07-21 / 2026-07-23):
                # ChatGPT's image tool failed — either its own "reply
                # with 'retry'" text or the generic "Hmm...something
                # seems to have gone wrong." error turn. Both ride one
                # recovery ladder: native Retry button -> paced text
                # "retry" -> escalation rounds (wait, refresh, new
                # session, whole prompt). When the ladder is spent it
                # re-raises and the worker stops (files on disk resume).
                # A REFUSAL surfacing mid-ladder is handled exactly like
                # a first-attempt refusal (F1 fix — it used to escape
                # this block and stop the whole site).
                if not image_failed_retry:
                    raise
                try:
                    data, t_send = recover_image_failed(
                        exc, driver, generate_one, base, should_stop, log,
                        emit, input_paths,
                    )
                    retried = True
                except ItemRefused as exc2:
                    result, reason = try_safer(exc2)
                    if result is None:
                        skip_reason = reason
                        refused_exc = exc2
                    else:
                        data, t_send = result
                        retried = True

            # F1 duplicate guard: identical bytes to the previous save
            # = the site re-served the old image; one fresh re-submit,
            # then a loud skip (never a silent duplicate file)
            if skip_reason is None:
                digest = hashlib.sha1(data).digest()
                if digest == last_saved_digest:
                    log(
                        "    DUPLICATE IMAGE — identical to the previous"
                        " save; one fresh re-submit ..."
                    )
                    emit({"type": "item_retry"})
                    try:
                        data, t_send = generate_one(base, attach=input_paths)
                        digest = hashlib.sha1(data).digest()
                        retried = True
                    except (
                        ItemRefused,
                        NoImage,
                        ImageGenFailed,
                        GenerationTimeout,
                        SendVanished,
                    ) as exc:
                        skip_reason = f"duplicate image, retry failed: {exc}"
                    if skip_reason is None and digest == last_saved_digest:
                        skip_reason = (
                            "duplicate image persisted after a fresh"
                            " re-submit"
                        )
                if skip_reason is None:
                    last_saved_digest = digest

            if skip_reason is not None:
                refused += 1
                log(f"    REFUSED/SKIPPED — {skip_reason}")
                log(
                    "    continuing with the next item; rework the"
                    " prompt (or intervene manually) and rerun later"
                )
                t_rec("skipped", action=skip_reason)
                # THE REFUSAL DIAGNOSTIC (owner 2026-08-11): every
                # retry this run allows is spent — instead of a third
                # blind attempt, ask the site ONCE, text-only, WHY it
                # blocked this item. Best-effort by design: a failed
                # question never fails the run.
                diagnosis = ""
                # getattr: duck-typed drivers without ask_text (tests,
                # the API job) simply skip the question
                ask = getattr(driver, "ask_text", None)
                if refused_exc is not None and ask is not None:
                    log(
                        "    asking the refusal diagnostic question"
                        " (text only, no image burned) ..."
                    )
                    try:
                        # .replace, never .format — prompts contain
                        # braces; and the prompt is EMBEDDED because
                        # the site may not see prior context (the
                        # Obi-Wan "no access" answer, 2026-08-11)
                        diagnosis = ask(
                            REFUSAL_DIAGNOSTIC_QUESTION.replace(
                                "{prompt}", base
                            ),
                            log,
                        )
                    except Exception as dexc:
                        log(
                            "    diagnostic question FAILED (run"
                            f" continues): {dexc}"
                        )
                    if diagnosis:
                        log(f"    WHY (site's answer): {diagnosis[:200]}")
                        t_rec(
                            "diagnosis",
                            matched=refused_exc.category,
                            action="logged",
                        )
                    else:
                        log("    no diagnostic answer arrived")
                if run_report is not None:
                    run_report.refused(item.drop_path, skip_reason)
                    if diagnosis:
                        run_report.diagnosis(item.drop_path, diagnosis)
                emit(
                    {
                        "type": "item_refused",
                        "drop_path": item.drop_path,
                        "reason": skip_reason,
                        "diagnosis": diagnosis,
                    }
                )
                if idx < total:
                    _pause(timing, should_stop, log)
                continue
            t_image = time.monotonic()
            gen_s = t_image - t_send

            # a ticked redo saves as its precomputed _vN version rel;
            # everything else at the canonical dest (owner 2026-07-27)
            rel = version_dest.get(item.drop_path) or dest_for(
                item.drop_path, site_key
            )
            dest = out_base / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            orig_res = _png_size(data)
            fmt = sniff_format(data)
            if fmt != dest.suffix.lstrip(".").lower():
                log(
                    f"    WARNING: bytes look like"
                    f" {fmt or 'an unknown format'}, saved as"
                    f" {dest.suffix} because the sheet names the file"
                )

            actions: list[str] = []
            if item.drop_path in version_dest:
                # visible in the report's note column; badge_keys_for
                # ignores unknown segments, so no false badge dot
                actions.append(f"NEW VERSION: {rel.rsplit('/', 1)[-1]}")
            if post_save is not None:
                try:
                    # the hook composes its own steps (bg removal,
                    # crop, upscale ...) and returns the full
                    # description, e.g. "REMOVE BG: done, CROP: done"
                    action = post_save(dest)
                    if action:
                        actions.append(action)
                        log(f"    {action}")
                except Exception as exc:
                    fix_failures += 1
                    actions.append("POSTPROCESS: FAILED")
                    log(
                        f"    POSTPROCESS FAILED (image kept as"
                        f" saved): {exc}"
                    )

            saved_bytes = dest.read_bytes()
            size = len(saved_bytes)
            final_res = _png_size(saved_bytes)
            generated += 1
            log(f"    saved {dest} ({size:,} bytes)")
            t_rec("saved", action=rel)
            # count it live right away (dashboard progress + generate
            # avg) — carries everything the dashboard needs to add the
            # image to its table now, except our-time (needs the pause).
            # "actions" (the post_save description) + "retried" feed the
            # per-image STATUS BADGES (owner 2026-07-20).
            action_str = ", ".join(actions)
            emit(
                {
                    "type": "item_progress",
                    "idx": idx,
                    "of": total,
                    "title": item.title,
                    "drop_path": item.drop_path,
                    "rel": rel,
                    "gen_s": gen_s,
                    "orig_res": orig_res,
                    "final_res": final_res,
                    "size": size,
                    "actions": action_str,
                    "retried": retried,
                }
            )

            # OUR time = everything from the image appearing to the next
            # SEND: save + background fix + the paced pause (owner
            # 2026-07-17: "sve se računa"). The pause is timed here so it
            # belongs to this image's overhead; the last image has none.
            if idx < total:
                _pause(timing, should_stop, log)
            over_s = time.monotonic() - t_image

            if run_report is not None:
                run_report.item(
                    item.drop_path, gen_s, over_s, orig_res, final_res,
                    size, actions,
                )
            emit(
                {
                    "type": "item_done",
                    "title": item.title,
                    "drop_path": item.drop_path,
                    "rel": rel,
                    "gen_s": gen_s,
                    "over_s": over_s,
                    "orig_res": orig_res,
                    "final_res": final_res,
                    "size": size,
                    "actions": action_str,
                    "retried": retried,
                }
            )

            # F2 gap fix (owner 2026-07-29): the image ARRIVED, but is
            # the site quietly rendering on a degraded model? The
            # banner check runs AFTER the save (the made image is
            # never wasted); "wait" stops the site like a quota (the
            # auto-restart resumes past the saved files), "continue"
            # is remembered for the rest of the run.
            if degrade_probe is not None and not degrade_handled:
                banner = degrade_probe()
                if banner is not None:
                    degrade_handled = True
                    reset_s = parse_quota_reset(banner)
                    choice = (
                        on_degrade(reset_s)
                        if on_degrade is not None
                        else "wait"
                    )
                    if choice == "continue":
                        log(
                            "    MODEL DEGRADED (banner up, images"
                            " still rendering) — continuing on the"
                            " weaker model by choice"
                        )
                    else:
                        raise TerminalState(
                            "model degraded (banner) — waiting for"
                            f" the reset: {banner[:200]}",
                            retry_after_s=reset_s,
                        )
    except TerminalState as exc:
        stopped_why = "quota / rate limit — stopped"
        if exc.retry_after_s is not None:
            log(f"  quota — reset in ~{exc.retry_after_s / 60:.0f} min")
            stopped_why += f" (reset in ~{fmt_duration(exc.retry_after_s)})"
        raise
    except BaseException as exc:
        stopped_why = {
            "GenerationTimeout": "generation timed out",
            "NoImage": "no image — DOM state unknown",
            "ImageGenFailed": "image generation failed (site's own error)",
        }.get(type(exc).__name__, f"aborted: {type(exc).__name__}")
        raise
    finally:
        if run_report is not None:
            run_report.finish(
                generated, time.monotonic() - start, stopped_why
            )
        emit({"type": "sheet_done", "generated": generated})

    if refused:
        log(
            f"  NOTE: {refused} item(s) REFUSED by the site — listed in"
            " the report; rework those prompts and rerun"
        )
    if fix_failures:
        log(
            f"  NOTE: postprocess failed on {fix_failures} image(s) —"
            " the raw saves are kept; rerun the fixes over the output"
            " folder later"
        )
    return generated
