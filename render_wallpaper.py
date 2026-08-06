"""Chalkboard entry point: fetch -> render -> chalk the desktop -> exit.

Run manually with `python render_wallpaper.py`, or `--mock` to render from
the fixture in fetch_data.mock_data() without touching `gh` or the network.
Windows Task Scheduler calls this on a timer — see scripts/install-task.ps1.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import msvcrt  # noqa: E402  (Windows-only; this gadget never runs elsewhere)

from fetch_data import (  # noqa: E402
    ChalkboardFetchError,
    get_my_open_prs,
    get_repo_commits,
    get_review_requested_prs,
    mock_data,
)
from render import render_dashboard  # noqa: E402
from set_wallpaper import set_wallpaper  # noqa: E402

CONFIG_PATH = BASE_DIR / "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def expand(path_str):
    return Path(os.path.expandvars(path_str))


def acquire_lock(lock_path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return None
    return fh


def release_lock(lock_fh):
    if lock_fh is None:
        return
    lock_fh.seek(0)
    try:
        msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    lock_fh.close()


def collect(config):
    my_prs = get_my_open_prs(config.get("gh_timeout_seconds", 20))
    review_prs = get_review_requested_prs(config.get("gh_timeout_seconds", 20))
    commits = {}
    for repo in config["tracked_repos"]:
        try:
            commits[repo["name"]] = get_repo_commits(
                repo["owner"],
                repo["repo"],
                config.get("commits_per_repo", 6),
                config.get("gh_timeout_seconds", 20),
            )
        except ChalkboardFetchError as exc:
            logging.warning("Commit fetch failed for %s: %s", repo["name"], exc)
            commits[repo["name"]] = []
    return {
        "my_prs": my_prs,
        "review_prs": review_prs,
        "commits": commits,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    config = load_config()

    log_path = expand(config["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    lock_path = expand(config["lock_path"])
    lock_fh = acquire_lock(lock_path)
    if lock_fh is None:
        logging.info("Previous chalking cycle still in flight — skipping this one.")
        return

    try:
        data = mock_data() if "--mock" in sys.argv else collect(config)

        output_path = expand(config["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        render_dashboard(data, config, output_path)
        set_wallpaper(output_path)

        logging.info(
            "Chalked the desktop — %d PRs authored, %d review requests, %d repos tracked.",
            len(data["my_prs"]),
            len(data["review_prs"]),
            len(data["commits"]),
        )
    except ChalkboardFetchError as exc:
        logging.warning("Fetch failed, keeping the last chalked image: %s", exc)
    except Exception:
        logging.exception("Unhandled failure during chalking cycle.")
    finally:
        release_lock(lock_fh)


if __name__ == "__main__":
    main()
