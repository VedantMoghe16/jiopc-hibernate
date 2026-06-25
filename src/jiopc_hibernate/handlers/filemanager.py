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

    @classmethod
    def _detect_folder(cls, win) -> str | None:
        # 1) Explicit folder argument — reliable for a separately-launched
        #    instance (pcmanfm-qt ~/Documents).
        for arg in win.cmdline[1:]:
            if not arg.startswith("-") and os.path.isdir(os.path.expanduser(arg)):
                return os.path.expanduser(arg)
        # 2) Single-instance case (LxQt default): every file window shares the
        #    desktop process's PID, so /proc cwd is just $HOME. The window title
        #    is the folder's name/path — resolve it to a real directory.
        folder = cls._resolve_title(win.title)
        if folder:
            return folder
        # 3) Fall back to the process cwd if it is a directory.
        if win.cwd and os.path.isdir(win.cwd):
            return win.cwd
        return None

    @staticmethod
    def _resolve_title(title: str | None) -> str | None:
        """Map a file-manager window title to a directory, best-effort.

        Handles an absolute path or '~/...' shown in the title, and the common
        case where the title is just the folder name directly under $HOME
        (e.g. "Documents" -> ~/Documents). Returns None if nothing resolves —
        restore then opens the file manager at its default view.
        """
        if not title:
            return None
        t = title.strip()
        if t.startswith("/") and os.path.isdir(t):
            return t
        if t.startswith("~"):
            p = os.path.expanduser(t)
            return p if os.path.isdir(p) else None
        cand = os.path.join(os.path.expanduser("~"), t)
        return cand if os.path.isdir(cand) else None
