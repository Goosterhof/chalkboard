# CLAUDE.md — The Chalkboard

The Chalkboard is a Windows desktop wallpaper that erases and rewrites
itself every few minutes with a live dashboard: your open PRs, the PRs
waiting on your review, and recent commit activity across a tracked list
of repositories. No photo survives underneath it — the desktop background
*is* the readout.

Since v2 the board *looks like its name*: a café blackboard. Black slate
with eraser smudges and ghost scribbles, tall Amatic SC chalk caps, dotted
menu leaders running out to PR ages like prices, hand-drawn check marks,
per-repo commit sparklines in yellow chalk under **THE REGULARS**, and a
Caveat script hand for annotations. The menu-board face was chosen by the
investor from a three-way audition (slate / menu board / blueprint) on
2026-08-08; the audition renders live in the session scratchpad, the losing
directions were not archived.

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
panels (Sentinel status, experiment health) can be grafted on later
without a rewrite.

## Architecture

```
gh CLI (already authenticated as Goosterhof)
   │
   ▼
render_wallpaper.py   — entry point: lock → fetch → render → set wallpaper → exit
   ├─ fetch_data.py    — gh CLI wrappers: your open PRs (+ per-PR check &
   │                     review status via `gh pr view`), review-requested
   │                     PRs, per-repo 14-day commit buckets + newest
   │                     commit. Raises ChalkboardFetchError on any failure
   │                     so the caller can bail without touching the
   │                     wallpaper. Also carries the Kendo seam (below).
   ├─ render.py        — the menu-board composition: layout in 2560×1440
   │                     design units, scaled to the actual primary screen
   │                     (ctypes GetSystemMetrics; `preview_size` fallback
   │                     off-Windows)
   ├─ chalk.py         — the chalk physics: board texture (mottling, eraser
   │                     smudges, ghost scribbles, vignette), per-colour
   │                     ChalkLayer masks composited with noise-modulated
   │                     alpha so strokes skip like real chalk, wobbly
   │                     hand-drawn lines/rects/ticks, sparklines, dotted
   │                     leaders, dust
   └─ set_wallpaper.py — ctypes SystemParametersInfoW call (no-op logger
                          off-Windows so bench previews just leave the PNG)
   │
   ▼
Windows Task Scheduler — "Chalkboard" task, fires every config.json's
                          refresh_minutes (see scripts/install-task.ps1)
```

No persistent background process. Each run: acquire a file lock (via
`msvcrt`, so an overrun previous cycle can't stack with the next
Task-Scheduler trigger) → fetch → render → apply → release lock → exit. A
fetch failure logs a warning and leaves the last chalked PNG in place
rather than blanking or crashing the desktop. The board texture is
re-seeded every cycle, so each rechalking leaves slightly different eraser
history — the surface itself says "rewritten".

## File layout

```
chalkboard/
├── config.json           — tracked repos, refresh interval, gh timeout,
│                            output/log/lock paths, font dir, kendo seam
├── fetch_data.py          — gh CLI wrappers + Kendo seam + mock_data() fixture
├── chalk.py               — chalk rendering toolkit (textures, strokes, grain)
├── render.py              — menu-board layout renderer
├── set_wallpaper.py       — SystemParametersInfoW wrapper
├── render_wallpaper.py    — entry point (lock → fetch → render → set)
├── requirements.txt       — Pillow, numpy
├── fonts/                 — bundled OFL faces: Amatic SC 400/700 (chalk
│                            caps), Caveat 500 (script hand) + OFL licences.
│                            Bundled because Windows ships neither; Caveat
│                            is the same hand the Mezzanine's Field Journal
│                            writes in.
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
- `activity_days` — the sparkline window (default 14): daily commit-count
  buckets per tracked repo, fetched as one `gh api` call per repo.
- `ignore_bot_reviews` — default `true`: drops `*[bot]` authors (read:
  dependabot) from the review queue so the humans waiting on you aren't
  buried under the bot tail. The authored column is never filtered.
- `refresh_minutes` — read by `scripts/install-task.ps1` when registering
  the scheduled task; changing it requires re-running the install script.
  Also chalked into the footer rail.
- `gh_timeout_seconds` — subprocess timeout per `gh` call, so a hung
  network doesn't stack Task Scheduler runs on top of each other.
- `output_path` / `log_path` / `lock_path` — `%LOCALAPPDATA%\chalkboard\`
  by default; `os.path.expandvars` resolves the env var at runtime.
- `font_dir` — repo-relative directory with the bundled TTFs. Falls back to
  PIL's bitmap default font with a logged warning if a face is missing —
  the panel still renders, just uglier.
- `preview_size` — `[width, height]` used when the Windows display API is
  unavailable (bench previews on Linux/WSL).
- `kendo` — the chef's-note seam, **disabled by default**:
  `{"enabled": bool, "counts_command": "..."}`. When enabled, the command
  runs each cycle and must print JSON like
  `{"plate": 4, "sprint": "S34", "served": 12, "total": 20}` on stdout;
  the values are chalked into the footer rail
  (`CHEF'S NOTE: 4 ON YOUR PLATE · SPRINT S34 — 12/20 SERVED`). The command
  and any token it needs are provisioned by the investor by hand — the
  Chalkboard never manages credentials. Any failure logs a warning and
  skips the note; the board never breaks over the kitchen.

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

On a non-Windows bench, `render_wallpaper.py --mock` renders at
`preview_size` and logs where the PNG landed instead of applying it — the
fastest way to iterate on `render.py`/`chalk.py` is to point `output_path`
somewhere inspectable and look at pixels.

## Fetch surface (v2)

- **Authored PRs** — `gh search prs --author=@me --state=open`, newest
  first, then one `gh pr view --json statusCheckRollup,reviewDecision` per
  displayed PR (capped at 4) for the check mark (mint ✓ green / rose ✗ red /
  yellow ~ pending) and the review line (`approved`, `changes requested`,
  `waiting for review`).
- **Review requests** — `gh search prs --review-requested=@me` with author
  and age, bot authors filtered (see `ignore_bot_reviews`), longest-waiting
  first; the authored column runs newest-first.
- **Activity** — `gh api repos/{o}/{r}/commits?since=…`, paginated
  manually up to 5 pages (a busy fortnight blows straight past `per_page`'s
  silent 100 cap — the sparklines flatlined at exactly 100 before this; and
  `--paginate --slurp` doesn't exist on every installed gh, so page numbers
  it is), bucketed locally into daily counts; the newest commit feeds the
  "N this week — message" line under each regular's sparkline.
- Ages are humanized (`5h`, `2d`) from `createdAt` — menu prices, not
  timestamps.

## Known limitations (v2)

- Primary monitor only — `GetSystemMetrics(0/1)` ignores multi-monitor
  setups.
- No Sentinel/CI yet — not a candidate for the public-repo Sentinel roster
  until it earns one.
- Layout is static/grid-based by design: 3 PRs per column (an overflow
  line names how many more), sparkline slots split the width evenly.
  Revisit if the review queue regularly overflows.
- The Kendo chef's note ships as a seam only — `enabled: false` until the
  investor mints a token and wires `counts_command`.
- Turning it off doesn't restore your prior wallpaper — nothing saves the
  original path. Pick a new background manually if you stop running this.

## Naming

"Chalkboard" was chosen over The Annunciator, The Marquee, and The Ticker
— it leans hardest into the laboratory motif: a scientist's board, erased
and rewritten every cycle with fresh readings, rather than a static
report. v2 committed to the name visually: the menu-board face means the
board now reads as chalk on slate, not as a terminal screenshot on a dark
rectangle.
