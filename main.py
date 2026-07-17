"""PromptPainter — the single entry point.

No arguments -> opens the GUI (the usual way in). With a sheet
argument -> the CLI, driving ONE site per invocation.

Usage:
    python main.py
    python main.py "path/to/theme_prompts.md" --site gemini
    python main.py "path/to/theme_prompts.md" --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from painter.config import (
    BACKGROUND_MODES,
    CDP_URL,
    DEFAULT_OUT_DIR,
    SITES,
    TIMING,
    background_suffix,
)
from painter.sheet_parser import Sheet, SheetError, parse_sheet


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="PromptPainter",
        description=(
            "Reads a prompt-sheet .md and drives the logged-in"
            " Gemini/ChatGPT tab over CDP — supervised, paced, resumable."
        ),
    )
    p.add_argument(
        "sheet",
        type=Path,
        nargs="?",
        help="the prompt-sheet .md file (omit everything to open the GUI)",
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
            "output base; generation stages at <out>/_staging/<site>/,"
            " approval moves images to <out>/<site>/<drop-path>"
            f" (default: {DEFAULT_OUT_DIR})"
        ),
    )
    p.add_argument(
        "--background",
        choices=BACKGROUND_MODES,
        default="auto",
        help=(
            "background suffix appended to every prompt — auto ="
            " transparent on ChatGPT, white on Gemini (default: auto)"
        ),
    )
    p.add_argument(
        "--approve-all",
        action="store_true",
        help=(
            "skip the review phase: move every staged image of this run"
            " straight to the final folder"
        ),
    )
    p.add_argument(
        "--pause",
        type=float,
        default=None,
        help=(
            "seconds between prompts (default:"
            f" {TIMING.pause_between_prompts_s:.0f})"
        ),
    )
    p.add_argument("--cdp", default=CDP_URL, help=f"CDP URL (default: {CDP_URL})")
    p.add_argument(
        "--no-bgfix",
        action="store_true",
        help="skip the background tool after each saved image",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report the sheet only — no browser needed",
    )
    return p


def report(sheet: Sheet) -> None:
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.sheet is None:
        import gui

        gui.main()
        return 0

    try:
        sheet = parse_sheet(args.sheet)
    except (SheetError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report(sheet)
    if sheet.problems:
        print(
            "\nThe sheet violates the contract — fix the sheet, then rerun.",
            file=sys.stderr,
        )
        return 2
    if args.dry_run:
        return 0
    if not args.site:
        print("ERROR: --site is required (or use --dry-run)", file=sys.stderr)
        return 2

    from painter.review import approve, staged_images, staging_root

    out_base = args.out.resolve()
    out_root = staging_root(out_base, args.site)
    if sheet.source.resolve().is_relative_to(out_base):
        print(
            "ERROR: the sheet lives inside the output folder — sources"
            " are READ ONLY; pick another output folder.",
            file=sys.stderr,
        )
        return 2

    post_save = None
    if not args.no_bgfix:
        from painter.postprocess import deps_error, fix_background

        problem = deps_error()
        if problem:
            print(
                f"ERROR: {problem}\n(or rerun with --no-bgfix)",
                file=sys.stderr,
            )
            return 2
        post_save = fix_background

    timing = (
        TIMING
        if args.pause is None
        else replace(TIMING, pause_between_prompts_s=args.pause)
    )
    suffix = background_suffix(args.background, SITES[args.site])

    # imported lazily so --dry-run works without playwright installed
    from painter.chrome import ChromeError, ensure_chrome
    from painter.driver import DriverError, SiteDriver, TerminalState
    from painter.runner import run_sheet

    site = SITES[args.site]
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
        generated = run_sheet(
            sheet,
            driver,
            out_root,
            timing,
            post_save=post_save,
            prompt_suffix=suffix,
        )
        staged = staged_images(out_base, (args.site,))
        if args.approve_all:
            for item in staged:
                approve(out_base, item)
            print(
                f"\nDone: {generated} image(s) generated,"
                f" {len(staged)} approved into {out_base / args.site}"
            )
        else:
            print(
                f"\nDone: {generated} image(s) generated;"
                f" {len(staged)} await review in {out_root}\n"
                "Review them in the GUI ('Review staged') or rerun with"
                " --approve-all."
            )
        return 0
    except TerminalState as exc:
        print(
            f"\nTERMINAL STATE: {exc}\n"
            "Run stopped; progress is saved — rerun later to resume.",
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
