# Inactivity-timeout integration (Component A)

The guard daemon already detects idleness itself (see `../lxqt/README.md`), so
**no extra setup is required**. This directory documents two things: the idle
backends the guard uses, and how to drive the save from an *external* idle
manager instead, if a deployment already standardises on one.

## Built-in idle detection (default)

The guard reads X11 idle time once per `idle_poll_interval_s` (default 15 s)
and saves when it exceeds `idle_timeout_s` (default 600 s), using the first
available of:

| Backend          | Source                                   | Package        |
|------------------|------------------------------------------|----------------|
| `xprintidle`     | XScreenSaver extension, ms of idle       | `xprintidle`   |
| `xssstate -i`    | XScreenSaver extension, ms of idle       | `xssstate`     |
| *(none present)* | guard runs as a **signal-only** hook     | —              |

Install `xprintidle` (recommended; tiny, no deps) for inactivity support:

```sh
sudo apt-get install xprintidle
```

## Alternative — drive saves from xautolock / xss-lock

If the Gold Image already runs an idle manager, point it at the save command
instead of (or alongside) the guard. The save is bounded and idempotent.

**xautolock** — fire the save as the "notify" action a bit *before* the lock:

```sh
xautolock \
  -time 10 \                       # minutes idle
  -notify 30 -notifier 'jiopc-hibernate save --trigger inactivity_timeout' \
  -locker 'lxqt-leave --lockscreen'
```

**xss-lock** (logind/systemd idle → lock) — save in the lock command:

```sh
xss-lock -- sh -c 'jiopc-hibernate save --trigger inactivity_timeout; lxqt-leave --lockscreen'
```

When using an external manager, set `idle_timeout_s` very high (or stop the
guard's polling) in `config.json` to avoid duplicate saves; the 5 s debounce
will absorb the occasional overlap regardless.
