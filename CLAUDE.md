# CLAUDE.md — The Chalkboard

The Chalkboard is a Windows desktop wallpaper that erases and rewrites
itself every few minutes with a live dashboard: your open PRs, the PRs
waiting on your review, and recent commit activity across a tracked list
of repositories. No photo survives underneath it — the desktop background
*is* the readout.

This repo lives as a submodule at `zmuuzn/gadgets/chalkboard/` — the
laboratory's fourth gadget and the first that isn't a compiled desktop app
or VS Code extension. It doesn't deploy, has no `/up` health check, no
shared Postgres, and none of the containment protocols that govern the
experiments apply to it: it's a cron-triggered Python script that shells
out to the already-authenticated `gh` CLI and calls `SystemParametersInfoW`.
It earns its place under `gadgets/` the same way Horadric Cube does — a
tool the Mad Scientist uses adjacent to the lab, not a deployed organ of it
— and it's grafted here specifically so it doesn't drift out of the
laboratory's institutional memory the way a bare standalone repo would.
The tracked-repo list currently spans Script-wide work (`emmie-app`,
`kendo`, `ubl-genie`) alongside lab work (`war-room`, `zmuuzn`) — it is not
lab-scoped today, but the config is deliberately data-driven so lab-scoped
panels (Sentinel status, experiment health, Kendo issue counts) can be
grafted on later without a rewrite.

## Architecture

```
gh CLI (already authenticated as Goosterhof)
   │
   ▼
render_wallpaper.py   — entry point: lock → fetch → render → set wallpaper → exit
   ├─ fetch_data.py    — gh CLI wrappers: your open PRs, review-requested PRs,
   │                     per-repo commit history. Raises ChalkboardFetchError
   │                     on any failure so the caller can bail without
   │                     touching the wallpaper.
   ├─ render.py        — Pillow: draws the dark dashboard panel at primary
   │                     screen resolution (ctypes GetSystemMetrics)
   └─ set_wallpaper.py — ctypes SystemParametersInfoW call
   │
   ▼
Windows Task Scheduler — "Chalkboard" task, fires every config.json's
                          refresh_minutes (see scripts/install-task.ps1)
```

No persistent background process. Each run: acquire a file lock (via
`msvcrt`, so an overrun previous cycle can't stack with the next
Task-Scheduler trigger) → fetch → render → apply → release lock → exit. A
fetch failure logs a warning and leaves the last chalked PNG in place
rather than blanking or crashing the desktop.

## File layout

```
chalkboard/
├── config.json           — tracked repos, refresh interval, gh timeout,
│                            output/log/lock paths, font path
├── fetch_data.py          — gh CLI wrappers + mock_data() fixture
├── render.py              — Pillow dashboard renderer
├── set_wallpaper.py       — SystemParametersInfoW wrapper
├── render_wallpaper.py    — entry point (lock → fetch → render → set)
├── requirements.txt       — Pillow
├── scripts/
│   ├── install-task.ps1   — registers the Task Scheduler job (pins cwd +
│   │                        pythonw.exe so relative paths never break)
│   └── uninstall-task.ps1
└── PLAN.md                — superseded by this file; kept for the
                             original design-review trail
```

## Config schema (`config.json`)

- `tracked_repos` — list of `{name, owner, repo}`. `name` is the display
  label; `owner`/`repo` address the GitHub API. Add entries here, not in
  code.
- `commits_per_repo` — how many commits to pull and show per tracked repo.
- `refresh_minutes` — read by `scripts/install-task.ps1` when registering
  the scheduled task; changing it requires re-running the install script.
- `gh_timeout_seconds` — subprocess timeout per `gh` call, so a hung
  network doesn't stack Task Scheduler runs on top of each other.
- `output_path` / `log_path` / `lock_path` — `%LOCALAPPDATA%\chalkboard\`
  by default; `os.path.expandvars` resolves the env var at runtime.
- `font_path` — pinned to `C:\Windows\Fonts\CascadiaMono.ttf` (verified
  present on this machine). Falls back to PIL's bitmap default font with a
  logged warning if missing — the panel still renders, just uglier.

## Running it

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Render from the fixture in fetch_data.mock_data() — no gh calls, no network:
.venv\Scripts\python render_wallpaper.py --mock

# Real run — actually chalks your desktop:
.venv\Scripts\python render_wallpaper.py

# Register the recurring Task Scheduler job:
.venv\Scripts\powershell -File scripts\install-task.ps1
```

## Known limitations (v1)

- Primary monitor only — `GetSystemMetrics(0/1)` ignores multi-monitor
  setups.
- No Sentinel/CI yet — this is a fresh v1 personal tool, not a candidate
  for the public-repo Sentinel roster until it earns one.
- Layout is static/grid-based by design, not dynamically reflowing — kept
  deliberately simple for v1; revisit if commit volume regularly overflows
  the panel.
- Turning it off doesn't restore your prior wallpaper — nothing saves the
  original path. Pick a new background manually if you stop running this.

## Naming

"Chalkboard" was chosen over The Annunciator, The Marquee, and The Ticker
— it leans hardest into the laboratory motif: a scientist's board, erased
and rewritten every cycle with fresh readings, rather than a static
report.
