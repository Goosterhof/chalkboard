"""Chalkboard entry point: fetch -> render -> chalk the desktop -> exit.

Run manually with `python render_wallpaper.py`, or `--mock` to render from
the fixture in fetch_data.mock_data() without touching `gh` or the network.
Windows Task Scheduler calls this on a timer — see scripts/install-task.ps1.
On non-Windows hosts (bench previews) locking and wallpaper application are
skipped and the PNG lands at output_path for inspection.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    import msvcrt

from fetch_data import (  # noqa: E402
    ChalkboardFetchError,
    get_kendo_counts,
    get_machine_specs,
    get_my_open_prs,
    get_repo_activity,
    get_review_requested_prs,
    mock_bare_data,
    mock_data,
    mock_loud_data,
)
from render import chalk_service_pause, render_dashboard  # noqa: E402
from set_wallpaper import set_wallpaper  # noqa: E402

CONFIG_PATH = BASE_DIR / "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state(state_path):
    """Cycle memory: the last successful chalking time and how many cycles
    have failed since — what the service-pause stamp is written from."""
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(state_path, state):
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError as exc:
        logging.warning("Couldn't persist cycle state: %s", exc)


def mark_paused(config, output_path, state_path, state, reason):
    """A failed cycle must not leave a confidently wrong timestamp on the
    wall (chaos #00110 D3) — restamp the old board as paused and re-apply."""
    pauses = state.get("pauses", 0) + 1
    save_state(state_path, {**state, "pauses": pauses})
    try:
        if chalk_service_pause(output_path, config, state.get("last_stamp", "?"), pauses, reason):
            set_wallpaper(output_path)
    except Exception:
        logging.exception("Couldn't chalk the service-pause notice.")


def expand(path_str):
    return Path(os.path.expandvars(path_str))


def acquire_lock(lock_path):
    if not IS_WINDOWS:
        return "no-lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        return None
    return fh


def release_lock(lock_fh):
    if lock_fh is None or lock_fh == "no-lock":
        return
    lock_fh.seek(0)
    try:
        msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    lock_fh.close()


def make_stamp():
    return time.strftime("%a %-d %b · rechalked %H:%M" if os.name != "nt"
                         else "%a %#d %b · rechalked %H:%M").upper()


def collect(config):
    timeout = config.get("gh_timeout_seconds", 20)
    my_prs = get_my_open_prs(timeout)
    review_prs = get_review_requested_prs(timeout, config.get("ignore_bot_reviews", True))
    activity, last_commit = {}, {}
    for repo in config["tracked_repos"]:
        try:
            buckets, last = get_repo_activity(
                repo["owner"], repo["repo"],
                config.get("activity_days", 14), timeout,
            )
        except ChalkboardFetchError as exc:
            logging.warning("Activity fetch failed for %s: %s", repo["name"], exc)
            buckets, last = [], None
        activity[repo["name"]] = buckets
        if last:
            last_commit[repo["name"]] = last
    return {
        "my_prs": my_prs,
        "review_prs": review_prs,
        "activity": activity,
        "last_commit": last_commit,
        "kendo": get_kendo_counts(config.get("kendo"), timeout),
        "pantry": get_machine_specs(config.get("pantry")),
        "stamp": make_stamp(),
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

    output_path = expand(config["output_path"])
    state_path = expand(config.get("state_path", "%LOCALAPPDATA%\\chalkboard\\state.json"))
    state = load_state(state_path)

    try:
        if "--mock-loud" in sys.argv:      # register stress: 5 candidates vs budget 3
            data = mock_loud_data()
        elif "--mock-bare" in sys.argv:    # the empty-bench register
            data = mock_bare_data()
        elif "--mock" in sys.argv:
            data = mock_data()
        else:
            data = collect(config)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        render_dashboard(data, config, output_path)
        set_wallpaper(output_path)
        save_state(state_path, {"last_stamp": time.strftime("%H:%M"), "pauses": 0})

        logging.info(
            "Chalked the desktop — %d PRs authored, %d review requests, %d repos on the board.",
            len(data["my_prs"]),
            len(data["review_prs"]),
            len(data["activity"]),
        )
    except ChalkboardFetchError as exc:
        logging.warning("Fetch failed — restamping the board as paused: %s", exc)
        mark_paused(config, output_path, state_path, state, "GH WENT QUIET")
    except Exception:
        logging.exception("Unhandled failure during chalking cycle — restamping the board as paused.")
        mark_paused(config, output_path, state_path, state, "THE KITCHEN HIT A SNAG")
    finally:
        release_lock(lock_fh)


if __name__ == "__main__":
    main()
