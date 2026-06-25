# Changelog

All notable changes to JioPC Session Hibernate.

## [1.0.0] — 2026-06-25

Initial hackathon submission — Challenge 03, Session Hibernate (Cross-VM
Session Restore). Complete implementation of all five required components plus
all three bonus goals.

### Components
- **A — Session-end hook**: autostarted `guard` daemon trapping logout signals
  (`user_disconnect`) and polling X11 idle time (`inactivity_timeout`); 5 s
  debounce; optional `jiopc-hibernate-leave` logout wrapper; xautolock/xss-lock
  integration documented.
- **B — State capture**: `wmctrl -lpGx` + `/proc/<pid>/{exe,cmdline,cwd}`
  enumeration; per-window handler capture; unsaved-work detection; hard,
  monotonic 10 s save budget with partial-state write.
- **C — Per-app handlers**: configurable JSON master list bound to handler
  classes — Chrome, terminal, file manager, document — with a generic fallback
  and code-free *declarative* handlers.
- **D — `session-state.json`**: versioned, documented schema; atomic write;
  recency; consume-on-restore.
- **E — Restore service**: XDG-autostart login flow; recency gate;
  `[Restore]/[Dismiss]` notification; guarded relaunch; best-effort,
  screen-clamped geometry; rename to `-last`; never crashes.

### Bonus
- Declarative (config-only) handlers + `extra` slot wired for LibreOffice
  cursor position.
- Partial-restore report (summary notification of restored vs. failed apps).
- Restore history — last `history_depth` (default 3) sessions retained.

### Packaging & tooling
- `.deb` build (`packaging/build-deb.sh`), arch `all`, depends only on
  `python3`; installs system-wide autostart + launchers with no user
  interaction.
- 33 hermetic tests, offline `selftest`, benchmark harness with documented
  methodology, cross-VM demo runbook.
