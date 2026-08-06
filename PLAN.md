# GitHub Live Wallpaper Dashboard — Implementation Plan

## Goal
A Windows desktop wallpaper that periodically regenerates itself as an image showing:
1. Your open PRs (across your repos/orgs)
2. PRs where you're requested as a reviewer
3. Recent commit activity on a tracked list of repositories

No wallpaper photo is preserved — it's replaced by a solid dark dashboard-style panel.

## Confirmed tracked repos (commit activity section)
| Requested name | Resolved repo |
|---|---|
| emmie-app | `emmie-app/emmie` |
| kendo | `script-development/kendo` |
| ubl-genie | `Back-to-code/ublgenie-app` |
| war-room | `Goosterhof/war-room` |
| zmuuzn | `Goosterhof/zmuuzn` |

Stored as a simple editable list in the config so more can be added later without touching code.

## Architecture

```
gh CLI (already authenticated as Goosterhof)
   │
   ▼
Python script (render_wallpaper.py)
   ├─ fetch_data.py   → calls `gh api` / `gh pr list` for:
   │                      - your open PRs (search: author:@me is:open is:pr)
   │                      - PRs requesting your review (search: review-requested:@me is:open)
   │                      - recent commits per tracked repo (gh api repos/{owner}/{repo}/commits)
   ├─ render.py       → Pillow: draws a dark-panel dashboard image at your screen resolution
   └─ set_wallpaper.py → ctypes call to SystemParametersInfoW to apply the PNG as wallpaper
   │
   ▼
Windows Task Scheduler → runs the script every N minutes (e.g. 10)
```

No persistent background process. Each run: fetch → render → set wallpaper → exit.

## Auth
Uses the existing `gh` CLI session (already logged in as Goosterhof, token scopes `repo`, `read:org`, etc. — sufficient for PR search and commit reads). Script shells out to `gh` rather than managing its own token.

## Data to fetch (via `gh` commands)
- Your open PRs:
  `gh search prs --author=@me --state=open --json repository,title,url,updatedAt`
- PRs awaiting your review:
  `gh search prs --review-requested=@me --state=open --json repository,title,url,updatedAt`
- Commit activity per tracked repo (last N days or last N commits):
  `gh api repos/{owner}/{repo}/commits --jq '.[] | {message: .commit.message, author: .commit.author.name, date: .commit.author.date}'`
  (limit to last 5–10 commits per repo, or filter by date to "last 24–48h" so the panel stays relevant)

## Rendering (Pillow)
- Canvas sized to primary monitor resolution (detect via `ctypes.windll.user32.GetSystemMetrics`).
- Dark background (#1a1a1a or similar), simple card/dashboard layout:
  - Section 1: "Your open PRs" — list with repo name + title, truncated
  - Section 2: "Awaiting your review" — same format
  - Section 3: "Recent commits" — grouped by tracked repo, most recent first
  - Footer: last-updated timestamp
- Font: a clean monospace or system font bundled or referenced from Windows fonts dir.
- Keep layout static/grid-based (not dynamic reflow) to keep rendering code simple.

## Wallpaper application
- Save rendered PNG to a fixed path (e.g. `%LOCALAPPDATA%\github-wallpaper\current.png`).
- Call `SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)` via `ctypes`.

## Scheduling
- Windows Task Scheduler task, trigger: "every 10 minutes", action: run `python render_wallpaper.py` (or a compiled/packaged version, or just point at the venv's pythonw.exe to avoid a console flash).
- Rate-limit consideration: `gh` API calls easily stay within GitHub's rate limits at a 10-minute cadence given the small repo list.

## File layout (proposed)
```
github-wallpaper-dashboard/
  config.json            # tracked repos list, refresh interval, output path
  fetch_data.py
  render.py
  set_wallpaper.py
  render_wallpaper.py    # entry point: fetch → render → set
  requirements.txt       # Pillow
  PLAN.md                # this file
```

## Open items to decide during implementation
- Exact visual layout/spacing — do a first pass, iterate visually.
- How many commits/PRs to show before truncating (avoid an overly tall panel).
- Whether to add error handling for `gh` calls failing (e.g. no network) — probably: skip refresh, keep last rendered image, log to a file.
- Multi-monitor behavior — target primary monitor only for v1.

## Environment notes (already verified)
- `gh` CLI v2.85.0 installed and authenticated as `Goosterhof`.
- Python 3.13.1 installed; Pillow **not yet installed** (`pip install Pillow` needed).
