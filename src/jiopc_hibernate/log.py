"""Logging — a single file logger that can never take down the session.

The spec is emphatic: "the desktop session must never crash due to a
background utility failure." So logging setup is wrapped in best-effort
guards, falls back to stderr if the log directory is unwritable, and the
file handler caps its own size so a roaming home never fills up.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

_LOGGER_NAME = "jiopc.hibernate"
_configured = False


def get_logger() -> logging.Logger:
    """Return the package logger, configuring handlers exactly once."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Primary sink: a size-capped file in the persistent home.
    try:
        paths.ensure_dirs()
        handler: logging.Handler = RotatingFileHandler(
            paths.log_file(), maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        # If the home is unwritable, degrade to stderr rather than crash.
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False

    _configured = True
    return logger
