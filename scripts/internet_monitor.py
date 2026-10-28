#!/usr/bin/env python3

import csv
import socket
import subprocess
import time

from datetime import datetime, timezone
from pathlib import Path


# --------------------------------------------------
# Configuration
# --------------------------------------------------

# Automatically locate the root of the Git repository.
REPO_DIR = Path(__file__).resolve().parent.parent

HISTORY_FILE = REPO_DIR / "internet_history.csv"

# Check connectivity every 30 seconds.
CHECK_INTERVAL = 30

# Maximum time to wait for each connectivity test.
CONNECTION_TIMEOUT = 3

# External endpoints used to test internet connectivity.
TEST_ENDPOINTS = [
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
]


# --------------------------------------------------
# Time and connectivity functions
# --------------------------------------------------

def current_time():
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def internet_available():
    """Return True if at least one endpoint is reachable."""

    for host, port in TEST_ENDPOINTS:
        try:
            with socket.create_connection(
                (host, port),
                timeout=CONNECTION_TIMEOUT
            ):
                return True

        except OSError:
            continue

    return False


# --------------------------------------------------
# History functions
# --------------------------------------------------

def initialize_history():
    """Create the CSV file and header if necessary."""

    if not HISTORY_FILE.exists():
        with open(
            HISTORY_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.writer(file)

            writer.writerow([
                "timestamp_utc",
                "event",
                "outage_duration_seconds"
            ])


def record_event(event, outage_duration=None):
    """Append a connectivity event to the CSV file."""

    timestamp = current_time()

    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            timestamp,
            event,
            (
                outage_duration
                if outage_duration is not None
                else ""
            )
        ])

    print(
        f"[{timestamp}] {event}"
        + (
            f" | Outage duration: {outage_duration} seconds"
            if outage_duration is not None
            else ""
        ),
        flush=True
    )


# --------------------------------------------------
# Git functions
# --------------------------------------------------

def git_command(*args):
    """Execute a Git command inside the repository."""

    return subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=30
    )


def push_history():
    """
    Stage and commit the history file if it changed.
    Then attempt to push to the remote repository.
    """

    try:
        # Stage only the internet history file.
        result = git_command(
            "add",
            "--",
            HISTORY_FILE.name
        )

        if result.returncode != 0:
            print(
                "Git add failed:",
                result.stderr,
                flush=True
            )
            return False

        # Check whether the staged file has changed.
        result = git_command(
            "diff",
            "--cached",
            "--quiet",
            "--",
            HISTORY_FILE.name
        )

        if result.returncode == 1:

            # The history file has staged changes.
            result = git_command(
                "commit",
                "-m",
                "Update internet connectivity history"
            )

            if result.returncode != 0:
                print(
                    "Git commit failed:",
                    result.stderr,
                    flush=True
                )
                return False

        elif result.returncode != 0:

            print(
                "Git diff failed:",
                result.stderr,
                flush=True
            )
            return False

        # Always attempt the push. This also retries a
        # previous push that failed after a local commit.
        result = git_command("push")

        if result.returncode != 0:
            print(
                "Git push failed:",
                result.stderr,
                flush=True
            )
            return False

        print(
            "Internet history successfully pushed to GitHub.",
            flush=True
        )

        return True

    except (OSError, subprocess.TimeoutExpired) as error:

        print(
            f"Git operation failed: {error}",
            flush=True
        )

        return False


# --------------------------------------------------
# Main monitoring loop
# --------------------------------------------------

def main():

    if not REPO_DIR.is_dir():
        raise RuntimeError(
            f"Repository directory does not exist: {REPO_DIR}"
        )

    if not (REPO_DIR / ".git").is_dir():
        raise RuntimeError(
            f"Not a Git repository: {REPO_DIR}"
        )

    initialize_history()

    previous_status = None
    disconnected_at = None

    # A push is needed when a new event is recorded.
    pending_push = False

    print(
        "Internet connectivity monitor started.",
        flush=True
    )

    print(
        f"Repository: {REPO_DIR}",
        flush=True
    )

    while True:

        try:
            online = internet_available()

            status = (
                "CONNECTED"
                if online
                else "DISCONNECTED"
            )

            # Record the initial status and subsequent changes.
            if status != previous_status:

                if status == "DISCONNECTED":

                    disconnected_at = datetime.now(
                        timezone.utc
                    )

                    record_event("DISCONNECTED")

                else:

                    outage_duration = None

                    if disconnected_at is not None:

                        outage_duration = int(
                            (
                                datetime.now(timezone.utc)
                                - disconnected_at
                            ).total_seconds()
                        )

                    record_event(
                        "CONNECTED",
                        outage_duration
                    )

                    disconnected_at = None

                previous_status = status
                pending_push = True

            # Push only when a new event needs uploading.
            # If a push fails, retry on a later online check.
            if online and pending_push:

                if push_history():
                    pending_push = False

            time.sleep(CHECK_INTERVAL)

        except Exception as error:

            print(
                f"Monitor error: {error}",
                flush=True
            )

            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
