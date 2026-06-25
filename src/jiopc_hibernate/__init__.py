"""JioPC Session Hibernate — application-level, cross-VM session save & restore.

A user-space (no-root) utility for the JioPC floating-VM platform. When a
user is disconnected — by inactivity timeout or by pressing disconnect — the
running GUI session is captured to the persistent home directory. On the next
login, *on any VM in the pool*, the restore service offers to bring the apps
back: in-app state where a handler supports it, a fresh relaunch otherwise.

The package is intentionally dependency-free (Python 3 standard library only).
Every interaction with the outside world — wmctrl, xdotool, /proc, signals,
notify-send — is routed through a thin, mockable seam so the system degrades
gracefully when a tool is absent and can be unit-tested off-target.
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
