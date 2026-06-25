"""Component B, part 2 — flag windows that look like they hold unsaved work.

Most editors mark a dirty document in the window title with a leading bullet
(•) or asterisk (*) — gedit, LibreOffice, VS Code, Kate, GIMP all do some
variant. We detect that purely from the title we already captured (no extra
tooling) and record a boolean. The flag is advisory: the restore step (or the
user, via the partial-restore report) is informed; we never block a save or
silently drop a window because it might be dirty.
"""

from __future__ import annotations

import re

# Leading marker (gedit "•Untitled", LibreOffice/VS Code style) or a trailing
# "*" / " - modified" hint. Kept deliberately loose — a false positive only
# means we surface an extra "unsaved" note, which is harmless.
_MARKERS = ("•", "*", "✱", "◆")
_TRAILING_MODIFIED = re.compile(r"(\*|\bmodified\b|\bunsaved\b)\s*$", re.IGNORECASE)


def has_unsaved_marker(title: str) -> bool:
    if not title:
        return False
    stripped = title.strip()
    if stripped[:1] in _MARKERS:
        return True
    if any(m in stripped[:3] for m in _MARKERS):
        return True
    return bool(_TRAILING_MODIFIED.search(stripped))
