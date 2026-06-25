"""Best-effort window placement on restore.

After an app is relaunched it draws a new window at a WM-chosen position. We
try to nudge it back to its saved geometry with ``wmctrl -e``. This is the
most fragile, least-important part of restore — the next VM may have a
different resolution, and a window we can't place is no failure at all — so
every step is time-boxed and guarded, and geometry is *clamped* to the
current screen so a 1920×1080 layout doesn't fling a window off a 1280×720
display.

Matching the new window to the saved one is done by WM_CLASS plus a
"claimed" set the restore service maintains, so two terminals don't both
land in the same spot.
"""

from __future__ import annotations

import time

from . import system, windows
from .log import get_logger

_log = get_logger()


def current_window_ids() -> set[str]:
    return {w.wid for w in windows.enumerate_windows(timeout=2.0)}


def find_window(wm_class: str, exclude: set[str], timeout: float = 4.0) -> str | None:
    """Poll for a newly-appeared window matching wm_class, ignoring `exclude`.

    Returns the window id once it appears, or None within the timeout.
    """
    if not wm_class:
        return None
    target = wm_class.lower()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in windows.enumerate_windows(timeout=1.5):
            if w.wid in exclude:
                continue
            if target in (w.wm_class or "").lower():
                return w.wid
        time.sleep(0.3)
    return None


def move_resize(wid: str, geo: dict, screen: dict | None = None) -> bool:
    """Apply geometry to a window via wmctrl. Returns success (best-effort)."""
    if not geo or not system.have("wmctrl"):
        return False
    x, y = int(geo.get("x", 0)), int(geo.get("y", 0))
    w, h = int(geo.get("width", 0)), int(geo.get("height", 0))
    if w <= 0 or h <= 0:
        return False
    x, y, w, h = _clamp(x, y, w, h, screen)
    # Drop maximised states first so the move takes effect, then place it.
    system.run(["wmctrl", "-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz"], timeout=2.0)
    res = system.run(["wmctrl", "-i", "-r", wid, "-e", f"0,{x},{y},{w},{h}"], timeout=2.0)
    if not res.ok:
        _log.info("geometry apply failed for %s: %s", wid, res.stderr.strip())
    return res.ok


def _clamp(x: int, y: int, w: int, h: int, screen: dict | None) -> tuple[int, int, int, int]:
    """Keep the window inside the current screen (resolution may have shrunk)."""
    if not screen:
        return x, y, w, h
    sw, sh = int(screen.get("width", 0)), int(screen.get("height", 0))
    if sw > 0:
        w = min(w, sw)
        x = max(0, min(x, sw - w))
    if sh > 0:
        h = min(h, sh)
        y = max(0, min(y, sh - h))
    return x, y, w, h
