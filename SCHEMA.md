# `session-state.json` — schema reference (Component D)

The single artifact that travels between VMs. Written by the saver to
`~/.local/share/jiopc/hibernate/session-state.json`, read by the restore
service on the next login. It lives in the persistent (NFS-roaming) home, so
it is automatically present on whatever VM the broker allocates next — no
database, no server, no machine-local state.

## Top-level object

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | Format version. Currently `1`. Lets the restore service refuse/migrate future formats. |
| `saved_at` | string | ISO-8601 UTC, `YYYY-MM-DDTHH:MM:SSZ`. Drives the staleness check. |
| `trigger` | string | Why the save fired: `inactivity_timeout` \| `user_disconnect` \| `session_end` \| `manual`. |
| `hostname` | string | The VM the session was saved on (informational; restore is VM-agnostic). |
| `save_duration_ms` | int | How long the capture took. Proves the time-budget claim. |
| `time_budget_ms` | int | The budget in force at save time (default 10000). |
| `budget_exceeded` | bool | `true` if capture hit the deadline and wrote partial state. |
| `display` | object \| null | Source screen size `{width,height}`; lets restore clamp geometry to a smaller screen. |
| `window_count` | int | Convenience count of `windows` (derived). |
| `windows` | array | One object per captured GUI window (below). |

## Window object

| Field | Type | Description |
|---|---|---|
| `app_name` | string | Human label (from WM_CLASS / argv0). |
| `exec` | string \| null | Executable path (`/proc/<pid>/exe`, falling back to argv0). |
| `cmdline` | array<string> | The original argv (`/proc/<pid>/cmdline`). |
| `handler` | string | Which restore handler owns it: `chrome` \| `terminal` \| `filemanager` \| `document` \| a declarative name \| `generic`. |
| `restore_args` | array<string> | Arguments the handler will relaunch with (e.g. `["--restore-last-session"]`, or a resolved `--workdir=…`). |
| `geometry` | object \| null | `{x,y,width,height}` at save time. Best-effort on restore. |
| `desktop` | int | Virtual-desktop index (`-1` = sticky). |
| `wm_class` | string | Raw `instance.Class`; used to re-match the window for geometry. |
| `pid` | int | PID at save time (informational; not valid on the next VM). |
| `title` | string | Window title at save time. |
| `unsaved` | bool | `true` if the title carried an unsaved-work marker (`•`/`*`). |
| `restore_supported` | bool | `true` if in-app state was captured for *this* window; `false` means a plain relaunch. |
| `extra` | object | Handler-specific in-app state (e.g. `{"cwd": …}`, `{"documents": […]}`). Extension point for richer handlers. |

## Example

```json
{
  "schema_version": 1,
  "saved_at": "2026-05-30T07:15:00Z",
  "trigger": "user_disconnect",
  "hostname": "vm-pool-07",
  "save_duration_ms": 184,
  "time_budget_ms": 10000,
  "budget_exceeded": false,
  "display": { "width": 1920, "height": 1080 },
  "window_count": 2,
  "windows": [
    {
      "app_name": "Google-chrome",
      "exec": "/usr/bin/google-chrome",
      "cmdline": ["/usr/bin/google-chrome", "--profile-directory=Default"],
      "handler": "chrome",
      "restore_args": ["--restore-last-session"],
      "geometry": { "x": 100, "y": 50, "width": 1200, "height": 800 },
      "desktop": 0,
      "wm_class": "google-chrome.Google-chrome",
      "pid": 2345,
      "title": "Inbox - Gmail",
      "unsaved": false,
      "restore_supported": true,
      "extra": {}
    },
    {
      "app_name": "qterminal",
      "exec": "/usr/bin/qterminal",
      "cmdline": ["/usr/bin/qterminal"],
      "handler": "terminal",
      "restore_args": ["--workdir=/home/user/projects"],
      "geometry": { "x": 50, "y": 100, "width": 800, "height": 500 },
      "desktop": 0,
      "wm_class": "qterminal.qterminal",
      "pid": 2350,
      "title": "user@vm: ~/projects",
      "unsaved": false,
      "restore_supported": true,
      "extra": { "cwd": "/home/user/projects" }
    }
  ]
}
```

## Lifecycle on disk

```
session-state.json            written atomically on every save (temp + rename)
session-state-last.json       previous session, after restore consumes it
session-state-<epoch>.json    history snapshots, newest `history_depth`-1 kept
```

- **Atomic write** — written to `…json.tmp` then `os.replace`d, so a save
  interrupted by session teardown never leaves a half-written file.
- **Consume on restore** — after the restore flow runs (whether the user
  accepts, dismisses, or the state was stale), the live file is renamed to
  `session-state-last.json` so it can never re-trigger on a later login.
- **History** — before each overwrite the prior state is snapshotted; the
  newest `history_depth` are retained (bonus: restore from an earlier session).
