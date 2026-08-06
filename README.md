# The Chalkboard

> *A scientist's chalkboard: erased and rewritten every cycle with fresh readings, never a static report.*

The Chalkboard is a Windows desktop wallpaper that regenerates itself on a
timer with a live dashboard: your open pull requests, the PRs waiting on
your review, and recent commit activity across a tracked list of
repositories. Nothing survives underneath it — the background *is* the
readout.

It has no server, no database, no login. It shells out to your already-
authenticated `gh` CLI, draws a PNG with Pillow, and applies it as the
desktop background via a Windows API call. Windows Task Scheduler is the
only thing keeping it alive.

## Setup

```powershell
git clone git@github.com:Goosterhof/chalkboard.git
cd chalkboard

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Edit config.json — set your tracked_repos, refresh_minutes, etc.

# Render from the built-in fixture first — no gh calls, no network:
.venv\Scripts\python render_wallpaper.py --mock

# Real run — chalks your actual desktop:
.venv\Scripts\python render_wallpaper.py

# Register the recurring refresh:
powershell -File scripts\install-task.ps1
```

To stop it:

```powershell
powershell -File scripts\uninstall-task.ps1
```

This unregisters the scheduled task but does **not** restore your previous
wallpaper — nothing saves that path. Pick a new background manually if you
want one back.

## Requirements

- Windows (uses `ctypes.windll` and `msvcrt` — this gadget is Windows-only
  by design)
- Python 3.11+
- [GitHub CLI](https://cli.github.com/) (`gh`), already authenticated
  (`gh auth status`)

## Configuration

Everything lives in `config.json` — tracked repos, refresh interval, output
paths, font. See `CLAUDE.md` for the full schema and architecture notes.

## Known limitations

- Primary monitor only.
- No CI/Sentinel yet — this is a fresh v1.
- No multi-language support; the panel is English-only.

See `CLAUDE.md` for the full architecture writeup and design rationale.
