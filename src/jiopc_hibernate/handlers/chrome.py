"""Chrome / Chromium handler — the headline in-app restore.

Chrome already persists its own session (open tabs, scroll, form data) to
``~/.config/google-chrome/Default/Sessions``. Our job is twofold:

  * **on save**  — send the Chrome process a *clean* shutdown signal (SIGTERM)
    so it flushes that session to disk and marks the exit type "Normal".
    Without this, the next launch thinks it crashed and shows the ugly
    "restore pages?" bubble instead of silently reopening.
  * **on restore** — launch ``google-chrome --restore-last-session``, which
    reopens every tab exactly. Tab fidelity is therefore 100% and rides on
    Chrome's own machinery — we store no tab list ourselves.

The clean-shutdown signal is the only place the system sends a signal to a
foreign process; it is SIGTERM (graceful, the same thing the WM would send),
never SIGKILL, and failures are swallowed.
"""

from __future__ import annotations

import os
import signal

from .base import RestoreHandler
from ..log import get_logger
from ..windows import Window

_log = get_logger()


class ChromeHandler(RestoreHandler):
    name = "chrome"

    def restore_command(self, ws):
        exe = ws.exec or "google-chrome"
        args = ws.restore_args or ["--restore-last-session"]
        # Preserve a non-default profile if the original argv pinned one.
        profile = next((a for a in ws.cmdline if a.startswith("--profile-directory=")), None)
        cmd = [exe, *args]
        if profile and profile not in cmd:
            cmd.append(profile)
        return cmd

    def pre_save(self, windows: list[Window]) -> None:
        """Politely ask every Chrome process to shut down so it flushes."""
        pids = {w.pid for w in windows if w.pid > 0 and self.rule.matches(w)}
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                _log.info("sent clean-shutdown (SIGTERM) to Chrome pid %d", pid)
            except (ProcessLookupError, PermissionError, OSError) as exc:
                _log.warning("could not signal Chrome pid %d: %s", pid, exc)
