# LxQt session-end integration (Component A)

The state save must fire on **both** disconnect paths the spec names —
inactivity timeout and user-initiated disconnect/logout — **without** a new
"Hibernate" button and **without** changing existing logout behaviour. We do
that with the autostarted **guard daemon** (`jiopc-hibernate-guard`), and
offer an optional explicit logout wrapper for teams that prefer it.

## 1. Primary mechanism — the guard daemon (zero config, recommended)

`integration/autostart/jiopc-hibernate-guard.desktop` starts the guard with
the LxQt session. It needs no patching of `lxqt-session` and no root:

- **User-initiated disconnect / logout.** When LxQt tears the session down,
  `lxqt-session` sends `SIGTERM` to its autostart children (and the X server
  sends `SIGHUP` on display loss). The guard traps these, runs **one** bounded
  save tagged `user_disconnect`, then exits so teardown proceeds untouched.
  We *add* the save step; logout itself is unchanged.

- **Inactivity timeout.** The guard samples X11 idle time (`xprintidle`, or
  `xssstate -i` via the XScreenSaver extension) every `idle_poll_interval_s`.
  When idle crosses `idle_timeout_s` it fires one save tagged
  `inactivity_timeout` and latches until the user is active again. It never
  locks the screen or ends the session — that stays the desktop's job.

A 5-second debounce stops the two paths from double-saving when an idle save
is immediately followed by a logout `SIGTERM`.

> Why a daemon and not an `lxqt-session` patch? It is user-space, no-root,
> reversible, and survives LxQt point releases. It is additive by construction:
> if it dies, logout still works; it just doesn't save.

## 2. Optional — explicit logout wrapper

Some deployments want the save to happen *synchronously before* the logout
action, independent of signal timing. Bind the "Logout/Disconnect" action (or
a keyboard shortcut) to the wrapper in this directory:

```ini
# ~/.config/lxqt/globalkeyshortcuts.conf  (or a custom menu/panel action)
[General]
...
# Example: bind your disconnect button/shortcut to:
#   jiopc-hibernate-leave
```

`jiopc-hibernate-leave` runs `jiopc-hibernate save --trigger user_disconnect`
(bounded by the 10 s budget) and then calls the real `lxqt-leave --logout`,
so existing logout behaviour is preserved exactly — the save is simply
prepended.

## 3. Verifying

```sh
jiopc-hibernate status          # shows tooling + last saved session
jiopc-hibernate save --trigger user_disconnect   # manual fire
# then check ~/.local/share/jiopc/hibernate/session-state.json
```
