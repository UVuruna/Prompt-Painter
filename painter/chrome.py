"""Chrome launcher — opens the automation Chrome when none is running.

Chrome 136+ ignores ``--remote-debugging-port`` on the DEFAULT user
profile, so PromptPainter runs Chrome with its own profile folder
(``chrome-profile/``, gitignored). The owner logs in there ONCE;
cookies persist, so every later run is already logged in. The
launcher never touches the owner's normal Chrome profile.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from painter.config import (
    CDP_PORT,
    CDP_URL,
    CHROME_CANDIDATES,
    CHROME_LAUNCH_TIMEOUT_S,
    CHROME_PROFILE_DIR,
)


class ChromeError(RuntimeError):
    """Chrome could not be found or its CDP endpoint never answered."""


def cdp_alive(cdp_url: str = CDP_URL) -> bool:
    """True when a debuggable Chrome answers on the CDP endpoint."""
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def find_chrome() -> Path:
    for candidate in CHROME_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    raise ChromeError(
        "chrome.exe not found — looked at: "
        + ", ".join(CHROME_CANDIDATES)
        + ". Add the right path to CHROME_CANDIDATES in painter/config.py."
    )


def ensure_chrome(site_urls: tuple[str, ...], cdp_url: str = CDP_URL) -> str:
    """Attach point guarantee: returns 'already-running' or 'launched'.

    When nothing answers on the CDP port, launches the automation
    Chrome (dedicated profile) with one tab per requested site and
    waits until the endpoint answers.
    """
    if cdp_alive(cdp_url):
        return "already-running"

    chrome = find_chrome()
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(chrome),
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            *site_urls,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + CHROME_LAUNCH_TIMEOUT_S
    while time.monotonic() < deadline:
        if cdp_alive(cdp_url):
            return "launched"
        time.sleep(0.5)
    raise ChromeError(
        f"Chrome was started but {cdp_url} never answered within"
        f" {CHROME_LAUNCH_TIMEOUT_S:.0f}s — is another Chrome already"
        " holding the profile folder, or a firewall blocking the port?"
    )
