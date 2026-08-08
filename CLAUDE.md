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
   │                     wallpaper. Also carries the Kendo seam (below) and
   │                     THE PANTRY collector (psutil: memory, disks,
   │                     uptime — no gh involved).
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
Task-Scheduler trigger) → fetch → render → apply → release lock → exit.
The board texture is re-seeded every cycle, so each rechalking leaves
slightly different eraser history — the surface itself says "rewritten".

**A failed cycle admits it on the wall** (chaos #00110 D3): instead of
leaving the old PNG up with a confidently wrong timestamp, the subtitle
line of the last board is erased and re-chalked in rose —
`~ SERVICE PAUSED · LAST CHALKED 14:12 · GH WENT QUIET ~` (fetch failure)
or `THE KITCHEN HIT A SNAG` (anything else) — and an eraser smudge grows
over the specials with every silent cycle. Cycle memory (last successful
stamp + consecutive-pause count) persists in `state_path`; a healthy cycle
resets it. If no board exists yet, nothing is touched.

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
├── requirements.txt       — Pillow, numpy, psutil
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
- `pantry` — the machine-stock panel:
  `{"enabled": bool, "disks": [{"path": "C:\\", "label": "CELLAR C:"}]}`.
  Renders memory used/total, up to 2 disks (free GB), and uptime
  (`STOVE ON … 6d 4h`) as chalk stock-bars on the right of the bottom
  band; a shelf over 85 % full hatches rose instead of yellow. THE REGULARS
  shrinks to make room — with the pantry off, the sparklines take the full
  width back. Deliberately **no CPU%**: on a minutes-cadence board a CPU
  number is one stale sample wearing a live gauge's costume — fast gauges
  wait for the living board (v3, below). An unreadable disk path logs and
  is skipped; a missing psutil shuts the whole pantry with a warning.
- `refresh_minutes` — read by `scripts/install-task.ps1` when registering
  the scheduled task; changing it requires re-running the install script.
  Also chalked into the footer rail. Dropped 10 → 3 with v2.5 (a full
  cycle is ~16 gh requests — ~320/hr at this cadence, far under the
  5000/hr authenticated ceiling).
- `gh_timeout_seconds` — subprocess timeout per `gh` call, so a hung
  network doesn't stack Task Scheduler runs on top of each other.
- `output_path` / `log_path` / `lock_path` / `state_path` —
  `%LOCALAPPDATA%\chalkboard\` by default; `os.path.expandvars` resolves
  the env var at runtime. `state_path` carries the cycle memory the
  service-pause stamp is written from.
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
  yellow ~ pending / a dim `?` when the detail fetch itself failed — the
  board says "I couldn't read this one" rather than dressing it as no-CI)
  and the review line in the board's own kitchen vocabulary: `plated`
  (approved), `sent back` (changes requested), `still on the pass`
  (waiting) — GitHub's words made the CI tick read as review approval
  (chaos #00110 D2).
- **Review requests** — `gh search prs --review-requested=@me` with author
  and age, bot authors filtered (see `ignore_bot_reviews`), longest-waiting
  first; the authored column runs newest-first.
- **Activity** — `gh api repos/{o}/{r}/commits?since=…`, paginated
  manually up to 5 pages (a busy fortnight blows straight past `per_page`'s
  silent 100 cap — the sparklines flatlined at exactly 100 before this; and
  `--paginate --slurp` doesn't exist on every installed gh, so page numbers
  it is), bucketed locally into daily counts; the newest commit feeds the
  "N/wk — message" caption under each regular's sparkline. The message
  tail is truncated on a word boundary and rides along only when at least
  one whole word of it fits the slot — narrow slots (pantry on, small
  screens) show the count alone rather than a useless ellipsis
  (chaos #00110 D1).
- Ages are humanized (`5h`, `2d`) from `createdAt` — menu prices, not
  timestamps.

## The Registers (v2.6)

The board raises its voice — chaos #00110 D4, designed by the Artisan
against the *measured* live queues (the Monkey's "~5 days" would have
fired on 14 of 16 bench PRs; the real thresholds sit in the gaps of the
age distribution, and the two columns are different populations). Full
spec + restraint ledger: `zmuuzn/documents/design-systems/`
`chalkboard-register-spec.md`. The shape:

- **Eight named moves**, mechanical triggers only: GOING COLD (rose age +
  circle scribble; 7d bench / 4d pass), STONE COLD (14d — the age sets in
  the big hand), EIGHTY-SIXED (red CI strikes the leader, never the
  title), KITCHEN'S CLEAR (empty review column, mint frame), BENCH IS
  BARE (white — a fact, not a celebration), HASN'T BEEN IN (0 commits in
  7 days — the slot demotes to dim), BIG WEEK (≥12 and ≥2× prior — the
  count in the big yellow hand), ROT OFF THE BOARD (hidden overflow's
  oldest ≥14d — the note confesses "the oldest has been sitting 82d").
- **A shout budget** — `MAX_SHOUTS = 3`, priority ROT → STONE COLD → RED
  → COLD → BIG WEEK; losers render quiet fallbacks (rose without circle,
  stroke bump without count, dim confession) — information never
  disappears, only volume comes down. Filling a blank zone or removing
  ink is free.
- **One primitive, one meaning** — a circle always means *waiting on
  you*; it decorates nothing else.
- Every cycle logs `Register: N candidate(s), loud=…, demoted=…` — a week
  of that answers whether MAX_SHOUTS=3 throttles ordinary days (the one
  constant derived from a single day's data).
- Register-stress fixtures: `--mock-loud` (5 candidates vs budget 3, an
  empty pass, a silent regular, rot in the tail) and `--mock-bare`.

## The Living Board (v3 — written down, not started)

The investor asked what a Windows background can actually *be* (2026-08-08).
The answer is a ladder, and v2.x sits on the bottom rung by design:

1. **PNG swap via `SystemParametersInfoW`** (current). Refresh floor is
   minutes; each swap rewrites the transcoded wallpaper and broadcasts a
   settings change. Can never animate — only be a fresher photograph.
2. **`IDesktopWallpaper` COM** — supported API, per-monitor wallpapers +
   slideshow control. Fixes the primary-monitor-only limitation without
   changing the architecture. Cheap; take alongside any other rung.
3. **The WorkerW trick** — message `0x052C` to Progman spawns a WorkerW
   layer between wallpaper and desktop icons; re-parent a real window
   (WebView2/canvas/WebGL) into it and the background becomes a *running
   surface*: self-drawing chalk strokes, drifting dust, breathing gauges,
   live CPU/network — everything the pantry deliberately refuses today.
   This is how Wallpaper Engine and Lively do it. **The tax:** it is an
   undocumented hack. Windows 11 24H2 broke it (WorkerW stopped existing
   at startup; Microsoft placed a compatibility hold on machines running
   wallpaper customizers) until the January 2025 fixes (KB5050009 /
   KB5050094). Stable since, guaranteed never. A living board must also
   pause itself when a fullscreen app/game is up.
4. **Desktop-pinned widget window** (the Rainmeter model) — borderless,
   non-activating, always-at-bottom. Fully supported APIs, coexists with a
   normal wallpaper; but sits *over* the wallpaper and under the icons
   rather than being the background.

**The chosen v3 path when the time comes:** prototype the board as a local
HTML/canvas page hosted by **Lively Wallpaper** (open source, has a CLI,
owns the WorkerW mess + 24H2 patches + pause-on-fullscreen + multi-monitor)
— the chalk aesthetic ports to canvas with the same bundled fonts, and the
prototype proves what "alive" feels like without the lab owning the ledge.
If it earns permanence, the same page moves into a Tauri v2 window the lab
parents into WorkerW itself (Mezzanine already carries the Tauri
patterns), eyes open about the 24H2-class fragility. Rung 2
(`IDesktopWallpaper`) is worth taking in either future.

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
