"""Export an existing sanitized formal evidence package without inventing scores.

Run from the repository root. Output is a new directory, never an existing one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from tradingagents.runapi.redact import Redactor


def package(source: Path, destination: Path, scores: Path) -> Path:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Destination must be a new independent directory")
    cohort = source / "cohort.json"
    files = {"cohort.json": cohort, "gov004_scores.json": scores.resolve()}
    records = {}
    for evidence in sorted(source.glob("gov004_*.json")):
        if evidence.name == "gov004_scores.json":
            continue
        data = json.loads(evidence.read_text(encoding="utf-8"))
        if data.get("kind") != "formal":
            raise ValueError("Package formal evidence separately from diagnostics")
        for row in data["cases"]:
            for key in ("report_path", "manifest_path", "run_dir"):
                if not row.get(key):
                    continue
                path = Path(row[key])
                path = (path if path.is_absolute() else source / path).resolve()
                relative = path.relative_to(source).as_posix()
                row[key] = relative
                if key != "run_dir":
                    if not path.is_file():
                        raise ValueError("Referenced artifact is missing")
                    files[relative] = path
        records[evidence.name] = json.dumps(data, ensure_ascii=False, indent=2).encode()
    if not records:
        raise ValueError("No formal evidence to package")
    # Refuse unsafe data; never alter evidence text and invalidate its citations or hashes.
    redactor = Redactor()
    payloads = {name: path.read_bytes() for name, path in files.items()}
    payloads.update(records)
    for name, payload in payloads.items():
        text = payload.decode("utf-8")
        if redactor.scrub(text) != text:
            raise ValueError(f"Potential credential content in {name}; sanitize and re-adjudicate first")
    created = False
    try:
        destination.mkdir(parents=True, exist_ok=False)
        created = True
        inventory = {}
        for name, payload in payloads.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            inventory[name] = hashlib.sha256(payload).hexdigest()
        (destination / "integrity.json").write_text(json.dumps({
            "schema_version": 1, "files": inventory,
            "note": "Integrity does not establish human approval or semantic correctness.",
        }, indent=2) + "\n", encoding="utf-8")
        return destination
    except BaseException:
        if created:
            shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--scores", required=True, type=Path)
    args = parser.parse_args()
    result = package(args.source, args.destination, args.scores)
    print(f"Evidence packaged at {result}; run score_gov004.py against this directory before acceptance.")


if __name__ == "__main__":
    main()
