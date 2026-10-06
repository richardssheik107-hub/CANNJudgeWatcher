"""Offline validation of the fixed public profile and any existing live archive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import zlib

SLUG = "ct_starcup_aiop_final"
SOURCE = "https://cannjudge.cn"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Live configuration must be a JSON object")
    if (
        config.get("transport") != "http"
        or config.get("cookie_env") != ""
        or config.get("history_pages_per_poll") != 0
        or isinstance(config.get("history_pages_per_poll"), bool)
        or config.get("include") != [{"slug": SLUG}]
        or config.get("cli_auth", False) is not False
    ):
        raise ValueError("Profile requires HTTP, exact final slug, cookie_env='', history_pages_per_poll=0 and no CLI authentication")
    print("Public final profile verified; no credentials or submission-list collection enabled.")
    path = args.db.resolve()
    if not path.exists():
        print("Live database does not yet exist; the collector will initialize its separate archive.")
        return
    if not path.is_file():
        raise ValueError("Live database path is not a file")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        scopes = {
            sid: json.loads(definition)
            for sid, definition in db.execute("SELECT id, definition FROM scopes")
        }
        for scope in scopes.values():
            if scope.get("demo") is not False or scope.get("stage") != SLUG:
                raise ValueError("Existing database contains demo data or another contest stage")
        for sid, compressed, imported in db.execute("SELECT scope_id, data, imported FROM snapshots"):
            snapshot = json.loads(zlib.decompress(compressed))
            scope = snapshot.get("scope", {})
            if (
                sid not in scopes or scope.get("demo") is not False
                or scope.get("stage") != SLUG or snapshot.get("source") != SOURCE
                or imported != 0
            ):
                raise ValueError("Existing archive contains unrelated or imported snapshots")
        for (sid,) in db.execute("SELECT DISTINCT scope_id FROM evidence"):
            if sid not in scopes:
                raise ValueError("Existing archive contains unrelated evidence")
    print("Existing public final archive verified read-only; all records will be kept.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, zlib.error) as exc:
        print(f"Starcup live check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
