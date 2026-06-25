# JioPC Session Hibernate

**Application-level, cross-VM session save & restore for the JioPC floating-VM
platform.** Challenge 03 (Hard) — JioPC × IIT Bombay Hackathon 2026 · Team
InnovAstra.

When a user is disconnected — idle timeout or the disconnect button — their
running GUI session (open apps, window geometry, and per-app in-app state) is
captured to the persistent home directory. On the next login, **on any VM in
the pool**, a notification offers to restore it: Chrome reopens its tabs, the
terminal returns to its directory, the file manager and documents reopen, and
anything else relaunches fresh. The VM changes; the session continues.

- **User-space, no root.** wmctrl / `/proc` / signals / notify-send — all
  unprivileged. Autostart is per-session.
- **Stdlib-only Python 3.** Zero pip dependencies; the `.deb` only needs
  `python3`.
- **Never blocks logout, never crashes the desktop.** Hard 10 s save budget;
  every external call and every relaunch is independently guarded.
- **Stateless / cross-VM by construction.** Everything lives in
  `~/.local/share/jiopc/hibernate/`, which roams with the home over NFS.

See **[DESIGN.md](DESIGN.md)** for the full rationale, **[SCHEMA.md](SCHEMA.md)**
for the state format, and **[demo/DEMO.md](demo/DEMO.md)** for the cross-VM
demo runbook.

## How it works (5 components)

| | Component | What it does |
|---|---|---|
| **A** | Session-end hook (`guard.py`) | Autostarted daemon; traps logout signals (`user_disconnect`) and polls X11 idle time (`inactivity_timeout`). Adds the save step without changing logout. |
| **B** | State capture (`saver.py`) | Enumerates GUI apps via `wmctrl` + `/proc`; records exec/argv/geometry/in-app state; flags unsaved work; time-budgeted. |
| **C** | Restore handlers (`handlers/`) | Configurable master list: Chrome, terminal, file manager, document — plus a generic fallback. New apps addable by JSON alone. |
| **D** | `session-state.json` | Versioned, documented JSON in the roaming home. |
| **E** | Restore service (`restore.py`) | Login-time XDG autostart: recency gate → `[Restore]/[Dismiss]` prompt → guarded relaunch → best-effort geometry → partial-restore report. |

## Install (Ubuntu 24.04 + LxQt)

```sh
# build the .deb (on the VM or any host with dpkg-deb)
packaging/build-deb.sh
sudo apt install ./packaging/dist/jiopc-hibernate_1.0.0_all.deb

# recommended companions for full functionality
sudo apt install wmctrl libnotify-bin xprintidle
```

Installs the guard + restore autostart entries system-wide — every user's next
LxQt login is covered, with no per-user setup. Optional per-user config:
`~/.config/jiopc-hibernate/config.json` (see `config/config.json` for all keys).

## Use it / inspect it

```sh
jiopc-hibernate status                       # tooling, config, last saved session
jiopc-hibernate save --trigger user_disconnect   # capture now
jiopc-hibernate restore                      # run the restore flow (with prompt)
jiopc-hibernate restore --yes                # restore without the prompt (demo)
jiopc-hibernate enumerate                    # list capturable windows + handler
jiopc-hibernate guard                        # the idle/signal daemon (autostarted)
jiopc-hibernate selftest                     # offline end-to-end check (no X11)
```

## Develop & verify (works on Linux *or* macOS — no X11 needed)

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

.venv/bin/python -m pytest -q                # 33 hermetic tests
PYTHONPATH=src python3 -m jiopc_hibernate selftest   # real save→restore loop
python3 benchmarks/benchmark.py --fake --runs 20     # benchmark harness
```

The OS is touched only through one mockable seam (`system.py`), so the entire
save/restore pipeline is exercised off-target. On a box with no `wmctrl`/X11 it
degrades cleanly: enumeration returns nothing, a valid (empty) state is written,
nothing crashes.

## Configuration highlights

| Key | Default | Meaning |
|---|---|---|
| `save_time_budget_ms` | `10000` | Hard ceiling on a save; partial state written past it. |
| `idle_timeout_s` | `600` | Idle seconds before an `inactivity_timeout` save. |
| `staleness_threshold_s` | `86400` | Older state is discarded silently (no prompt). |
| `restore_prompt_timeout_s` | `60` | Unanswered prompt → treated as dismiss. |
| `history_depth` | `3` | Sessions retained for "restore an earlier session". |
| `restore_geometry` | `true` | Apply saved geometry best-effort on restore. |
| `chrome_clean_shutdown` | `true` | SIGTERM Chrome on real session-end so it flushes. |

## License

Proprietary — JioPC × IIT Bombay Hackathon 2026 submission. © 2026 Team InnovAstra.
