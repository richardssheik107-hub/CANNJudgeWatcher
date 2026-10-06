"""Check local runtime and existing synthetic data without opening a writable DB."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import zlib


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required")
    for module in ("fastapi", "uvicorn", "httpx"):
        importlib.import_module(module)
    if args.db is None:
        print("Python and runtime dependencies are available.")
        return
    path = args.db.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        definitions = {
            sid: json.loads(definition)
            for sid, definition in db.execute("SELECT id, definition FROM scopes")
        }
        if not definitions or {s.get("group") for s in definitions.values()} != {"A", "B"}:
            raise ValueError("Existing DB must contain both synthetic A and B groups")
        for scope in definitions.values():
            if (
                scope.get("demo") is not True
                or scope.get("epoch") != "synthetic-v1"
                or scope.get("contest_id") != "demo-" + scope["group"]
                or not scope.get("problems")
            ):
                raise ValueError("Existing DB contains non-demo or unknown scope data")
        counts = dict.fromkeys(definitions, 0)
        for sid, compressed in db.execute("SELECT scope_id, data FROM snapshots"):
            snapshot = json.loads(zlib.decompress(compressed))
            if (
                sid not in definitions
                or snapshot.get("source") != "synthetic-demo"
                or snapshot.get("scope") != definitions[sid]
                or not snapshot.get("observations")
                or not snapshot.get("totals")
            ):
                raise ValueError("Existing DB contains non-demo or incomplete snapshots")
            counts[sid] += 1
        if any(count == 0 for count in counts.values()):
            raise ValueError("Existing demo scope has no snapshots")
        for (sid,) in db.execute("SELECT DISTINCT scope_id FROM evidence"):
            if sid not in definitions:
                raise ValueError("Existing DB contains unrelated evidence")
        if db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0:
            raise ValueError("Existing demo DB has no evidence")
    print("Existing synthetic A/B demo verified in read-only mode; data will be reused.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, sqlite3.Error, ImportError, zlib.error) as exc:
        print(f"Local demo check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
