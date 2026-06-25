"""Component B, part 1 — enumerate open windows and the GUI apps behind them.

Standard X11 tooling does the heavy lifting: ``wmctrl -lpGx`` lists every
managed top-level window with its PID, geometry and WM_CLASS in one shot. We
join that against /proc (handled in `system`) to recover the executable,
argv and cwd. ``xdotool`` is a fallback for the (rare) WMs where wmctrl's
``-p`` PID column is empty.

Everything degrades: no X11, no wmctrl, or a parse miss yields an empty list,
and the saver simply records that no windows were found rather than crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import system
from .log import get_logger

_log = get_logger()


@dataclass
class Window:
    """One managed top-level window plus the process that owns it."""
    wid: str               # X window id, e.g. 0x03a00007
    desktop: int           # virtual desktop index (-1 == sticky/all)
    pid: int
    x: int
    y: int
    width: int
    height: int
    wm_class: str          # "instance.Class", e.g. google-chrome.Google-chrome
    host: str              # client machine reported by the WM
    title: str

    # Filled in from /proc during capture.
    exe: str | None = None
    cmdline: list[str] = field(default_factory=list)
    cwd: str | None = None

    @property
    def app_name(self) -> str:
        """A human label: prefer the Class half of WM_CLASS, fall back to argv0."""
        if self.wm_class and "." in self.wm_class:
            return self.wm_class.split(".", 1)[1]
        if self.wm_class:
            return self.wm_class
        if self.cmdline:
            return self.cmdline[0].rsplit("/", 1)[-1]
        return self.title or "Unknown"


def _parse_wmctrl(lines: list[str]) -> list[Window]:
    """Parse ``wmctrl -lpGx`` rows.

    Columns (whitespace-separated, title is the free-text remainder):
        wid  desktop  pid  x  y  w  h  wm_class  host  title...
    """
    out: list[Window] = []
    for line in lines:
        parts = line.split(None, 9)
        if len(parts) < 9:
            continue
        try:
            wid = parts[0]
            desktop = int(parts[1])
            pid = int(parts[2])
            x, y, w, h = (int(parts[i]) for i in range(3, 7))
            wm_class = parts[7]
            host = parts[8]
            title = parts[9] if len(parts) > 9 else ""
        except ValueError:
            continue
        out.append(Window(wid, desktop, pid, x, y, w, h, wm_class, host, title))
    return out


def enumerate_windows(timeout: float = 3.0) -> list[Window]:
    """Return every managed GUI window, enriched from /proc. Best-effort."""
    if not system.is_linux():
        _log.info("not on Linux; window enumeration unavailable")
        return []
    if not system.have("wmctrl"):
        _log.warning("wmctrl not installed; cannot enumerate windows")
        return []

    res = system.run(["wmctrl", "-lpGx"], timeout=timeout)
    if not res.ok:
        _log.warning("wmctrl failed: %s", res.stderr.strip())
        return []

    windows = _parse_wmctrl(res.lines)
    if not windows and system.is_wayland():
        _log.warning(
            "0 windows and session is Wayland — wmctrl (X11) cannot enumerate "
            "Wayland windows. The LxQt target runs on X11; use an X11 session.")
    for win in windows:
        _enrich_from_proc(win)
    _log.info("enumerated %d window(s)", len(windows))
    return windows


def _enrich_from_proc(win: Window) -> None:
    """Attach exec path, argv and cwd from /proc; tolerate missing entries."""
    if win.pid <= 0:
        return
    win.exe = system.proc_exe(win.pid)
    win.cmdline = system.proc_cmdline(win.pid) or []
    win.cwd = system.proc_cwd(win.pid)


def display_geometry(timeout: float = 2.0) -> dict | None:
    """Current screen size, so restore can reason about resolution changes.

    Parsed from ``wmctrl -d`` (the desktop geometry column). Best-effort and
    purely informational — geometry restore is never gated on this.
    """
    if not system.have("wmctrl"):
        return None
    res = system.run(["wmctrl", "-d"], timeout=timeout)
    if not res.ok:
        return None
    for line in res.lines:
        # "0  * DG: 1920x1080  VP: 0,0  WA: ..."
        if "DG:" in line:
            try:
                geo = line.split("DG:", 1)[1].split()[0]
                w, h = geo.lower().split("x")
                return {"width": int(w), "height": int(h)}
            except (ValueError, IndexError):
                return None
    return None
