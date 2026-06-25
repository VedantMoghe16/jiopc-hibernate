"""The configurable master list — binds handlers.json rules to handler code.

This is the heart of Component C's "configurable registry that is easy to
extend." The flow:

  * handlers.json is an ordered list of match rules. Each names a `handler`.
  * A rule whose handler name maps to a Python class (chrome/terminal/
    filemanager/document) gets that class's richer capture/restore logic.
  * A rule whose handler name is unknown becomes a *declarative* handler:
    the generic base class plus the rule's static `restore_args` and
    `restore_supported`. This is how a new app can be added with **zero code**
    — drop a rule in handlers.json and ship it.

The packaged default lives next to this module (default_handlers.json); a
user/Gold-Image copy at $XDG_CONFIG_HOME/jiopc-hibernate/handlers.json wins
if present. First matching rule owns the window; anything unmatched falls to
the generic handler.
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import MatchRule, RestoreHandler
from .chrome import ChromeHandler
from .terminal import TerminalHandler
from .filemanager import FileManagerHandler
from .document import DocumentHandler
from .. import paths
from ..log import get_logger
from ..windows import Window

_log = get_logger()

#: Named Python handlers. A rule referencing a name not here is treated as a
#: purely declarative handler (generic behaviour + the rule's static args).
_HANDLER_CLASSES: dict[str, type[RestoreHandler]] = {
    "chrome": ChromeHandler,
    "terminal": TerminalHandler,
    "filemanager": FileManagerHandler,
    "document": DocumentHandler,
    "generic": RestoreHandler,
}

_DEFAULT_RULES_FILE = Path(__file__).with_name("default_handlers.json")


class Registry:
    def __init__(self, handlers: list[RestoreHandler]):
        self._handlers = handlers
        self._generic = RestoreHandler()

    @classmethod
    def load(cls, rules_file: Path | None = None) -> "Registry":
        rules = _load_rules(rules_file)
        handlers: list[RestoreHandler] = []
        for rule in rules:
            handler_cls = _HANDLER_CLASSES.get(rule.handler, RestoreHandler)
            if rule.handler not in _HANDLER_CLASSES:
                _log.info("declarative handler '%s' (no code, config-only)", rule.handler)
            handlers.append(handler_cls(rule))
        _log.info("loaded %d handler rule(s)", len(handlers))
        return cls(handlers)

    def match(self, win: Window) -> RestoreHandler:
        """First rule whose patterns match; generic fallback otherwise."""
        for handler in self._handlers:
            if handler.rule.matches(win):
                return handler
        return self._generic

    def pre_save_hooks(self) -> list[RestoreHandler]:
        """Handlers that define an app-wide pre-save action (e.g. Chrome)."""
        hooks = []
        for h in self._handlers:
            if type(h).pre_save is not RestoreHandler.pre_save:
                hooks.append(h)
        return hooks

    def restore_handler_for(self, handler_name: str) -> RestoreHandler:
        """Look up the handler used to *restore* a saved window by name."""
        for h in self._handlers:
            if h.name == handler_name:
                return h
        cls = _HANDLER_CLASSES.get(handler_name, RestoreHandler)
        return cls(MatchRule(handler=handler_name))


def _load_rules(rules_file: Path | None) -> list[MatchRule]:
    path = rules_file or _resolve_rules_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("could not load handlers from %s (%s); using built-in defaults", path, exc)
        raw = _builtin_defaults()
    rules = []
    for entry in raw.get("handlers", []):
        try:
            rules.append(MatchRule(
                handler=entry["handler"],
                wm_class_contains=entry.get("wm_class_contains", []),
                exec_contains=entry.get("exec_contains", []),
                restore_args=entry.get("restore_args", []),
                restore_supported=entry.get("restore_supported", False),
            ))
        except KeyError:
            continue
    return rules


def _resolve_rules_path() -> Path:
    user = paths.config_dir() / "handlers.json"
    if user.exists():
        return user
    return _DEFAULT_RULES_FILE


def _builtin_defaults() -> dict:
    """Last-resort defaults if even the packaged JSON is missing/corrupt."""
    return {
        "handlers": [
            {"handler": "chrome",
             "wm_class_contains": ["chrome", "chromium"],
             "exec_contains": ["chrome", "chromium"],
             "restore_args": ["--restore-last-session"], "restore_supported": True},
            {"handler": "terminal",
             "wm_class_contains": ["qterminal", "lxterminal", "xterm", "terminal"],
             "exec_contains": ["qterminal", "lxterminal", "xterm"],
             "restore_args": ["--workdir"], "restore_supported": True},
            {"handler": "filemanager",
             "wm_class_contains": ["pcmanfm", "pcmanfm-qt"],
             "exec_contains": ["pcmanfm"], "restore_supported": True},
            {"handler": "document",
             "wm_class_contains": ["libreoffice", "soffice"],
             "exec_contains": ["soffice", "libreoffice"], "restore_supported": True},
        ]
    }
