"""Terminal handler — restore the working directory.

A terminal's useful state is the directory the user was in. We read it from
``/proc/<pid>/cwd`` at save time (no root: same-uid /proc is always readable)
and replay it with the emulator's own working-directory flag on restore.

Flag conventions differ per emulator, so the registry stores a template per
known terminal in handlers.json; this class just substitutes the captured cwd.
LxQt ships qterminal, whose flag is ``--workdir``; xterm/lxterminal accept
``--working-directory``. The captured cwd is also stashed in `extra` for the
benefit of any emulator we don't have a flag for (it can still be shown to the
user in the partial-restore report).
"""

from __future__ import annotations

from .base import RestoreHandler


class TerminalHandler(RestoreHandler):
    name = "terminal"

    def capture(self, win):
        ws = super().capture(win)
        ws.restore_supported = bool(win.cwd)
        if win.cwd:
            ws.extra["cwd"] = win.cwd
            flag = self.rule.restore_args[0] if self.rule.restore_args else "--working-directory"
            # Most emulators accept "--flag=PATH"; store the resolved arg.
            ws.restore_args = [f"{flag}={win.cwd}"]
        return ws

    def restore_command(self, ws):
        if not ws.exec:
            return None
        return [ws.exec, *ws.restore_args]
