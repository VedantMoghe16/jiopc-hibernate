# JioPC Session Hibernate — Design Document

**Challenge 03 — Session Hibernate (Cross-VM Session Restore)**
Team InnovAstra · Hackathon 2026 · Difficulty: Hard

---

## 1. The problem, restated

JioPC gives each user a VM from a shared pool. Sessions are **stateless by
design**: disconnect (idle timeout or the disconnect button) and your next
login lands you on a *different* VM with everything closed. The only thing
that follows you is your **home directory** (NFS-roaming).

So the design problem is precise: *capture enough of the running GUI session
into the home directory that it can be faithfully recreated on an arbitrary
VM later — automatically, without root, without blocking logout, and without
ever crashing the desktop.*

This is **application-level session restore**, explicitly *not* OS hibernate
(no RAM-to-disk on a floating VM) and *not* a "Hibernate button." It is
best-effort: apps that can expose in-app state are restored to it; apps that
can't are relaunched fresh. Restoring most of a session beats restoring none.

## 2. Architecture at a glance

```
                         ┌──────────────────────── on the OLD VM ───────────────────────┐
  idle / logout  ─────▶  │  guard (Component A)                                          │
                         │     SIGTERM/HUP trap  ─┐                                       │
                         │     X11 idle poll    ──┴─▶ saver (Component B)                 │
                         │                              │  enumerate (wmctrl + /proc)     │
                         │                              │  match handler (Component C)    │
                         │                              │  capture in-app state           │
                         │                              ▼                                 │
                         │                       session-state.json (Component D)         │
                         └────────────────────────────────┬──────────────────────────────┘
                                                           │  (persists in ~/.local/share,
                                                           │   roams via NFS to the next VM)
                         ┌────────────────────────────────▼──── on the NEW VM ───────────┐
   login (XDG autostart) │  restore service (Component E)                                 │
                         │     recency gate → notify [Restore]/[Dismiss]                  │
                         │     relaunch each app (handler cmd + best-effort geometry)     │
                         │     rename → session-state-last.json ; partial-restore report  │
                         └───────────────────────────────────────────────────────────────┘
```

Every box is one small module under `src/jiopc_hibernate/`. The OS — wmctrl,
/proc, signals, notify-send — is touched only through `system.py`, a single
mockable seam. That is why the whole thing can be unit-tested and
self-tested on a machine with no X11 at all (see §8).

## 3. Mapping to the required components

| Spec component | Where | How |
|---|---|---|
| **A — Session-end hook** | `guard.py`, `integration/` | Autostarted daemon: traps logout signals (`user_disconnect`) and polls idle time (`inactivity_timeout`). Adds the save step; changes nothing about logout. |
| **B — State capture** | `saver.py`, `windows.py`, `system.py`, `unsaved.py` | `wmctrl -lpGx` + `/proc/<pid>/{exe,cmdline,cwd}`; records name/exec/argv/geometry; flags unsaved titles; **time-budgeted**. |
| **C — Per-app handlers** | `handlers/` + `default_handlers.json` | Configurable master list bound to handler classes; Chrome/terminal/file-manager/document shipped; generic fallback; **new handlers addable by config alone**. |
| **D — `session-state.json`** | `state.py`, `SCHEMA.md` | Versioned, documented schema; atomic write; recency; history; consume-on-restore. |
| **E — Restore flow** | `restore.py`, `notify.py`, `geometry.py` | Recency gate → prompt → guarded relaunch → best-effort geometry → rename → report. Never crashes. |

## 4. Key design decisions & justifications

### 4.1 A guard daemon for the session-end hook (Component A)

The spec wants the save to fire on **both** disconnect paths, with no new
button, without altering logout, and inside a time budget. The options were:

1. **Patch `lxqt-session`** — rejected: needs root/rebuild, breaks on LxQt
   updates, and risks changing logout behaviour. Disqualified by "existing
   disconnect/logout must continue unchanged" and "no root."
2. **XSMP session client** — register with the X session manager for a logout
   callback. Correct in theory but heavyweight to implement robustly in pure
   Python, and XSMP delivery is uneven across WMs.
3. **A tiny autostarted guard daemon** — *chosen.* It is the minimal additive
   hook:
   - **Logout / disconnect:** when LxQt tears down, `lxqt-session` SIGTERMs its
     autostart children (X sends SIGHUP on display loss). We trap those, run
     one bounded save, and exit. Purely additive — if the guard is gone,
     logout still works; it just doesn't save.
   - **Inactivity:** we sample X11 idle time (`xprintidle` / XScreenSaver) and
     save once when it crosses the threshold, latching until activity resumes.
     We never lock or log out — that remains the desktop's job.
   - A 5 s debounce prevents an idle-save and the subsequent logout-SIGTERM
     from double-writing.

   An optional explicit `jiopc-hibernate-leave` wrapper (save → then real
   `lxqt-leave`) is provided for teams that want a synchronous save bound to
   the disconnect button. Both paths produce the two named triggers, so both
   are demoable.

### 4.2 The 10 s budget is a deadline, not a hope (Component B)

`saver.py` computes a monotonic deadline up front. Window enumeration is
time-boxed (`wmctrl` via `system.run` with a timeout). The capture loop checks
the deadline before each window and, if exceeded, **stops and writes partial
state** with `budget_exceeded: true`. Per-window work is cheap (`/proc`
symlink/byte reads), so in practice we finish in well under a second (see
benchmarks); the deadline exists to defend against the pathological case
(hung X, hundreds of windows) so the hook can never block session teardown.

### 4.3 The registry: declarative master list + pluggable code (Component C)

`default_handlers.json` is an ordered list of match rules; each names a
`handler`. A rule whose name maps to a Python class (chrome/terminal/
filemanager/document) gets that class's rich capture/restore. A rule whose
name is *unknown* becomes a **declarative handler**: generic capture plus the
rule's static `restore_args`. That is the extensibility the spec asks for —
**a new app is added by dropping a rule in JSON, no code, no rebuild** (proven
by `test_declarative_handler_added_by_config_only` and the shipped
`texteditor` example). First match wins; everything unmatched falls to the
generic handler (exec + geometry), so *every* GUI app is at least relaunched.

`restore_supported` is computed **per window**, not assumed from the rule:
a document app with no recoverable file reports `false` (it will open blank),
which keeps the restore report honest.

### 4.4 Chrome rides its own session machinery

We store **no tab list**. Chrome already persists its session; we just (a)
send it a clean SIGTERM on a *real* session-end save so it flushes and marks a
"Normal" exit, and (b) relaunch with `--restore-last-session`, which reopens
every tab. This gives 100% tab fidelity for free and is robust to Chrome
version changes. Crucially, the clean-shutdown signal fires **only** on
`session_end`/`user_disconnect`, never on a speculative idle save — we must
not kill a user's browser just because they stepped away.

### 4.5 Geometry is genuinely best-effort

The next VM may run at a different resolution, so geometry is the least
important, most fragile step — and treated as such. On restore we find the new
window by WM_CLASS (tracking a "claimed" set so two terminals don't stack),
then `wmctrl -e` it into place, **clamped to the current screen** so a
1920×1080 layout doesn't throw a window off a 1280×720 display. A window we
can't place is not a failure.

### 4.6 Statelessness is enforced by path discipline

`paths.py` resolves *everything* under `$XDG_DATA_HOME` / `$XDG_CONFIG_HOME`
(i.e. the roaming home) and nowhere else. A single `JIOPC_HIBERNATE_HOME`
override redirects the whole tree — which is exactly what makes the system
testable off-target and demoable in a sandbox. There is no machine-local
state, no PID file in `/var`, no socket. Cross-VM restore therefore needs no
special handling: the file is simply *there* on the next VM.

### 4.7 "Never crash the desktop" is structural, not aspirational

- `system.run` never raises (missing tool, non-zero exit, timeout all become a
  falsy result); `system.spawn` swallows launch errors.
- The save loop wraps each window capture; one bad window is logged and
  skipped. The save function never propagates.
- The restore loop guards each relaunch independently; a failed app is
  recorded in the report and the next app proceeds.
- `cli.main` has a last-ditch `except` that logs and returns **exit 0**, so a
  bug can never make the autostart entry look like a session error.
- Logging itself degrades to stderr if the home is unwritable.

## 5. Tooling choices (the spec asked us to justify these)

| Area | Choice | Why |
|---|---|---|
| Language | **Python 3, stdlib only** | Fast to build; excellent `/proc`, subprocess and JSON handling; **zero pip deps** means the `.deb` only depends on `python3`, which the Gold Image already has. No PySide6/Qt — this is a headless utility. |
| Window enumeration | **wmctrl** (`-lpGx`), xdotool fallback | Standard X11 CLI; one call yields id+pid+geometry+class+title. xdotool only needed where wmctrl's PID column is empty. |
| Process/cwd capture | **`/proc/<pid>/{exe,cmdline,cwd}`** | Recovers exec path, argv and terminal working directory with **no root** (same-uid /proc is always readable). |
| Session-end hook | **autostart guard daemon** | User-space, no-root, additive, survives LxQt updates (§4.1). |
| Restore service | **XDG autostart `.desktop`** | The spec's recommended mechanism; runs at login on any VM; system-wide entry needs no per-user setup. |
| Handler registry | **JSON master list + classes** | Configurable and code-free-extensible (§4.3). JSON over YAML to avoid a PyYAML dependency. |
| Notifications | **notify-send `--action`**, zenity/kdialog fallback | Native LxQt notification with [Restore]/[Dismiss]; graceful ladder down to a safe default. |
| Browser state | **Chrome clean-shutdown + `--restore-last-session`** | Reuses Chrome's own session restore for 100% tab fidelity (§4.4). |
| State format | **plain JSON in `~/.local/share/jiopc/hibernate/`** | Roams via NFS; human-readable; no DB/server (§4.6). |

## 6. Constraints — how each is met

| Constraint | Met by |
|---|---|
| Triggers on any disconnect | Guard traps logout signals **and** polls idle (§4.1). |
| Hooks existing session end | Additive autostart guard; logout/disconnect behaviour unchanged. |
| State in home directory only | `paths.py` confines everything to the roaming home (§4.6). |
| Works on a different VM | No machine-local state; restore reads the roamed file (§4.6). |
| No root | wmctrl/xdotool/`/proc`/notify-send/signals are all user-space; autostart is per-session. |
| State-save time budget | Monotonic deadline + partial-write (§4.2); benchmarked far inside 10 s. |
| Best-effort, non-destructive restore | Per-app guarded relaunch; in-app where supported, fresh otherwise; failures logged, session never crashes (§4.7). |
| Geometry best-effort | WM_CLASS match + clamped `wmctrl -e` (§4.5). |
| User confirmation on restore | `notify.ask_restore` gate before any relaunch; default **dismiss** if unattended. |
| Stale-state handling | `is_stale` (default 24 h) → discard silently, no prompt, consume the file. |
| Ships as a `.deb` | `packaging/build-deb.sh`; arch `all`; installs autostart + launchers; no user interaction. |

## 7. What "NOT looking for" we deliberately avoided

No OS hibernate, no Hibernate button, no same-VM assumption, no indefinite
blocking (hard deadline), no all-or-nothing restore (every app is attempted
independently). All five non-goals are structurally impossible to hit given
the design above.

## 8. Testing & verification strategy

- **Hermetic unit/integration suite** (`tests/`, 33 tests): schema roundtrip &
  recency & history, registry matching, each handler's capture/restore,
  wmctrl parsing, unsaved detection, ignore filtering, the full restore flow
  including **dismiss**, **stale**, **absent**, and **partial-failure** paths.
  Runs anywhere — the OS seam is mocked.
- **Offline self-test** (`jiopc-hibernate selftest`): drives the *real*
  save→restore loop end-to-end against fabricated windows, asserting Chrome
  gets `--restore-last-session`, the terminal gets its cwd, the document path
  is captured, unsaved work is flagged, the budget is respected, the file is
  consumed, and stale state is discarded. The macOS/CI proof that the wiring
  is correct.
- **Benchmark harness** (`benchmarks/`): save time, restore time, success rate
  across 10 app combinations; `--fake` for the dev box/CI, `--live` for the
  VM. Methodology documented.
- **On-VM acceptance**: the cross-VM demo runbook (`demo/DEMO.md`) walks the
  exact reviewer checklist on a real Ubuntu 24.04 + LxQt VM.

## 9. Bonus goals delivered

- **Extra handler / extensibility** — declarative handlers (config-only) plus
  the `extra` per-document slot wired for a future LibreOffice cursor-position
  macro (§4.3, `document.py`).
- **Partial-restore report** — `RestoreReport` + a summary notification listing
  what was restored and what to reopen manually.
- **Restore history** — last `history_depth` (default 3) sessions retained as
  `session-state-<epoch>.json` (`state.rotate_history`).

## 10. Layout

```
src/jiopc_hibernate/
  paths.py config.py log.py system.py      # foundation + OS seam
  windows.py unsaved.py                     # Component B inputs
  state.py                                  # Component D (schema/IO/lifecycle)
  handlers/  base, chrome, terminal,        # Component C
             filemanager, document,
             registry, default_handlers.json
  saver.py                                  # Component B orchestration
  guard.py                                  # Component A daemon
  notify.py geometry.py restore.py          # Component E
  cli.py __main__.py selftest.py            # entry points + offline proof
integration/  autostart/  bin/  lxqt/  idle/   # session wiring
packaging/    build-deb.sh  debian/            # the .deb
benchmarks/   benchmark.py  methodology.md  results.md
tests/        33 hermetic tests
demo/         DEMO.md (cross-VM runbook)
```
