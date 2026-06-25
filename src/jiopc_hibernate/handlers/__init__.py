"""Per-app restore handlers (Component C) and the configurable registry."""

from .base import MatchRule, RestoreHandler
from .registry import Registry

__all__ = ["MatchRule", "RestoreHandler", "Registry"]
