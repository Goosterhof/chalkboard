# The Chalkboard

> *A scientist's chalkboard: erased and rewritten every cycle with fresh readings, never a static report.*

The Chalkboard is a Windows desktop wallpaper that regenerates itself on a
timer with a live dashboard: your open pull requests (with check and
review status), the PRs waiting on your review, 14-day commit sparklines
across a tracked list of repositories, and THE PANTRY — the machine's own
stock (memory, disk, uptime) as hand-drawn chalk gauges that hatch rose
when supplies run low. Nothing survives underneath it — the background
*is* the readout.

And it looks like its name: a café blackboard. Black slate with eraser
smudges, tall chalk caps, dotted menu leaders running out to PR ages like
prices, hand-drawn check marks, yellow chalk sparklines. The board texture
is re-seeded every cycle, so each rewrite leaves fresh eraser history.

It has no server, no database, no login. It shells out to your already-
authenticated `gh` CLI, draws a PNG with Pillow + numpy, and applies it as
the desktop background via a Windows API call. Windows Task Scheduler is
the only thing keeping it alive.

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

Everything lives in `config.json` — tracked repos, refresh interval,
sparkline window, output paths, bundled font dir, and the optional Kendo
chef's-note seam. See `CLAUDE.md` for the full schema and architecture
notes.

## Known limitations

- Primary monitor only.
- No CI/Sentinel yet.
- The Kendo chef's note is a disabled seam until a token and
  `counts_command` are provisioned.
- No multi-language support; the panel is English-only.

See `CLAUDE.md` for the full architecture writeup and design rationale.
