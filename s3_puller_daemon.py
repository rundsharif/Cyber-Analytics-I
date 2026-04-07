"""
s3_daemon.py
------------
A daemon script that polls an S3 "index" directory for new UUID-named
subdirectories and downloads their contents locally.

Dependencies:
    pip install boto3

AWS credentials should be configured via environment variables, an AWS
credentials file (~/.aws/credentials), or an IAM role attached to the host.
"""

import sqlite3
import time
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ---------------------------------------------------------------------------
# Configuration — edit these or pull from environment variables / a config file
# ---------------------------------------------------------------------------

S3_BUCKET = "email-ingestion-raw-data"
S3_INDEX_DIR = "processed_emails"   # No trailing slash
POLL_INTERVAL_SECONDS = 20                  # How often to check for new folders
LOCAL_DOWNLOAD_ROOT = Path("./processed_emails")      # Where to store downloaded files
DB_PATH = Path("./daemon_state.db")            # SQLite database file

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("s3_daemon.log"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db(db_path: Path) -> sqlite3.Connection:
    """Create (or open) the SQLite database and ensure the schema exists."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS discovered_folders (
            uuid            TEXT PRIMARY KEY,
            discovered_at   TEXT NOT NULL,
            downloaded_at   TEXT,
            status          TEXT NOT NULL DEFAULT 'pending'
            -- status values: pending | complete | failed
        )
    """)
    conn.commit()
    return conn


def get_known_uuids(conn: sqlite3.Connection) -> set[str]:
    """Return all UUIDs that have already been seen (any status)."""
    rows = conn.execute("SELECT uuid FROM discovered_folders").fetchall()
    return {row[0] for row in rows}


def insert_uuid(conn: sqlite3.Connection, uuid: str) -> None:
    """Record a newly discovered UUID with status 'pending'."""
    conn.execute(
        "INSERT OR IGNORE INTO discovered_folders (uuid, discovered_at) VALUES (?, ?)",
        (uuid, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def mark_complete(conn: sqlite3.Connection, uuid: str) -> None:
    conn.execute(
        "UPDATE discovered_folders SET status='complete', downloaded_at=? WHERE uuid=?",
        (datetime.now(timezone.utc).isoformat(), uuid),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, uuid: str) -> None:
    conn.execute(
        "UPDATE discovered_folders SET status='failed' WHERE uuid=?",
        (uuid,),
    )
    conn.commit()


def get_pending_uuids(conn: sqlite3.Connection) -> list[str]:
    """Return UUIDs that still need to be downloaded (pending or previously failed)."""
    rows = conn.execute(
        "SELECT uuid FROM discovered_folders WHERE status IN ('pending', 'failed')"
    ).fetchall()
    return [row[0] for row in rows]

# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def list_uuid_folders(s3_client, bucket: str, index_dir: str) -> list[str]:
    """
    List all 'subdirectory' prefixes directly under index_dir/.
    Returns a list of UUID strings (not full S3 prefixes).
    """
    prefix = f"{index_dir}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    uuids = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for common_prefix in page.get("CommonPrefixes", []):
            # common_prefix["Prefix"] looks like "index_dir/some-uuid/"
            full_prefix = common_prefix["Prefix"]
            uuid = full_prefix.rstrip("/").split("/")[-1]
            uuids.append(uuid)

    return uuids


def download_uuid_folder(s3_client, bucket: str, index_dir: str, uuid: str, local_root: Path) -> None:
    """
    Download all objects under {index_dir}/{uuid}/ into local_root/{uuid}/.
    Raises an exception if any download fails.
    """
    s3_prefix = f"{index_dir}/{uuid}/"
    local_dir = local_root / uuid
    local_dir.mkdir(parents=True, exist_ok=True)

    paginator = s3_client.get_paginator("list_objects_v2")
    downloaded_count = 0

    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        for obj in page.get("Contents", []):
            s3_key = obj["Key"]
            # Preserve relative path within the UUID folder
            relative_path = s3_key[len(s3_prefix):]
            if not relative_path:
                continue  # Skip the folder "object" itself if it exists

            local_file = local_dir / relative_path
            local_file.parent.mkdir(parents=True, exist_ok=True)

            log.info("  Downloading s3://%s/%s -> %s", bucket, s3_key, local_file)
            s3_client.download_file(bucket, s3_key, str(local_file))
            downloaded_count += 1

    log.info("  Downloaded %d file(s) for UUID %s", downloaded_count, uuid)

# ---------------------------------------------------------------------------
# Core daemon loop
# ---------------------------------------------------------------------------

def poll_once(s3_client, conn: sqlite3.Connection) -> None:
    """
    Single poll cycle:
      1. List all UUID folders currently in S3.
      2. Record any new ones in the DB.
      3. Attempt to download everything that is pending / previously failed.
    """
    log.info("Polling s3://%s/%s ...", S3_BUCKET, S3_INDEX_DIR)

    # --- Discover ---
    try:
        s3_uuids = list_uuid_folders(s3_client, S3_BUCKET, S3_INDEX_DIR)
    except (BotoCoreError, ClientError) as exc:
        log.error("Failed to list S3 folder: %s", exc)
        return

    known_uuids = get_known_uuids(conn)
    new_uuids = [u for u in s3_uuids if u not in known_uuids]

    if new_uuids:
        log.info("Found %d new UUID(s): %s", len(new_uuids), new_uuids)
        for uuid in new_uuids:
            insert_uuid(conn, uuid)
    else:
        log.info("No new UUIDs found.")

    # --- Download ---
    pending = get_pending_uuids(conn)
    if not pending:
        return

    log.info("%d UUID(s) queued for download.", len(pending))
    for uuid in pending:
        log.info("Downloading UUID: %s", uuid)
        try:
            download_uuid_folder(s3_client, S3_BUCKET, S3_INDEX_DIR, uuid, LOCAL_DOWNLOAD_ROOT)
            mark_complete(conn, uuid)
            log.info("UUID %s marked complete.", uuid)
        except (BotoCoreError, ClientError, OSError) as exc:
            log.error("Failed to download UUID %s: %s", uuid, exc)
            mark_failed(conn, uuid)


def run_daemon() -> None:
    """Initialise resources and enter the polling loop."""
    LOCAL_DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    conn = init_db(DB_PATH)
    log.info("Database ready at %s", DB_PATH)

    s3_client = boto3.client("s3")
    log.info("S3 client ready. Starting daemon (poll interval: %ds).", POLL_INTERVAL_SECONDS)

    try:
        while True:
            poll_once(s3_client, conn)
            log.info("Sleeping for %d seconds...\n", POLL_INTERVAL_SECONDS)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log.info("Daemon stopped by user.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_daemon()
