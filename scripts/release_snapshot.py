#!/usr/bin/env python3
"""Create and verify source snapshots used for dbt version rollback."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_PARTS = (
    "Dockerfile",
    "requirements.txt",
    "dbt_project.yml",
    "packages.yml",
    "package-lock.yml",
    "models",
    "macros",
    "tests",
    "seeds",
    "snapshots",
    "analyses",
)
TARGETS = {"dev": "dev", "staging": "staging", "production": "prod"}


def project_files(project_dir):
    if project_dir.is_symlink():
        raise ValueError("Release project directory cannot be a symlink")
    files = []
    for part in PROJECT_PARTS:
        path = project_dir / part
        if path.is_symlink():
            raise ValueError(f"Symlink is not allowed in a release: {part}")
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for root, dirs, names in os.walk(path, followlinks=False):
            for name in dirs + names:
                child = Path(root) / name
                if child.is_symlink():
                    raise ValueError(f"Symlink is not allowed in a release: {child}")
            files.extend(Path(root) / name for name in names)
    if not (project_dir / "dbt_project.yml").is_file():
        raise ValueError("dbt_project.yml is required")
    return sorted(files)


def digests(project_dir):
    return {
        path.relative_to(project_dir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in project_files(project_dir)
    }


def fingerprint(project_dir):
    encoded = json.dumps(digests(project_dir), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create(project_dir, backup_root, environment, expected_fingerprint):
    if environment not in TARGETS:
        raise ValueError(f"Unknown environment: {environment}")
    if fingerprint(project_dir) != expected_fingerprint:
        raise ValueError("dbt source changed during deployment")
    backup_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".release-", dir=backup_root))
    try:
        snapshot = staging / "dbt"
        snapshot.mkdir()
        for path in project_files(project_dir):
            dest = snapshot / path.relative_to(project_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        if fingerprint(snapshot) != expected_fingerprint:
            raise ValueError("dbt source changed while creating the release")
        manifest = {
            "format": 1,
            "environment": environment,
            "target": TARGETS[environment],
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "files": digests(snapshot),
        }
        (staging / "release.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = backup_root / f"{environment}_{name}_{staging.name.removeprefix('.release-')}"
        staging.rename(destination)
        print(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise


def verify(release_dir, environment):
    if environment not in TARGETS:
        raise ValueError(f"Unknown environment: {environment}")
    manifest_path = release_dir / "release.json"
    if manifest_path.is_symlink():
        raise ValueError("Release manifest cannot be a symlink")
    if not manifest_path.is_file():
        raise ValueError("Not a source release; legacy target-only backups cannot be rolled back")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise ValueError("Unsupported release format")
    if manifest.get("environment") != environment or manifest.get("target") != TARGETS[environment]:
        raise ValueError("Release environment or target does not match")
    actual = digests(release_dir / "dbt")
    if manifest.get("files") != actual:
        raise ValueError("Release files differ from their recorded checksums")
    all_files = {
        path.relative_to(release_dir / "dbt").as_posix()
        for path in (release_dir / "dbt").rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if all_files != set(actual):
        raise ValueError("Release contains unexpected files")
    print(f"Verified release: {release_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("project_dir", type=Path)
    create_parser.add_argument("backup_root", type=Path)
    create_parser.add_argument("environment", choices=TARGETS)
    create_parser.add_argument("--expected-fingerprint", required=True)
    fingerprint_parser = subparsers.add_parser("fingerprint")
    fingerprint_parser.add_argument("project_dir", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("release_dir", type=Path)
    verify_parser.add_argument("environment", choices=TARGETS)
    args = parser.parse_args()
    try:
        if args.command == "create":
            create(
                args.project_dir,
                args.backup_root,
                args.environment,
                args.expected_fingerprint,
            )
        elif args.command == "verify":
            verify(args.release_dir, args.environment)
        else:
            print(fingerprint(args.project_dir))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Release error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
