# LxQt session-end integration (Component A)

The state save must fire on **both** disconnect paths the spec names —
inactivity timeout and user-initiated disconnect/logout — **without** a new
"Hibernate" button and **without** changing existing logout behaviour. We do
that with two user-space hooks:

1. the autostarted **guard daemon** (`jiopc-hibernate-guard`) for idle saves;
2. a direct `lxqt-leave` wrapper for manual logout/disconnect, installed by
   the `.deb` with `dpkg-divert`.

## 1. Inactivity mechanism — the guard daemon

`integration/autostart/jiopc-hibernate-guard.desktop` starts the guard with
the LxQt session. It needs no patching of `lxqt-session` and no root:

- **Inactivity timeout.** The guard samples X11 idle time (`xprintidle`, or
  `xssstate -i` via the XScreenSaver extension) every `idle_poll_interval_s`.
  When idle crosses `idle_timeout_s` it fires one save tagged
  `inactivity_timeout` and latches until the user is active again. It never
  locks the screen or ends the session — that stays the desktop's job.

The guard still traps teardown signals as a fallback, but manual logout should
not rely on teardown timing because LXQt may already have closed user windows.

## 2. Manual logout/disconnect mechanism — direct `lxqt-leave` wrapper

The package binds `jiopc-hibernate-leave` directly before the normal LXQt leave
action:

```text
/usr/bin/lxqt-leave          -> jiopc-hibernate wrapper
/usr/bin/lxqt-leave.real     -> original LXQt leave binary
```

This is installed by `packaging/debian/postinst` using `dpkg-divert`. Every
normal LXQt panel/menu/shortcut call to `lxqt-leave` now runs:

```text
jiopc-hibernate save --trigger user_disconnect
exec /usr/bin/lxqt-leave.real <original args>
```

That means the save happens synchronously while Chrome, terminals, file
manager windows, and document apps are still open. The wrapper preserves the
original `lxqt-leave` arguments exactly, including the no-argument mode LXQt
uses to show its normal leave dialog. Normal logout/disconnect behaviour
continues after the bounded save. `packaging/debian/prerm` removes the wrapper
and restores the original binary on uninstall.

For source-tree testing without installing the `.deb`, run the wrapper
directly:

```ini
jiopc-hibernate-leave
```

## 3. Verifying

```sh
jiopc-hibernate status          # shows tooling + last saved session
jiopc-hibernate save --trigger user_disconnect   # manual fire
# then check ~/.local/share/jiopc/hibernate/session-state.json
```
