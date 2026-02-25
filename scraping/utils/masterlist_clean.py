#!/usr/bin/env python3
"""
Reads a JSON file from Google Cloud Storage, removes the last 24 entries,
and writes it back to the same object.

Assumption (most common): the JSON is a top-level list (array).
Fallback: if it's a dict, we try common list-keys like "items" / "jobs" / "data".
"""

import json
import sys
from typing import Any, Optional, Tuple

from google.cloud import storage


# -----------------------------
# Config (your inputs)
# -----------------------------
CREDENTIALS_PATH = "/Users/sebastianwinkler/Documents/Jobseite/AI/work_for_elon/service_account_key.json"

BUCKET_NAME = "automotive_comp"
FOLDER_NAME = "audi"
FILE_NAME = f"{FOLDER_NAME}_master.json"

ENTRIES_TO_DELETE = 1


# -----------------------------
# Helpers
# -----------------------------
def guess_list_container(obj: Any) -> Tuple[Optional[list], Optional[str]]:
    """
    Returns (list_ref, key) where:
      - list_ref is the list we should truncate
      - key is None if obj itself is the list, otherwise the dict key holding the list
    """
    if isinstance(obj, list):
        return obj, None

    if isinstance(obj, dict):
        for k in ("items", "jobs", "data", "entries", "results", "master", "records"):
            v = obj.get(k)
            if isinstance(v, list):
                return v, k

    return None, None


def truncate_last_n(lst: list, n: int) -> int:
    if n <= 0:
        return 0
    removed = min(n, len(lst))
    if removed > 0:
        del lst[-removed:]
    return removed


# -----------------------------
# Main
# -----------------------------
def main() -> int:
    object_path = f"{FOLDER_NAME.strip('/')}/{FILE_NAME}"

    client = storage.Client.from_service_account_json(CREDENTIALS_PATH)
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(object_path)

    if not blob.exists(client):
        print(f"ERROR: Object not found: gs://{BUCKET_NAME}/{object_path}", file=sys.stderr)
        return 2

    raw = blob.download_as_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in gs://{BUCKET_NAME}/{object_path}: {e}", file=sys.stderr)
        return 3

    target_list, key = guess_list_container(data)
    if target_list is None:
        print(
            "ERROR: JSON is neither a top-level list nor a dict containing a list under "
            "one of these keys: items/jobs/data/entries/results/master/records.\n"
            f"Top-level type: {type(data).__name__}",
            file=sys.stderr,
        )
        return 4

    before = len(target_list)
    removed = truncate_last_n(target_list, ENTRIES_TO_DELETE)
    after = len(target_list)

    if removed == 0:
        print(f"Nothing removed (list length={before}). No upload needed.")
        return 0

    # Pretty-print so the file stays readable; change to separators=(",", ":") if you want it compact.
    updated_json = json.dumps(data, ensure_ascii=False, indent=2)
    blob.upload_from_string(updated_json, content_type="application/json")

    where = "top-level list" if key is None else f'dict["{key}"] list'
    print(
        f"OK: Removed {removed} entries from {where}.\n"
        f"List length: {before} -> {after}\n"
        f"Wrote back to: gs://{BUCKET_NAME}/{object_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())