"""Pure, Tk-free module-level logic pulled out of ``gui/__init__.py``
(god-file refactor, Rule #20): the shared-filter engine helpers, the
per-image post-save pipeline runner, legacy settings migrations, the
fixer auto-dispatch decision, and small pure view-layout helpers
(``_menu_tile_columns``/``_next_view``/``_visible_agent_columns``) plus
the dashboard's ``_scope_stats``. Every function here takes plain
values (paths, dicts, duck-typed objects) and returns plain values —
no widget is ever built or touched, so this module is directly
unit-testable with no Tk display required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image

from painter import filters, jobtemp
from painter.config import (
    ASPECT_FILTER_DEFAULT_FROM,
    ASPECT_FILTER_DEFAULT_TO,
    ASPECT_FILTER_IF,
    ASPECT_FILTER_IF_NOT,
    ASPECT_FILTER_OFF,
    FILTER_KIND_ASPECT_EXACT,
    FILTER_KIND_ASPECT_RANGE,
    FILTER_POLARITY_IF,
    FILTER_POLARITY_IF_NOT,
    FIXER_MODE_WEBSITE,
    MENU_TILE_COLS,
    MENU_TILE_GAP_PX,
    MENU_TILE_W,
)

# --- Main Menu (GUI rework Phase 10) — the tile-grid column floor,
# shared by _menu_tile_columns (below) and MainMenu._reflow (gui/
# __init__.py), which re-imports it — the two must always agree, or a
# stricter grid floor than this function assumed would make the grid
# wider than the (non-horizontally-scrollable) viewport itself.
MENU_TILE_CELL_MIN_PX = MENU_TILE_W + MENU_TILE_GAP_PX + 24

# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------

# the stat keys shown per scope (the 'Average' group sits between
# Refused and Tempo and collapses)
_STAT_KEYS = ("done", "refused", "total", "gen", "over", "tmin", "tmax",
              "tempo", "eta")


def _scope_stats(
    done, refused, gen_times, over_times, totals, pending, elapsed
):
    """Display strings for one scope (a collection or the whole task).

    ``totals`` are per-image AI+our seconds (only for images whose our
    time is known), so the total average / min / max are exact.
    """
    remaining = max(pending - done - refused, 0)

    def avg(xs):
        return f"{sum(xs) / len(xs):.0f} s" if xs else "—"

    if done and elapsed > 0:
        tempo = f"{done / (elapsed / 3600):.0f} /h"
        eta = (
            f"{remaining * (elapsed / done) / 60:.0f} min"
            if remaining
            else "done"
        )
    else:
        tempo = "—"
        eta = "—"
    return {
        "done": f"{done}/{pending}" if pending else str(done),
        "refused": str(refused),
        "total": avg(totals),
        "gen": avg(gen_times),
        "over": avg(over_times),
        "tmin": f"{min(totals):.0f} s" if totals else "—",
        "tmax": f"{max(totals):.0f} s" if totals else "—",
        "tempo": tempo,
        "eta": eta,
    }


# ---------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------

def _filter_files(
    files: list[Path], conditions: list[filters.FilterCondition],
    log: Callable[[str], None],
) -> list[Path]:
    """Keep only the paths whose CURRENT pixel size passes the stacked
    filter (``painter.filters.matches`` — AND across every condition,
    owner decision 2026-07-21). An empty ``conditions`` list is a
    no-op — the common case — and opens nothing; the raw ``files``
    list comes back unchanged. A path PIL cannot open is EXCLUDED with
    a loud log line rather than aborting the whole picker (root Rule
    #1/#7: the caller's file dialog is external input — e.g. an
    "All files" pick could include a non-image by mistake)."""
    if not conditions:
        return list(files)
    kept = []
    for path in files:
        try:
            with Image.open(path) as im:
                width, height = im.size
        except Exception as exc:
            log(f"FILTER: cannot read {path.name} ({exc}) — excluded")
            continue
        if filters.matches(width, height, conditions):
            kept.append(path)
    return kept


def _parse_condition_dicts(
    dicts: list, log: Callable[[str], None]
) -> list[filters.FilterCondition]:
    """Best-effort parse of a JSON-loaded condition-dict list
    (settings.json's ``aspect_filter_conditions`` or a preset) into
    ``FilterCondition``s. A malformed entry is DROPPED with a loud log
    line rather than crashing the whole settings load — mirrors
    ``painter.settings.load_settings``'s own "a corrupt file loses the
    remembered choice, never the app" precedent, applied to one key."""
    out = []
    for d in dicts:
        try:
            out.append(filters.condition_from_dict(d))
        except (TypeError, KeyError, ValueError) as exc:
            log(f"SETTINGS: dropping unreadable filter condition {d!r} ({exc})")
    return out


def _migrate_legacy_aspect_filter(stored: dict) -> list[dict]:
    """One-time migration (GUI rework Phase 4, owner decision
    2026-07-21): the OLD scalar aspect-tool filter — settings.json's
    ``aspect_filter`` key, ``{"from": float, "to": float, "mode":
    ASPECT_FILTER_OFF/_IF/_IF_NOT}`` — into the NEW stacked-conditions
    shape (a list of ``painter.filters.condition_to_dict`` dicts, the
    same JSON shape ``aspect_filter_conditions`` and a saved preset
    both use).

    ``off`` carried no filtering, so it becomes an EMPTY list — an
    empty conditions list already matches everything, no special-
    casing needed downstream. ``IF``/``IF NOT`` becomes exactly ONE
    ``FILTER_KIND_ASPECT_RANGE`` condition with the SAME from/to/
    polarity numbers: ``matches()``'s ``lo <= ratio <= hi`` containment
    (IF) / its negation (IF NOT) is arithmetically identical to
    ``change_aspect``'s own old ``filter_from <= cur <= filter_to``
    check, so behaviour is preserved exactly, only the container shape
    changes. Pure and Tk-free (no ``self``, no widget) — callable
    straight from a settings dict, e.g. the owner's real
    ``{"from": 0.9, "to": 1.1, "mode": "IF NOT"}``.

    Raises ``ValueError`` loudly (root Rule #1) on an unrecognised
    ``mode`` string — a scenario the OLD dialog itself could never
    have written, so this is corrupt/foreign data, not a case to
    silently coerce; the caller (``PainterGui._apply_settings``)
    catches it and falls back to no filter, same as any other corrupt
    settings.json value."""
    mode = stored.get("mode", ASPECT_FILTER_OFF)
    if mode == ASPECT_FILTER_OFF:
        return []
    if mode not in (ASPECT_FILTER_IF, ASPECT_FILTER_IF_NOT):
        raise ValueError(f"unrecognised legacy aspect_filter mode: {mode!r}")
    lo = float(stored.get("from", ASPECT_FILTER_DEFAULT_FROM))
    hi = float(stored.get("to", ASPECT_FILTER_DEFAULT_TO))
    polarity = (
        FILTER_POLARITY_IF_NOT if mode == ASPECT_FILTER_IF_NOT
        else FILTER_POLARITY_IF
    )
    return [filters.condition_to_dict(filters.FilterCondition(
        kind=FILTER_KIND_ASPECT_RANGE, polarity=polarity, lo=lo, hi=hi,
    ))]


def _upscale_params_from_side_and_filter(
    min_side: int, conditions: list[filters.FilterCondition],
) -> dict:
    """The upscale gate's min-SIDE spinner + its embedded FilterEditor's
    condition stack -> ``upscale_if_small``'s four kwargs (GUI rework
    Phase 6, replacing the old four-field ``up_minw``/``up_minh``/
    ``up_aspmin``/``up_aspmax`` gate). ``min_side`` becomes BOTH
    ``min_width`` and ``min_height`` — the gate no longer distinguishes
    the two axes (owner decision); the shipped default already had them
    equal at 800px, so the default case behaves byte-identically.

    ``aspect_min``/``aspect_max`` are read off the FIRST Aspect (exact
    or range — ``filters.py`` treats the two identically, see its own
    docstring) condition in the stack whose polarity is IF: an exact
    algebraic match for what ``upscale_if_small`` already means by
    "qualifies" (``aspect_min <= W/H <= aspect_max``). NO such
    condition — the owner deleted the aspect row, or set it to IF NOT,
    a shape ``upscale_if_small``'s plain ``[lo, hi]`` pair cannot
    express — widens to ``(0, inf)``: every aspect ratio qualifies for
    the size gate alone.

    IMPORTANT — this is a deliberately PARTIAL translation, never the
    full story (root Rule #1: never silently drop a condition).
    ``upscale_if_small`` has no kwarg for a Width/Height/Any-side
    condition, a SECOND aspect condition, or an IF-NOT aspect condition
    — anything in ``conditions`` beyond the one this function folds in
    is the CALLER's responsibility to enforce separately via
    ``filters.matches()`` against the FULL, unmodified ``conditions``
    list before ever invoking ``upscale_if_small`` with this function's
    output. See ``_gate_and_upscale`` (the per-image site-pipeline
    gate) and ``UpscaleSettingsPanel.build_func``'s caller (the
    standalone tool's pre-filtered file list, via ``_filter_files`` in
    ``PainterGui._start_tool_from_panel``) — both call sites apply
    that gate; this function alone would silently ignore every
    non-aspect condition, so it is never used alone.
    """
    aspect_min, aspect_max = 0.0, float("inf")
    for c in conditions:
        if (
            c.kind in (FILTER_KIND_ASPECT_EXACT, FILTER_KIND_ASPECT_RANGE)
            and c.polarity == FILTER_POLARITY_IF
        ):
            aspect_min, aspect_max = c.lo, c.hi
            break
    return {
        "min_width": min_side,
        "min_height": min_side,
        "aspect_min": aspect_min,
        "aspect_max": aspect_max,
    }


def _gate_and_upscale(
    path: Path, log: Callable[[str], None],
    conditions: list[filters.FilterCondition], params: dict,
) -> str:
    """``upscale_if_small`` for ONE already-saved image, gated on the
    FULL stacked filter FIRST (GUI rework Phase 6, root Rule #1): any
    condition beyond the single aspect row ``_upscale_params_from_
    side_and_filter`` already folded into ``params`` — a stacked Width/
    Height/Any-side row, a second aspect row, or an IF-NOT aspect row —
    must still gate the image, losslessly. Used by the PER-SITE
    pipeline (``PainterGui._compose_post_save``), which has no upfront
    file list to pre-filter (each image is gated as it is saved); the
    STANDALONE Upscale tool instead pre-filters its whole file list
    once via ``_filter_files`` (same ``conditions``, same
    ``filters.matches()`` engine, applied to a list instead of one
    path).

    An empty ``conditions`` list — the FilterEditor's own "no filter,
    process everything" contract — skips the extra ``Image.open`` and
    goes straight to ``upscale_if_small``; the common seeded-default
    gate (one Aspect condition) DOES open the image here as well as
    inside ``upscale_if_small`` itself — a harmless redundant re-check
    (both read the SAME aspect band), not a bug: correctness over a
    micro-optimisation on a path that already waits multiple seconds
    per image for the site's own generation (root Priority A is about
    hot paths; this is not one)."""
    if conditions:
        with Image.open(path) as im:
            width, height = im.size
        if not filters.matches(width, height, conditions):
            return "nothing"
    from painter.upscale import upscale_if_small

    return upscale_if_small(path, log, **params)


def _run_pipeline_steps(
    path: Path,
    steps: list[tuple[str, str, Callable[[Path], str]]],
    temp: "jobtemp.JobTemp | None",
    keep_all_steps: bool,
    on_cap: Callable[[], None],
) -> str:
    """Run each ENABLED post-save STEP over one already-saved image, in
    order, composing the runner's action-string description ("REMOVE
    BG: done, CROP: done, ...") — the per-image engine of
    ``PainterGui._compose_post_save`` (GUI rework Phase 8's reordered
    BG -> Crop -> Aspect -> Upscale pipeline). ``steps`` is the
    caller-built ``(label, step_name, fn)`` triples for whichever
    switches are on, in PIPELINE order; ``fn`` is already a plain
    ``path -> status`` callable (its own log sink bound at the call
    site), so this function stays engine-agnostic — it never imports
    postprocess/aspect/upscale itself.

    When ``temp`` (a JobTemp) is attached, each step's PRE-state is
    backed up first:

    * the FIRST enabled step's pre-state is tagged ``step="original"``
      — the pristine, restore-everything baseline (the runner's raw
      just-saved image, before the pipeline touches it at all) — and is
      ALWAYS taken, cap or toggle or not, so every image keeps at LEAST
      this one restore point. This DELIBERATELY DEDUPS against that
      first step's own name (owner ask, GUI rework Phase 8: "avoid a
      pointless duplicate when original == the first step's pre-
      state") — the two would be byte-identical backups of the exact
      same instant, so only ONE is ever written. A caller reading
      ``steps_for()`` should expect the first ENABLED step's own name
      to be ABSENT from the list — "original" already covers that
      instant; see the ``JOBTEMP_STEP_NAMES`` ordering-contract
      comment in painter/config.py, which already frames "original" as
      captured "before the pipeline touches the file at all" (i.e. not
      tied to any one step's name).
    * every LATER enabled step's pre-state gets its OWN named backup
      ("bg"/"crop"/"aspect"/"upscale") — but only when ``keep_all_
      steps`` is True AND the job is not yet ``over_cap()``. Once over
      cap, NEW per-step backups stop (the "original-only" fallback)
      and ``on_cap()`` fires; when ``keep_all_steps`` is False (the
      owner's own choice, not an emergency), the same skip happens
      SILENTLY — ``on_cap()`` is reserved for the cap, never the
      toggle. The caller turns a real cap hit into the loud persistent
      dashboard banner (see DashPanel's "over_cap" event).
    * a step backed up under its OWN name whose result was "nothing" (a
      genuine no-op — before == after) has that backup DROPPED right
      back, mirroring the four standalone tools' own restore-point
      hygiene (``PainterGui._run_tool_job``): a no-op leaves nothing
      worth restoring. "original" is NEVER dropped, whatever any step's
      own outcome — it is the restore-all target regardless.

    With ``temp is None`` (no JobTemp attached — never happens once
    ``_start_site`` has run, but keeps this function usable headless in
    tests) every step still runs normally; only the backup bookkeeping
    is skipped.
    """
    rel = path.relative_to(temp.folder).as_posix() if temp is not None else ""
    parts = []
    took_original = False
    for label, step_name, fn in steps:
        backed_up_as = None
        if temp is not None:
            if not took_original:
                temp.backup(path, rel, step="original")
                took_original = True
            elif not keep_all_steps:
                pass  # the owner's own choice — silent skip, no banner
            elif not temp.over_cap():
                temp.backup(path, rel, step=step_name)
                backed_up_as = step_name
            else:
                on_cap()
        status = fn(path)
        if backed_up_as is not None and status != "done":
            temp.drop(rel, step=backed_up_as)  # a no-op — nothing to restore
        parts.append(f"{label}: {status}")
    return ", ".join(parts)


def _migrate_legacy_upscale_gate(min_width, aspect_min, aspect_max) -> dict:
    """One-time migration (GUI rework Phase 6, owner decision
    2026-07-21): the OLD three upscale-gate numbers — a min WIDTH (min
    HEIGHT is DROPPED; the two axes collapse into ONE min-SIDE spinner,
    and every shipped default and every real settings.json seen so far
    already had width == height, so nothing observable is lost in
    practice) and an aspect ``[from, to]`` band — into the NEW neutral
    shape ``{"min_side": int, "conditions": [ONE Aspect (range)
    condition dict, IF polarity, the SAME band]}``.

    Shared by BOTH migration call sites — the per-agent ``up_minw``/
    ``up_aspmin``/``up_aspmax`` fields AND the standalone tool's
    ``upscale_tool`` dict's ``min_width``/``aspect_min``/``aspect_max``
    — same numbers, same target shape, only the SOURCE key names
    differ; each caller extracts its own three values (defaulting a
    missing key to today's shipped default) and hands them here. The
    returned dict's field names are neutral (not tied to either
    caller's own persisted-JSON key names — the per-agent caller writes
    them into ``up_minside``/``up_filter_conditions`` as STRINGS/lists,
    the standalone caller keeps ``min_side`` as a plain int matching
    ``UpscaleParamsDialog.result``'s own shape).

    Raises ``ValueError``/``TypeError`` loudly (root Rule #1) when a
    value will not convert to a number — mirrors ``_migrate_legacy_
    aspect_filter``'s own precedent exactly (missing key -> the caller
    already substituted a default before calling this; PRESENT but
    unparsable -> loud, the caller catches and falls back to the
    shipped default gate, never crashes the app on a hand-corrupted
    settings.json)."""
    min_side = int(float(min_width))
    lo = float(aspect_min)
    hi = float(aspect_max)
    return {
        "min_side": min_side,
        "conditions": [
            filters.condition_to_dict(filters.FilterCondition(
                kind=FILTER_KIND_ASPECT_RANGE, polarity=FILTER_POLARITY_IF,
                lo=lo, hi=hi,
            ))
        ],
    }


def _visible_agent_columns(
    order: list[str], visible: dict[str, bool],
) -> dict[str, int]:
    """Left-to-right column index for each VISIBLE key in ``order`` (GUI
    rework Phase 12, spec item 3A: either site's AgentPanel can be
    hidden so only the other stays on screen). A hidden key
    (``visible.get(key, True)`` is False) is simply ABSENT from the
    result — the remaining visible panel(s) compact toward column 0
    instead of leaving a dead gap where the hidden one used to sit, e.g.
    ChatGPT hidden, Gemini alone -> ``{"gemini": 0}``, never
    ``{"gemini": 1}``. Both visible -> ``{"chatgpt": 0, "gemini": 1}``;
    both hidden (never reached in practice — set_run_state forces a
    running site back to visible, and a site that never ran can still
    be hidden by hand, which IS a legal "nothing showing" state) ->
    ``{}``.

    Pure and Tk-free — ``PainterGui._relayout_agents`` is the only
    caller, applying the result to real ``grid()``/``grid_remove()``
    calls plus each column's weight (0 for an unused column so the
    visible one(s) expand into the freed width, the same reset-then-
    reassign technique ``DashGrid.relayout`` already uses)."""
    cols: dict[str, int] = {}
    i = 0
    for key in order:
        if visible.get(key, True):
            cols[key] = i
            i += 1
    return cols


# ---------------------------------------------------------------------
# Fixer AI — auto-dispatch decision (GUI rework Phase 20)
# ---------------------------------------------------------------------


def _fixer_decision(agent, event: dict) -> str:
    """The auto-fixer's PURE decision (owner's UV/prompt.txt item 1:
    "ako ustanovi gresku salje fikseru da ispravi ... u situaciji ako su
    oba ukljucena") — given ONE site's fixer switches (duck-typed: only
    ``.fixer_var``/``.fixer_mode_var`` are read, so a test's bare fake
    needs no full ``AgentPanel`` — the SAME convention
    ``_upscale_params_from_side_and_filter`` etc. already use) and an
    ``item_checked`` event, what should ``PainterGui._maybe_spawn_fixer``
    do next? Tk-free — the whole branch table is a headless test.

    * ``"none"`` — the fixer switch is off, or this image was not
      flagged (kind != "flagged" or an empty defects list) — nothing to
      fix.
    * ``"api"`` — dispatch ``ai.edit_image`` on a background thread
      RIGHT NOW: a plain REST call, so it genuinely overlaps the site's
      OWN next-image generation (the intended parallel flow).
    * ``"website_queue"`` — the owner wants a WEBSITE fix, but the
      site's browser tab is busy generating the next image at this
      exact instant (one tab, one operation) — NEVER driven from here;
      queued instead (see ``PainterGui._queue_website_fix``).
    """
    if not agent.fixer_var.get():
        return "none"
    if event.get("kind") != "flagged" or not event.get("defects"):
        return "none"
    if agent.fixer_mode_var.get() == FIXER_MODE_WEBSITE:
        return "website_queue"
    return "api"


def _fix_result_ui(
    which: str, result: tuple[str, str],
) -> tuple[str, bool | None, bool | None]:
    """The MANUAL fix buttons' pure result-to-UI mapping (GUI rework
    Phase 20) — behind ``DocWindow._apply_fix_result``, kept Tk-free so
    the enable/disable/status-text table is a headless test (gui.py's
    own established "pure helpers get pytest, real Tk/UI wiring gets a
    screenshot" split — no test in this suite ever constructs a real
    ``tk.Toplevel``). ``which`` is "image" or "website" (which button's
    background worker produced ``result``); ``result`` is the
    ``(kind, message)`` pair ``_run_image_fix``/``_run_website_fix``
    return. Returns ``(status_text, enable_image, enable_website)`` —
    ``None`` for either flag means "leave that button exactly as
    ``DocWindow._run_fix`` already left it" (both disabled, mid-fix).

    * ``"ok"`` — both stay disabled (``None``, ``None``): this report is
      now STALE (the image just changed) — a fresh Check… is the honest
      next step, never a second blind fix off the same old defects.
    * ``"gated"`` — PERMANENT for the button that fired (stays
      disabled); the OTHER path may still work, so it re-enables.
    * anything else (``"error"``) — TRANSIENT (e.g. the site is
      currently generating) — both re-enable, retry-able.
    """
    kind, message = result
    if kind == "ok":
        return (f"Fixed — {message}", None, None)
    if kind == "gated":
        if which == "image":
            return (message, None, True)   # image stays off; website may work
        return (message, True, None)       # website stays off; image may work
    return (f"Fix failed: {message}", True, True)  # "error" — retry-able


# ---------------------------------------------------------------------
# Main Menu (GUI rework Phase 10)
# ---------------------------------------------------------------------

def _menu_tile_columns(width_px: int, tile_count: int) -> int:
    """How many ``MENU_TILES`` columns fit ``width_px`` without
    shrinking a tile below ``MENU_TILE_CELL_MIN_PX`` (owner 2026-07-21
    workflow fix — the grid used to hardcode ``MENU_TILE_COLS`` columns
    regardless of the actual window width; at the narrow end of
    ``WINDOW_MIN_W`` a slightly different font/DPI/scrollbar width was
    enough to clip or overflow the fixed 4-wide layout). ``MainMenu.
    _reflow`` enforces the SAME per-column floor as a real Tk
    ``minsize`` — the two must always agree, or a stricter grid floor
    than this function assumed would make the grid wider than the
    (non-horizontally-scrollable) viewport itself, trading one clipping
    failure mode for another at the right edge. Never more than
    ``MENU_TILE_COLS`` (today's ideal 4x2 layout for 8 tiles) or more
    than ``tile_count`` itself (no empty trailing columns), never fewer
    than 1. ``width_px <= 0`` (no real measurement yet, e.g. the very
    first pack before any ``<Configure>`` fires) falls back to the
    ideal layout, exactly like today's fixed default. Pure, Tk-free —
    mirrors ``_visible_agent_columns``/``_next_view``'s own split (the
    Tk-facing half, ``MainMenu._reflow``, is proven by a real-window
    screenshot, matching gui.py's established convention for widget
    geometry — see ___tests.md)."""
    ideal = min(MENU_TILE_COLS, max(1, tile_count))
    if width_px <= 0:
        return ideal
    fit = max(1, width_px // MENU_TILE_CELL_MIN_PX)
    return min(ideal, fit)


def _next_view(
    current: str, active_count: int, menu_requested: bool = False,
) -> str:
    """Pure view-transition decision (GUI rework Phase 11) — no Tk, so
    it is unit-testable on its own. ``current`` is today's
    ``PainterGui._view`` ("menu" / "main" / "running"); ``active_count``
    is ``len(PainterGui._active_kinds())`` — every JOB_ORDER kind with a
    live worker right now; ``menu_requested`` is True only on an
    explicit Menu-button click (the pinned top-strip one outside
    "running", IconBar's own copy during it).

    Rules (owner 2026-07-21, binding design doc, Phase 11):

    * a Menu click is honoured ONLY once NOTHING is active — refused
      (view unchanged) otherwise, however many jobs are still running;
    * absent a Menu click, ANY active job forces "running" — the
      auto-enter-on-first-start rule (0 -> >=1 while on "menu" or
      "main" lands on "running");
    * once "running", it STAYS "running" even as jobs finish one by
      one, all the way down to zero — Stop closing the LAST active job
      never auto-navigates by itself; only a SUBSEQUENT explicit Menu
      click does (see the first rule above);
    * otherwise the view is simply unchanged (covers "menu"/"main"
      while genuinely idle — nothing here needs to move).
    """
    if menu_requested:
        return "menu" if active_count == 0 else current
    if active_count > 0:
        return "running"
    return current
