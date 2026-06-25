"""Per-app restore handler — the contract every handler implements.

A handler is the bridge between a live window and a replayable WindowState.
It does three jobs, any of which it may decline (the base class gives safe,
generic defaults so a handler only overrides what it actually improves on):

  * **capture**  — turn a Window into a WindowState, adding in-app state and
                   restore arguments where the app exposes them.
  * **command**  — turn a WindowState back into an argv to launch on restore.
  * **pre_save** — an optional app-wide action run *before* the file is
                   written, e.g. signalling Chrome to flush its session.

Matching (which handler owns a window) is decided by the registry from
declarative rules in handlers.json, not by the handler itself — that keeps
matching configurable without touching code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..state import WindowState
from ..unsaved import has_unsaved_marker
from ..windows import Window


@dataclass
class MatchRule:
    """How the registry decides a handler owns a window (from handlers.json)."""
    handler: str
    wm_class_contains: list[str] = field(default_factory=list)
    exec_contains: list[str] = field(default_factory=list)
    restore_args: list[str] = field(default_factory=list)   # static args, declarative
    restore_supported: bool = False                         # declarative default

    def matches(self, win: Window) -> bool:
        cls = (win.wm_class or "").lower()
        exe = (win.exe or "").lower()
        argv0 = (win.cmdline[0].lower() if win.cmdline else "")
        for needle in self.wm_class_contains:
            if needle.lower() in cls:
                return True
        for needle in self.exec_contains:
            if needle.lower() in exe or needle.lower() in argv0:
                return True
        return False


class RestoreHandler:
    """Base handler: a faithful generic capture/relaunch with geometry only."""

    #: Stable identifier, referenced by handlers.json and written into state.
    name = "generic"

    def __init__(self, rule: MatchRule | None = None):
        self.rule = rule or MatchRule(handler=self.name)
        # Effective name comes from the rule, so a *declarative* handler (a
        # rule with no Python class) reports its configured name, not "generic".
        self.name = self.rule.handler

    # --- capture ------------------------------------------------------------
    def capture(self, win: Window) -> WindowState:
        """Default capture: exec path + argv + geometry, no in-app state."""
        ws = WindowState(
            app_name=win.app_name,
            exec=win.exe or (win.cmdline[0] if win.cmdline else None),
            cmdline=list(win.cmdline),
            handler=self.name,
            geometry={"x": win.x, "y": win.y, "width": win.width, "height": win.height},
            desktop=win.desktop,
            wm_class=win.wm_class,
            pid=win.pid,
            title=win.title,
            unsaved=has_unsaved_marker(win.title),
            restore_supported=self.rule.restore_supported,
            restore_args=list(self.rule.restore_args),
        )
        return ws

    # --- restore ------------------------------------------------------------
    def restore_command(self, ws: WindowState) -> list[str] | None:
        """Build the argv to relaunch. Default: exec + declarative restore_args.

        Returns None when there is nothing safe to launch (no exec path),
        which the restore service logs as a skip rather than an error.
        """
        if not ws.exec:
            return None
        return [ws.exec, *ws.restore_args]

    # --- optional app-wide save hook ---------------------------------------
    def pre_save(self, windows: list[Window]) -> None:
        """Run once before the state file is written. Default: nothing."""
        return None
