#!/usr/bin/env python3
"""Load many JSON files from a directory into MongoDB, then inspect them.

Setup:
    uv sync --group explore
    docker compose up -d   # in this directory

Usage:
    python json-to-mongo.py load    ./data
    python json-to-mongo.py inspect
    python json-to-mongo.py find '{"status": "error"}'
"""
import argparse
import json
import sys
from pathlib import Path

from bson import encode
from bson.errors import InvalidDocument
from pymongo import MongoClient

MAX_DOC_BYTES = 16 * 1024 * 1024 - 4096  # leave headroom under Mongo's 16 MB cap
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "json_inspect"
COLL_NAME = "docs"
BATCH_SIZE = 1000


def iter_docs(path: Path):
    """Yield documents from a .json (object or array) or .jsonl file."""
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
    else:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            yield from data
        else:
            yield data


def load(directory: str, coll):
    root = Path(directory)
    files = [p for p in root.rglob("*") if p.suffix in (".json", ".jsonl")]
    print(f"Found {len(files)} files")

    batch, total, bad, oversized = [], 0, 0, 0
    for i, path in enumerate(files, 1):
        try:
            for doc in iter_docs(path):
                if not isinstance(doc, dict):
                    doc = {"value": doc}
                doc["_source_file"] = str(path.relative_to(root))
                try:
                    size = len(encode(doc))
                except (OverflowError, InvalidDocument) as e:
                    oversized += 1
                    print(f"  skipped doc in {path}: not BSON-encodable ({e})",
                          file=sys.stderr)
                    continue
                if size > MAX_DOC_BYTES:
                    oversized += 1
                    print(f"  skipped doc in {path}: {size / 1e6:.1f} MB exceeds "
                          f"the 16 MB document limit", file=sys.stderr)
                    continue
                batch.append(doc)
                if len(batch) >= BATCH_SIZE:
                    coll.insert_many(batch, ordered=False)
                    total += len(batch)
                    batch = []
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            bad += 1
            print(f"  skipped {path}: {e}", file=sys.stderr)
        if i % 500 == 0:
            print(f"  processed {i}/{len(files)} files")

    if batch:
        coll.insert_many(batch, ordered=False)
        total += len(batch)
    print(f"Inserted {total} documents; {bad} files failed to parse; "
          f"{oversized} documents skipped (too large / not encodable)")


def inspect(coll):
    print("Total documents:", coll.count_documents({}))
    print("Distinct source files:", len(coll.distinct("_source_file")))

    # Which top-level keys exist, how often, and with which types?
    pipeline = [
        {"$project": {"kv": {"$objectToArray": "$$ROOT"}}},
        {"$unwind": "$kv"},
        {"$group": {"_id": {"key": "$kv.k", "type": {"$type": "$kv.v"}},
                    "count": {"$sum": 1}}},
        {"$sort": {"_id.key": 1, "count": -1}},
    ]
    print("\nTop-level fields (key, type, count):")
    for r in coll.aggregate(pipeline, allowDiskUse=True):
        print(f"  {r['_id']['key']:30} {r['_id']['type']:10} {r['count']}")


def find(query: str, coll, limit: int = 5):
    for doc in coll.find(json.loads(query)).limit(limit):
        print(json.dumps(doc, default=str, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load").add_argument("directory")
    sub.add_parser("inspect")
    sub.add_parser("find").add_argument("query")
    args = ap.parse_args()

    coll = MongoClient(MONGO_URI)[DB_NAME][COLL_NAME]
    if args.cmd == "load":
        load(args.directory, coll)
    elif args.cmd == "inspect":
        inspect(coll)
    elif args.cmd == "find":
        find(args.query, coll)


if __name__ == "__main__":
    main()
