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

import random
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from painter.config import (
    CONTINUE_NUDGE,
    IMAGE_FAILED_RETRY_MAX,
    IMAGE_RETRY_NUDGE,
    PAUSE_POLL_INTERVAL_S,
    REPORT_SUFFIX,
    SAFER_PREAMBLE,
    STATE_DIRNAME,
    Timing,
    dest_for,
    fmt_duration,
    fmt_size,
)
from painter.driver import (
    ImageGenFailed,
    ItemRefused,
    NoImage,
    SiteDriver,
    TerminalState,
    sniff_format,
)
from painter.sheet_parser import Sheet, SkippedItem

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


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pause(timing: Timing, should_stop: ShouldStop | None, log: Log) -> None:
    """A random polite pause between prompts, interruptible by Stop."""
    wait = random.uniform(timing.pause_min_s, timing.pause_max_s)
    log(f"    pause {wait:.2f}s (paced run)")
    pause_end = time.monotonic() + wait
    while time.monotonic() < pause_end:
        if should_stop is not None and should_stop():
            break
        time.sleep(0.5)


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


class RunReport:
    """``<out_root>/<sheet-stem>_report.txt`` — appended per run.

    Written INCREMENTALLY (header, then a line per image, then the
    summary) so an interrupted run keeps every finished line.
    """

    def __init__(self, path: Path, theme: str, site_name: str):
        self.path = path
        self._theme = theme
        self._site = site_name
        self._gen_times: list[float] = []
        self._over_times: list[float] = []
        self._refused = 0

    def _append(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")

    def start(self, pending: int, total: int, skipped=()) -> None:
        self._append("=" * 68)
        self._append(f"{self._theme}  [{self._site}]")
        self._append(f"Run started:  {_now()}  ({pending}/{total} pending)")
        for sk in skipped:
            self._append(
                f"SKIPPED by the sheet (L{sk.line}): {sk.title} —"
                f" {sk.reason}"
            )
        self._append("-" * 68)

    def item(
        self,
        drop_path: str,
        gen_s: float,
        over_s: float,
        orig_res: str,
        final_res: str,
        size_bytes: int,
        actions: list[str],
    ) -> None:
        self._gen_times.append(gen_s)
        self._over_times.append(over_s)
        note = f"  [{', '.join(actions)}]" if actions else ""
        resolution = (
            f"{orig_res} -> {final_res}"
            if final_res not in ("", orig_res)
            else orig_res
        )
        self._append(
            f"{_now()}  {drop_path:<44} gen {gen_s:6.1f}s"
            f"  ours {over_s:6.1f}s  {resolution:>21}"
            f"  {fmt_size(size_bytes):>8}{note}"
        )

    def refused(self, drop_path: str, reason: str) -> None:
        self._refused += 1
        self._append(f"{_now()}  {drop_path:<44} REFUSED — {reason[:120]}")

    def finish(self, generated: int, wall_s: float, stopped_why: str) -> None:
        self._append("-" * 68)
        if self._refused:
            self._append(
                f"Refused: {self._refused} image(s) — rework those"
                " prompts in the sheet (or intervene manually) and rerun"
            )
        if self._gen_times:
            n = len(self._gen_times)
            avg_gen = sum(self._gen_times) / n
            avg_over = sum(self._over_times) / n
            self._append(
                f"Images: {generated}  |  average generation (AI):"
                f" {fmt_duration(avg_gen)}/image  |  average our time"
                f" (save+bgfix+pause): {fmt_duration(avg_over)}/image"
            )
            self._append(
                "Total AI + our time:"
                f" {fmt_duration(sum(self._gen_times) + sum(self._over_times))}"
                f"  (wall clock: {fmt_duration(wall_s)})"
            )
        else:
            self._append("Images: 0")
        self._append(f"Run finished: {_now()}  ({stopped_why})")
        self._append("")


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
    prompt_suffix: str | Callable[[str], str] = "",
    extra_suffix: dict[str, str] | None = None,
    report: bool = True,
    only: set[str] | None = None,
    on_event: OnEvent | None = None,
    safer_retry: bool = False,
    continue_nudge: bool = True,
    image_failed_retry: bool = True,
    new_chat_per_folder: bool = False,
) -> int:
    """Generate every pending item of a clean sheet; returns the count.

    Saves land at ``out_base / dest_for(drop, site_key)`` — the
    assets-mirroring layout. The report lives under
    ``out_base/_state/<site>/`` so the image tree stays copy-ready.
    The caller has already refused sheets with problems; skipped
    entries are logged here and never driven. ``only`` (the owner's
    ticked drop paths) narrows the queue to those items but NEVER
    overwrites a dest file already on disk — the folder is always the
    source of truth (owner 2026-07-21, after a restart regenerated 18
    already-saved images): a ticked item whose dest file exists is
    skipped exactly like the unattended (``only=None``) resume path,
    logged and added to the report. To redo a bad image the owner
    deletes the file first, then reruns (ticked or not). ``extra_suffix``
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

    for sk in sheet.skipped:
        log(f"  SKIP {sk.title} — {sk.reason}")

    # "Done" is the SAVED FILE itself, not a sidecar record (owner
    # 2026-07-19): an item is already done exactly when its dest file
    # exists on disk. The folder is ALWAYS the source of truth (owner
    # 2026-07-21): a ticked ``only`` selects WHICH items are candidates,
    # but never forces an overwrite of a file already on disk — to redo
    # a done image the owner deletes it first.
    def _on_disk(item) -> bool:
        return (out_base / dest_for(item.drop_path, site_key)).exists()

    report_skips = list(sheet.skipped)
    if only is not None:
        # the owner's ticks narrow the candidates; already-saved files
        # among them are still skipped — never regenerated by a tick alone
        ticked = [it for it in sheet.items if it.drop_path in only]
        if len(ticked) != len(sheet.items):
            log(
                f"  SELECTION: {len(ticked)}/{len(sheet.items)}"
                " item(s) ticked for this run"
            )
        queue = [it for it in ticked if not _on_disk(it)]
        already = len(ticked) - len(queue)
        if already:
            log(
                f"  RESUME: {already}/{len(ticked)} already saved"
                f" on disk under {site_key}/"
            )
            report_skips.extend(
                SkippedItem(it.title, "already saved on disk", it.line)
                for it in ticked
                if _on_disk(it)
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
    if run_report is not None:
        run_report.start(len(queue), len(sheet.items), tuple(report_skips))

    def emit(event: dict) -> None:
        if on_event is not None:
            on_event(event)

    def generate_one(text: str) -> tuple[bytes, float]:
        """Submit one prompt and return (image bytes, send timestamp).

        The send timestamp marks when SEND was pressed, so the caller
        can time the pure generation (send -> image) apart from the
        input hesitation inside submit_prompt.
        """
        driver.submit_prompt(text)
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

            # the suffix may depend on the prompt itself (Gemini's
            # aspect law: lancets portrait, badges square)
            suffix = (
                prompt_suffix(item.prompt)
                if callable(prompt_suffix)
                else prompt_suffix
            )
            # a PER-ITEM extra (the AI re-send fix note) rides at the
            # very end, after every site rule — and survives a safer
            # retry, which prepends its preamble to this same base
            extra = extra_suffix.get(item.drop_path) if extra_suffix else None
            if extra:
                suffix += "\n\n" + extra
            base = item.prompt + suffix
            retried = False  # True when the SAFER RETRY produced the image
            try:
                data, t_send = generate_one(base)
            except ItemRefused as exc:
                reason = str(exc)
                data = None
                if safer_retry:
                    log("    REFUSED — one safer retry (allegory note) ...")
                    emit({"type": "item_retry"})
                    try:
                        data, t_send = generate_one(SAFER_PREAMBLE + base)
                        retried = True
                        log("    safer retry SUCCEEDED")
                    except ItemRefused as exc2:
                        reason = str(exc2)
                if data is None:
                    refused += 1
                    log(f"    REFUSED — {reason}")
                    log(
                        "    continuing with the next item; rework the"
                        " prompt (or intervene manually) and rerun later"
                    )
                    if run_report is not None:
                        run_report.refused(item.drop_path, reason)
                    emit(
                        {
                            "type": "item_refused",
                            "drop_path": item.drop_path,
                        }
                    )
                    if idx < total:
                        _pause(timing, should_stop, log)
                    continue
            except NoImage:
                # ChatGPT stalled: the done edge fired but no image and no
                # marker matched. The owner's fix is a plain "continue"
                # nudge in the SAME chat — try it ONCE. On recovery the
                # nudge's own send time becomes t_send (gen_s is timed from
                # it); if the nudge STILL yields no image (or any other
                # DriverError — e.g. the nudge itself hits quota/refusal),
                # it propagates and the site stops loudly, exactly as before.
                if not continue_nudge:
                    raise
                log("    NO RESPONSE - nudging ChatGPT to continue (1 try) ...")
                emit({"type": "item_nudge", "drop_path": item.drop_path})
                data, t_send = generate_one(CONTINUE_NUDGE)
                log("    continue nudge RECOVERED")
            except ImageGenFailed as exc:
                # BUG 3: ChatGPT's OWN text already named the failure
                # ("Image generation failed ... reply with 'retry'")
                # while the busy/stop signal was still stuck — the
                # driver caught it WITHOUT burning the hard timeout.
                # Its own instructions say how to recover: resend the
                # word "retry" into the same chat, up to the configured
                # number of attempts, same skip-and-continue shape as a
                # safety refusal when it still won't budge.
                if not image_failed_retry:
                    raise
                reason = str(exc)
                data = None
                for attempt in range(1, IMAGE_FAILED_RETRY_MAX + 1):
                    log(
                        "    IMAGE GENERATION FAILED — sending"
                        f" '{IMAGE_RETRY_NUDGE}' ({attempt}/"
                        f"{IMAGE_FAILED_RETRY_MAX}) ..."
                    )
                    emit({"type": "item_retry"})
                    try:
                        data, t_send = generate_one(IMAGE_RETRY_NUDGE)
                        log("    retry RECOVERED")
                        break
                    except ImageGenFailed as exc2:
                        reason = str(exc2)
                        data = None
                if data is None:
                    refused += 1
                    log(f"    GENERATION FAILED — {reason}")
                    log(
                        "    continuing with the next item; rerun later"
                        " to retry"
                    )
                    if run_report is not None:
                        run_report.refused(item.drop_path, reason)
                    emit(
                        {
                            "type": "item_refused",
                            "drop_path": item.drop_path,
                        }
                    )
                    if idx < total:
                        _pause(timing, should_stop, log)
                    continue
            t_image = time.monotonic()
            gen_s = t_image - t_send

            dest = out_base / dest_for(item.drop_path, site_key)
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
                    "gen_s": gen_s,
                    "over_s": over_s,
                    "orig_res": orig_res,
                    "final_res": final_res,
                    "size": size,
                    "actions": action_str,
                    "retried": retried,
                }
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
