"""PromptPainter — the single entry point.

No arguments -> opens the GUI (the usual way in). With sheet
arguments -> the CLI, driving ONE site through the given sheets in
order.

Usage:
    python main.py
    python main.py sheet1.md sheet2.md --site gemini
    python main.py "path/to/theme_prompts.md" --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from functools import partial
from pathlib import Path

from painter.config import (
    BACKGROUND_CHOICES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    NEW_CHAT_CHOICES,
    SITES,
    TIMING,
    fmt_duration,
    prompt_suffix,
)
from painter.sheet_parser import Sheet, SheetError, parse_sheet


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="PromptPainter",
        description=(
            "Reads prompt-sheet .md files and drives the logged-in"
            " Gemini/ChatGPT tab over CDP — supervised, paced, resumable."
        ),
    )
    p.add_argument(
        "sheets",
        type=Path,
        nargs="*",
        help="prompt-sheet .md files (omit everything to open the GUI)",
    )
    p.add_argument(
        "--site",
        choices=sorted(SITES),
        help="which site to drive (required unless --dry-run)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=(
            "output base; images save at <out>/<site>/<drop-path>"
            f" (default: {DEFAULT_OUT_DIR})"
        ),
    )
    p.add_argument(
        "--background",
        choices=BACKGROUND_CHOICES,
        default=None,
        help=(
            "background rule appended to every prompt (default: the"
            " site's own — transparent on ChatGPT, white on Gemini)"
        ),
    )
    p.add_argument(
        "--pause",
        type=float,
        nargs="+",
        default=None,
        metavar=("MIN", "MAX"),
        help=(
            "pause between prompts: one value = fixed, two = a random"
            " range (default:"
            f" {TIMING.pause_min_s:.0f}-{TIMING.pause_max_s:.0f}s)"
        ),
    )
    p.add_argument("--cdp", default=CDP_URL, help=f"CDP URL (default: {CDP_URL})")
    p.add_argument(
        "--no-bgfix",
        action="store_true",
        help="skip the background remover after each saved image",
    )
    p.add_argument(
        "--no-crop",
        action="store_true",
        help="skip the transparent autocrop after each saved image",
    )
    p.add_argument(
        "--upscale",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Real-ESRGAN upscale of small near-square images (badge"
            " class) so no dimension stays below the configured"
            " minimum (default: on; --no-upscale to skip)"
        ),
    )
    p.add_argument(
        "--no-report",
        action="store_true",
        help="do not write the per-sheet report txt",
    )
    p.add_argument(
        "--new-chat",
        choices=NEW_CHAT_CHOICES,
        default="collection",
        help=(
            "open a fresh chat after every collection, also between"
            " folder groups, or never (default: collection)"
        ),
    )
    p.add_argument(
        "--safer-retry",
        action="store_true",
        help=(
            "on a SAFETY refusal, retry the item ONCE with an"
            " allegory-framing preamble before giving up"
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report the sheets only — no browser needed",
    )
    return p


def report_sheet(sheet: Sheet) -> None:
    print(f"THEME: {sheet.theme}")
    print(
        f"  {len(sheet.items)} to generate, {len(sheet.skipped)} skipped,"
        f" {len(sheet.problems)} problem(s)"
    )
    for it in sheet.items:
        print(f"  GEN  L{it.line:<4} {it.drop_path}  ({len(it.prompt)} ch)")
    for sk in sheet.skipped:
        print(f"  SKIP L{sk.line:<4} {sk.title} — {sk.reason}")
    for pr in sheet.problems:
        print(f"  PROBLEM L{pr.line}: {pr.message}")


def _build_post_save(do_bg: bool, do_crop: bool, do_upscale: bool):
    """The composed per-save hook (owner's #7: steps are flags).

    Returns the hook callable, None when every step is off, or the
    deps-problem STRING when the steps cannot run at all.
    """
    if not (do_bg or do_crop or do_upscale):
        return None

    # imported lazily so --dry-run stays stdlib-only
    from painter.postprocess import (
        crop_transparent,
        deps_error,
        remove_background,
    )

    problem = deps_error()
    if problem:
        return problem
    if do_upscale:
        from painter.upscale import upscale_if_small

    def post_save(path: Path) -> str:
        parts = []
        if do_bg:
            parts.append(f"REMOVE BG: {remove_background(path, print)}")
        if do_crop:
            parts.append(f"CROP: {crop_transparent(path, print)}")
        if do_upscale:
            parts.append(f"UPSCALE: {upscale_if_small(path, print)}")
        return ", ".join(parts)

    return post_save


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.sheets:
        import gui

        gui.main()
        return 0

    sheets: list[Sheet] = []
    broken = 0
    for path in args.sheets:
        try:
            sheet = parse_sheet(path)
        except (SheetError, OSError) as exc:
            print(f"SHEET SKIPPED: {exc}", file=sys.stderr)
            broken += 1
            continue
        report_sheet(sheet)
        if sheet.problems:
            print(
                f"SHEET SKIPPED (contract problems): {path.name} — fix"
                " the sheet and rerun.",
                file=sys.stderr,
            )
            broken += 1
            continue
        sheets.append(sheet)

    if args.dry_run:
        return 2 if broken else 0
    if not sheets:
        print("ERROR: no usable sheets.", file=sys.stderr)
        return 2
    if not args.site:
        print("ERROR: --site is required (or use --dry-run)", file=sys.stderr)
        return 2

    out_base = args.out.resolve()
    for sheet in sheets:
        if sheet.source.resolve().is_relative_to(out_base):
            print(
                f"ERROR: {sheet.source.name} lives inside the output"
                " folder — sources are READ ONLY; pick another output.",
                file=sys.stderr,
            )
            return 2

    post_save = _build_post_save(
        do_bg=not args.no_bgfix,
        do_crop=not args.no_crop,
        do_upscale=args.upscale,
    )
    if isinstance(post_save, str):  # a deps problem, not a hook
        print(
            f"ERROR: {post_save}\n(or rerun with --no-bgfix --no-crop"
            " --no-upscale)",
            file=sys.stderr,
        )
        return 2

    if args.pause is None:
        timing = TIMING
    else:
        low = args.pause[0]
        high = args.pause[-1]
        if low > high:
            print("ERROR: --pause MIN must be <= MAX", file=sys.stderr)
            return 2
        timing = replace(TIMING, pause_min_s=low, pause_max_s=high)
    site = SITES[args.site]
    background = args.background or site.default_background
    suffix = partial(prompt_suffix, args.site, background)

    # imported lazily so --dry-run works without playwright installed
    from painter.chrome import ChromeError, ensure_chrome
    from painter.driver import DriverError, SiteDriver, TerminalState
    from painter.runner import run_sheet

    try:
        state = ensure_chrome((site.url,), args.cdp)
    except ChromeError as exc:
        print(f"CHROME ERROR: {exc}", file=sys.stderr)
        return 1
    if state == "launched":
        print(
            "Chrome opened with the PromptPainter profile — log in on the"
            f" {site.name} tab if needed, then rerun this command."
        )
        return 0

    driver = SiteDriver(site, timing, args.cdp)
    try:
        print(f"\nAttaching over CDP at {args.cdp} ...")
        title = driver.attach()
        print(f"Attached to {title!r}. SUPERVISED RUN — watch the window.")
        total = 0
        for n, sheet in enumerate(sheets, start=1):
            print(f"\n--- sheet {n}/{len(sheets)}: {sheet.source.name} ---")
            generated = run_sheet(
                sheet,
                driver,
                out_base,
                args.site,
                timing,
                post_save=post_save,
                prompt_suffix=suffix,
                report=not args.no_report,
                safer_retry=args.safer_retry,
                new_chat_per_folder=(args.new_chat == "folder"),
            )
            total += generated
            if (
                args.new_chat in ("collection", "folder")
                and generated
                and n < len(sheets)
            ):
                try:
                    driver.new_chat()
                except Exception as exc:
                    print(f"NEW CHAT FAILED (continuing): {exc}")
        print(
            f"\nDone: {total} image(s) across {len(sheets)} sheet(s)"
            f" into {out_base}"
        )
        return 2 if broken else 0
    except TerminalState as exc:
        when = (
            f" — quota resets in ~{fmt_duration(exc.retry_after_s)}"
            if exc.retry_after_s is not None
            else ""
        )
        print(
            f"\nTERMINAL STATE: {exc}\n"
            f"Run stopped; finished work is saved — rerun later to"
            f" resume{when}.",
            file=sys.stderr,
        )
        return 3
    except DriverError as exc:
        print(
            f"\nDRIVER ERROR: {exc}\n"
            "Progress is saved — rerun to resume once the cause is fixed.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print(
            "\nInterrupted — progress is saved; rerun to resume.",
            file=sys.stderr,
        )
        return 130
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
