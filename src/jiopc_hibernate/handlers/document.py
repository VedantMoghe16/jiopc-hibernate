"""Document-app handler — reopen the document(s) that were open.

Targets LibreOffice (Writer/Calc/Impress) and any editor that takes a file
path as an argument. The open document is recovered, most-reliable first:

  1. a document-like path already present in the original argv;
  2. a document file held open in /proc/<pid>/fd (no root needed — we only
     read our own user's descriptors). This catches the common case where the
     app was launched bare and the user opened a file from its dialog.

Restore relaunches the app with the document path(s) as arguments, which
LibreOffice and most editors honour, reopening the file. Exact cursor /
caret position (a stated bonus goal) is a natural extension point: the
`extra` dict already carries per-document metadata, and a LibreOffice UNO
macro can populate `extra["cursor"]` — wired through here without changing
any other module. See DESIGN.md §"Extending the registry".
"""

from __future__ import annotations

import os

from .base import RestoreHandler

_DOC_EXTS = (
    ".odt", ".ods", ".odp", ".odg", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".rtf", ".txt", ".md", ".csv", ".pdf",
)


class DocumentHandler(RestoreHandler):
    name = "document"

    def capture(self, win):
        ws = super().capture(win)
        docs = self._detect_documents(win)
        # restore_supported reflects what we actually captured for THIS window:
        # with no recoverable document, relaunching opens a blank app — a
        # fresh relaunch, not an in-app restore.
        ws.restore_supported = bool(docs)
        if docs:
            ws.extra["documents"] = docs
            ws.restore_args = docs
        return ws

    def restore_command(self, ws):
        if not ws.exec:
            return None
        return [ws.exec, *ws.restore_args]

    @classmethod
    def _detect_documents(cls, win) -> list[str]:
        found: list[str] = []
        # 1) explicit file arguments
        for arg in win.cmdline[1:]:
            path = os.path.expanduser(arg)
            if not arg.startswith("-") and cls._looks_like_doc(path) and os.path.isfile(path):
                found.append(path)
        if found:
            return found
        # 2) open file descriptors (Linux /proc only; silently skipped elsewhere)
        fd_dir = f"/proc/{win.pid}/fd"
        try:
            entries = os.listdir(fd_dir)
        except OSError:
            return found
        for fd in entries:
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if cls._looks_like_doc(target) and os.path.isfile(target):
                if target not in found:
                    found.append(target)
        return found

    @staticmethod
    def _looks_like_doc(path: str) -> bool:
        return path.lower().endswith(_DOC_EXTS)
