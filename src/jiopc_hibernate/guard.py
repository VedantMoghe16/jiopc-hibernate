"""Component A — the session-end hook, as a lightweight user-space daemon.

The challenge needs a state save to fire automatically on *both* disconnect
paths, with no new "Hibernate" button, without changing existing logout
behaviour, and within a strict time budget. A small autostarted daemon is the
cleanest way to satisfy all of that without root or patching lxqt-session:

  * **user-initiated disconnect / logout** — when the LxQt session tears down,
    the session manager sends SIGTERM (and SIGHUP on X display loss) to its
    autostart children. We trap those signals, run one bounded save tagged
    ``user_disconnect``, and then exit so teardown proceeds normally. We add
    the save step; we change nothing about logout itself.

  * **inactivity timeout** — we sample the X server's idle time (via
    ``xprintidle``, falling back to the XScreenSaver extension through
    ``xssstate``). When idle crosses the configured threshold we fire one
    save tagged ``inactivity_timeout`` and arm a latch so we don't re-save
    every poll; the latch resets the moment the user is active again.

A debounce stops the two paths from double-saving (idle save, then SIGTERM a
moment later). The daemon is deliberately tiny and dependency-free; if idle
tooling is missing it simply runs as a signal-only hook.
"""

from __future__ import annotations

import signal
import threading
import time

from . import saver, state as state_mod, system
from .config import Config
from .log import get_logger

_log = get_logger()


class SessionGuard:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config.load()
        self._stop = threading.Event()
        self._last_save_monotonic = 0.0
        self._idle_latched = False
        self._debounce_s = 5.0

    # --- lifecycle ----------------------------------------------------------
    def run(self) -> None:
        """Install signal traps and enter the idle-polling loop. Blocks."""
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                pass  # not the main thread / unsupported — non-fatal
        _log.info("session guard started (idle_timeout=%ds, poll=%ds, budget=%dms)",
                  self.cfg.idle_timeout_s, self.cfg.idle_poll_interval_s,
                  self.cfg.save_time_budget_ms)
        self._poll_loop()

    def _on_signal(self, signum, _frame) -> None:
        name = signal.Signals(signum).name
        _log.info("received %s — session is ending, saving (user_disconnect)", name)
        self._save(state_mod.TRIGGER_USER_DISCONNECT)
        self._stop.set()

    # --- idle polling -------------------------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            idle = idle_seconds()
            if idle is None:
                # No idle tooling: degrade to a pure signal hook.
                self._stop.wait(self.cfg.idle_poll_interval_s)
                continue
            if idle >= self.cfg.idle_timeout_s:
                if not self._idle_latched:
                    _log.info("idle %.0fs >= %ds — saving (inactivity_timeout)",
                              idle, self.cfg.idle_timeout_s)
                    self._save(state_mod.TRIGGER_INACTIVITY)
                    self._idle_latched = True
            else:
                self._idle_latched = False  # user active again → re-arm
            self._stop.wait(self.cfg.idle_poll_interval_s)

    # --- the bounded save (with debounce) -----------------------------------
    def _save(self, trigger: str) -> None:
        now = time.monotonic()
        if now - self._last_save_monotonic < self._debounce_s:
            _log.info("debounced %s save (last save %.1fs ago)", trigger, now - self._last_save_monotonic)
            return
        self._last_save_monotonic = now
        try:
            saver.save_session(trigger, cfg=self.cfg)
        except Exception as exc:  # the guard must outlive any save failure
            _log.error("save raised (suppressed): %s", exc)


def idle_seconds() -> float | None:
    """Current X11 idle time in seconds, or None if it can't be determined."""
    if system.have("xprintidle"):
        res = system.run(["xprintidle"], timeout=2.0)
        if res.ok and res.stdout.strip().isdigit():
            return int(res.stdout.strip()) / 1000.0
    if system.have("xssstate"):
        res = system.run(["xssstate", "-i"], timeout=2.0)
        if res.ok and res.stdout.strip().isdigit():
            return int(res.stdout.strip()) / 1000.0
    return None
