"""Small human-readable formatters shared by the runner and the GUI."""


def fmt_duration(seconds: float) -> str:
    """A short human duration: '3m 12s', '48s'."""
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def fmt_op_duration(seconds: float) -> str:
    """A short op duration for the fast in-place tools: '0.2s', '3.4s',
    '12s', '1m 05s'. Sub-second precision below 10s that the whole-second
    ``fmt_duration`` would flatten to '0s' (bg/crop/aspect run in
    fractions of a second; only upscale takes real time)."""
    if seconds < 10:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def fmt_size(num_bytes: int) -> str:
    """A short human file size: '1.4 MB', '812 KB', '70 B'."""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / 1_048_576:.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"


def fmt_pct(value: float) -> str:
    """A tool metric percentage, precision scaled by magnitude (owner
    2026-07-19): below 10 -> 2 decimals ('0.08', '5.23', '9.99'), 10 and
    up -> 1 decimal ('10.0', '33.4', '300.0'). Returns the NUMBER only;
    callers append the '%'. So a 3px crop reads '0.24', never a rounded-
    away '0'."""
    return f"{value:.2f}" if value < 10 else f"{value:.1f}"
