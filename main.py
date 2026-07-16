"""PromptPainter CLI — supervised image generation from a prompt sheet.

Usage:
    python main.py "path/to/theme_prompts.md" --site gemini
    python main.py "path/to/theme_prompts.md" --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from painter.config import CDP_URL, DEFAULT_OUT_DIR, SITES, TIMING
from painter.sheet_parser import Sheet, SheetError, parse_sheet


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="PromptPainter",
        description=(
            "Reads a prompt-sheet .md and drives the already-open,"
            " logged-in Gemini/ChatGPT tab over CDP — supervised, paced,"
            " resumable."
        ),
    )
    p.add_argument("sheet", type=Path, help="the prompt-sheet .md file")
    p.add_argument(
        "--site",
        choices=sorted(SITES),
        help="which open tab to drive (required unless --dry-run)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path(DEFAULT_OUT_DIR),
        help=f"output root (default: {DEFAULT_OUT_DIR}/)",
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

    timing = (
        TIMING
        if args.pause is None
        else replace(TIMING, pause_between_prompts_s=args.pause)
    )

    # imported lazily so --dry-run works without playwright installed
    from painter.driver import DriverError, SiteDriver, TerminalState
    from painter.runner import run_sheet

    driver = SiteDriver(SITES[args.site], timing, args.cdp)
    try:
        print(f"\nAttaching over CDP at {args.cdp} ...")
        title = driver.attach()
        print(f"Attached to {title!r}. SUPERVISED RUN — watch the window.")
        generated = run_sheet(sheet, driver, args.out, timing)
        print(f"\nDone: {generated} image(s) generated into {args.out}\\")
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
