"""Chalkboard data collectors — thin `gh` CLI wrappers.

Every call shells out to the already-authenticated `gh` session; nothing
here manages a token. A failed call raises ChalkboardFetchError so the
caller can decide whether to keep the last rendered wallpaper.
"""

import json
import subprocess


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


def get_my_open_prs(timeout_seconds=20):
    return _run_gh(
        [
            "search", "prs",
            "--author=@me",
            "--state=open",
            "--json", "repository,title,url,updatedAt",
        ],
        timeout_seconds,
    )


def get_review_requested_prs(timeout_seconds=20):
    return _run_gh(
        [
            "search", "prs",
            "--review-requested=@me",
            "--state=open",
            "--json", "repository,title,url,updatedAt",
        ],
        timeout_seconds,
    )


def get_repo_commits(owner, repo, limit=6, timeout_seconds=20):
    # `gh api` silently switches to POST once a -F/-f param is present unless
    # --method is forced — without --method GET this 404s on every call.
    return _run_gh(
        [
            "api", f"repos/{owner}/{repo}/commits",
            "--method", "GET",
            "-F", f"per_page={limit}",
            "--jq", "map({message: .commit.message, author: .commit.author.name, date: .commit.author.date, sha: .sha})",
        ],
        timeout_seconds,
    )


def mock_data():
    """Static fixture for --mock runs — iterate on render.py without touching `gh` or the network."""
    return {
        "my_prs": [
            {"repository": {"name": "kendo"}, "title": "Add sprint velocity chart to the report tool", "url": "#"},
            {"repository": {"name": "zmuuzn"}, "title": "Graft The Chalkboard gadget", "url": "#"},
        ],
        "review_prs": [
            {"repository": {"name": "war-room"}, "title": "ADR-0021: PHPStan rule for log immutability", "url": "#"},
        ],
        "commits": {
            "emmie-app": [
                {"sha": "a1b2c3d", "message": "fix: correct timezone drift in cohort export\n", "author": "J. Vries", "date": "2026-08-06T09:14:00Z"},
            ],
            "kendo": [
                {"sha": "f00baar", "message": "feat: sprint burndown widget\n", "author": "S. Bakker", "date": "2026-08-06T08:02:00Z"},
                {"sha": "cafe123", "message": "fix: label sync race on bulk update\n", "author": "R. Jansen", "date": "2026-08-05T17:45:00Z"},
            ],
            "ubl-genie": [],
            "war-room": [
                {"sha": "0ddba11", "message": "docs: ADR-0021 PHPStan rule adoption notes\n", "author": "Goosterhof", "date": "2026-08-05T14:00:00Z"},
            ],
            "zmuuzn": [
                {"sha": "892c6a2", "message": "docs(chaos): file autopsy report for the Prompt Book restage\n", "author": "Goosterhof", "date": "2026-08-06T10:00:00Z"},
            ],
        },
        "fetched_at": "2026-08-06 12:00:00 (mock)",
    }
