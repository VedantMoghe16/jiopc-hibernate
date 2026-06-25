"""File-manager handler — reopen the folder that was showing.

PCManFM-Qt (the LxQt default) takes a folder path as a positional argument,
so restore is just ``pcmanfm-qt <path>``. The folder is recovered, in order
of reliability:

  1. the directory in /proc/<pid>/cwd (PCManFM-Qt chdir()s into the shown
     folder), or
  2. a path that already appears in the original argv.

If neither yields a directory we fall back to a plain relaunch (opens the
default/home view) — still better than not reopening the file manager at all.
"""

from __future__ import annotations

import os

from .base import RestoreHandler


class FileManagerHandler(RestoreHandler):
    name = "filemanager"

    def capture(self, win):
        ws = super().capture(win)
        folder = self._detect_folder(win)
        ws.restore_supported = bool(folder)
        if folder:
            ws.extra["folder"] = folder
            ws.restore_args = [folder]
        return ws

    def restore_command(self, ws):
        if not ws.exec:
            return None
        return [ws.exec, *ws.restore_args]

    @staticmethod
    def _detect_folder(win) -> str | None:
        if win.cwd and os.path.isdir(win.cwd):
            return win.cwd
        for arg in win.cmdline[1:]:
            if not arg.startswith("-") and os.path.isdir(os.path.expanduser(arg)):
                return arg
        return None
