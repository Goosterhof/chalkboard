"""Chalkboard data collectors — `gh` CLI wrappers plus the Kendo seam.

Every GitHub call shells out to the already-authenticated `gh` session;
nothing here manages a token. A failed call raises ChalkboardFetchError so
the caller can decide whether to keep the last rendered wallpaper.
"""

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone


class ChalkboardFetchError(RuntimeError):
    """Raised when a `gh` call fails, times out, or returns unparsable JSON."""


def _run_gh(args, timeout_seconds):
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            encoding="utf-8",
            timeout=timeout_seconds,
            check=True,
        )
    except FileNotFoundError as exc:
        raise ChalkboardFetchError("gh CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ChalkboardFetchError(f"gh {' '.join(args)} timed out after {timeout_seconds}s") from exc
    except subprocess.CalledProcessError as exc:
        raise ChalkboardFetchError(f"gh {' '.join(args)} failed: {exc.stderr.strip()}") from exc

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ChalkboardFetchError(f"gh {' '.join(args)} returned unparsable JSON") from exc


def humanize_age(iso_stamp):
    """'2026-08-06T09:14:00Z' -> '2d' / '5h' / '12m' — menu prices, not timestamps."""
    try:
        then = datetime.fromisoformat(iso_stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "?"
    delta = datetime.now(timezone.utc) - then
    if delta.days >= 1:
        return f"{delta.days}d"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h"
    return f"{max(delta.seconds // 60, 1)}m"


def _summarize_checks(rollup):
    """statusCheckRollup contexts -> green / red / pending / none."""
    if not rollup:
        return "none"
    states = {(c.get("conclusion") or c.get("state") or c.get("status") or "").upper() for c in rollup}
    if states & {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
        return "red"
    if states & {"", "PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED"}:
        return "pending"
    return "green"


_REVIEW_TEXT = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes requested",
    "REVIEW_REQUIRED": "waiting for review",
}


def _pr_detail(name_with_owner, number, timeout_seconds):
    """Per-PR check + review status. One extra call per open PR — the
    authored list is short, so this stays well under a cycle budget."""
    try:
        detail = _run_gh(
            ["pr", "view", str(number), "--repo", name_with_owner,
             "--json", "statusCheckRollup,reviewDecision"],
            timeout_seconds,
        )
    except ChalkboardFetchError as exc:
        logging.warning("PR detail fetch failed for %s#%s: %s", name_with_owner, number, exc)
        return "none", ""
    checks = _summarize_checks(detail.get("statusCheckRollup"))
    review = _REVIEW_TEXT.get(detail.get("reviewDecision") or "", "")
    return checks, review


def get_my_open_prs(timeout_seconds=20, detail_cap=4):
    raw = _run_gh(
        [
            "search", "prs",
            "--author=@me",
            "--state=open",
            "--json", "repository,title,url,number,createdAt",
        ],
        timeout_seconds,
    )
    # newest ink first — the freshest work tops the specials board
    raw.sort(key=lambda pr: pr.get("createdAt", ""), reverse=True)
    prs = []
    for i, pr in enumerate(raw):
        nwo = pr.get("repository", {}).get("nameWithOwner", "")
        checks, review = ("none", "") if i >= detail_cap or not nwo else _pr_detail(
            nwo, pr.get("number"), timeout_seconds)
        prs.append({
            "repo": pr.get("repository", {}).get("name", "?"),
            "number": pr.get("number", 0),
            "title": pr.get("title", ""),
            "age": humanize_age(pr.get("createdAt", "")),
            "checks": checks,
            "review": review,
        })
    return prs


def get_review_requested_prs(timeout_seconds=20, ignore_bots=True):
    raw = _run_gh(
        [
            "search", "prs",
            "--review-requested=@me",
            "--state=open",
            "--json", "repository,title,url,number,createdAt,author",
        ],
        timeout_seconds,
    )
    if ignore_bots:
        # dependabot alone can bury every human PR on the board; the drain
        # skill owns the bot tail, the board watches for people
        raw = [pr for pr in raw if not pr.get("author", {}).get("login", "").endswith("[bot]")]
    # longest-waiting first — the order they're going cold in
    raw.sort(key=lambda pr: pr.get("createdAt", ""))
    return [
        {
            "repo": pr.get("repository", {}).get("name", "?"),
            "number": pr.get("number", 0),
            "title": pr.get("title", ""),
            "author": pr.get("author", {}).get("login", "?"),
            "age": humanize_age(pr.get("createdAt", "")),
        }
        for pr in raw
    ]


def get_repo_activity(owner, repo, days=14, timeout_seconds=20):
    """Daily commit counts for the trailing window, oldest -> newest, plus
    the newest commit. One `gh api` call per repo."""
    since = (datetime.now(timezone.utc) - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    # Manual pagination: a busy fortnight blows straight past per_page's
    # silent 100 cap (the sparklines flatlined at exactly 100 before this),
    # and gh's --paginate --slurp doesn't exist on every installed gh
    # version — page numbers work everywhere.
    raw, page = [], 1
    while page <= 5:
        # `gh api` silently switches to POST once a -F/-f param is present
        # unless --method is forced — without --method GET this 404s.
        batch = _run_gh(
            [
                "api", f"repos/{owner}/{repo}/commits",
                "--method", "GET",
                "-F", "per_page=100",
                "-F", f"page={page}",
                "-f", f"since={since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                "--jq", "map({message: (.commit.message | split(\"\\n\")[0]), author: .commit.author.name, date: .commit.author.date, sha: .sha[0:7]})",
            ],
            timeout_seconds,
        )
        raw.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    else:
        logging.warning("%s/%s: over 500 commits in the window — sparkline is undercounting.", owner, repo)
    buckets = [0] * days
    for commit in raw:
        try:
            when = datetime.fromisoformat(commit["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        idx = (when - since).days
        if 0 <= idx < days:
            buckets[idx] += 1
    last = raw[0] if raw else None
    return buckets, last


def get_kendo_counts(kendo_config, timeout_seconds=20):
    """The Kendo seam — runs the configured command and expects JSON like
    {"plate": 4, "sprint": "S34", "served": 12, "total": 20} on stdout.
    The command (and any token it needs) is provisioned by the investor;
    the Chalkboard never manages credentials itself. Returns None (and the
    board simply skips the chef's note) unless enabled and healthy."""
    if not kendo_config or not kendo_config.get("enabled"):
        return None
    command = kendo_config.get("counts_command")
    if not command:
        logging.warning("Kendo enabled but no counts_command configured — skipping the chef's note.")
        return None
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, encoding="utf-8",
            timeout=timeout_seconds, check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
        logging.warning("Kendo counts fetch failed — skipping the chef's note: %s", exc)
        return None


def mock_data():
    """Static fixture for --mock runs — iterate on render.py without touching `gh` or the network."""
    return {
        "my_prs": [
            {"repo": "kendo", "number": 412, "title": "Add sprint velocity chart to the report tool",
             "age": "2d", "checks": "green", "review": "approved"},
            {"repo": "zmuuzn", "number": 108, "title": "Graft The Chalkboard gadget",
             "age": "5h", "checks": "pending", "review": "waiting for review"},
            {"repo": "war-room", "number": 51, "title": "Territory clock drift fix for the general's map",
             "age": "1d", "checks": "red", "review": "changes requested"},
        ],
        "review_prs": [
            {"repo": "emmie-app", "number": 233, "title": "Cohort export: stream instead of buffering",
             "author": "jvries", "age": "4h"},
            {"repo": "kendo", "number": 415, "title": "Label sync race on bulk update",
             "author": "rjansen", "age": "1d"},
            {"repo": "ubl-genie", "number": 88, "title": "Invoice line rounding under reverse charge",
             "author": "mpostma", "age": "3d"},
        ],
        "activity": {
            "emmie-app": [3, 5, 2, 0, 0, 4, 6, 3, 1, 0, 2, 5, 4, 2],
            "kendo":     [1, 2, 4, 6, 3, 2, 0, 0, 5, 7, 4, 3, 6, 8],
            "ubl-genie": [0, 1, 0, 2, 1, 0, 0, 0, 1, 3, 2, 0, 1, 0],
            "war-room":  [2, 0, 1, 3, 0, 0, 2, 4, 1, 2, 0, 1, 3, 2],
            "zmuuzn":    [4, 6, 3, 2, 5, 1, 0, 3, 6, 4, 7, 5, 2, 6],
        },
        "last_commit": {
            "emmie-app": {"sha": "a1b2c3d", "message": "fix: correct timezone drift in cohort export", "author": "J. Vries"},
            "kendo":     {"sha": "f00baar", "message": "feat: sprint burndown widget", "author": "S. Bakker"},
            "ubl-genie": {"sha": "e77d0e1", "message": "chore: bump laravel to 12.21", "author": "M. Postma"},
            "war-room":  {"sha": "0ddba11", "message": "docs: ADR-0021 PHPStan rule adoption notes", "author": "Goosterhof"},
            "zmuuzn":    {"sha": "892c6a2", "message": "docs(chaos): autopsy report for the Prompt Book restage", "author": "Goosterhof"},
        },
        "kendo": {"plate": 4, "sprint": "S34", "served": 12, "total": 20},
        "stamp": "FRI 8 AUG · RECHALKED 16:20",
    }
