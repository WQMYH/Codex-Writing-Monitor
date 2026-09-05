from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
import uuid
from io import BytesIO
from pathlib import Path

EXCLUDED_TOP_LEVEL = {".dist", ".git", ".skillflow", "skill-links"}
EXCLUDED_NAMES = {
    ".pytest_cache",
    ".pytest-tmp",
    ".test-tmp",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
BUNDLE_MANIFEST = "bundle-manifest.json"
SKILL_ARCHIVE_PATHS = ("LICENSE", "plotrail", "plotrail-intake")


def _ignored(path: str, names: list[str]) -> set[str]:
    current = Path(path)
    excluded = {name for name in names if name in EXCLUDED_NAMES}
    if current.name == "writing-ops":
        excluded.update(name for name in names if name in EXCLUDED_TOP_LEVEL)
    return excluded


def _file_manifest(root: Path) -> list[dict[str, str | int]]:
    entries: list[dict[str, str | int]] = []
    files = (
        item
        for item in root.rglob("*")
        if item.is_file()
        and item.name != BUNDLE_MANIFEST
        and not any(part in EXCLUDED_NAMES for part in item.relative_to(root).parts)
    )
    for path in sorted(files):
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative, "sha256": digest, "size": path.stat().st_size})
    return entries


def seal_bundle(bundle_root: Path, source_root: Path | None = None) -> Path:
    bundle_root = bundle_root.resolve(strict=True)
    manifest_path = bundle_root / BUNDLE_MANIFEST
    manifest = {
        "schemaVersion": 1,
        "humanReviewStatus": "pending",
        "sourceRoot": str((source_root or bundle_root).resolve()),
        "files": _file_manifest(bundle_root),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def verify_bundle(bundle_root: Path) -> dict[str, object]:
    bundle_root = bundle_root.resolve(strict=True)
    manifest = json.loads((bundle_root / BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("files") != _file_manifest(bundle_root):
        raise ValueError("bundle manifest does not match the installed artifact")
    if manifest.get("humanReviewStatus") != "pending":
        raise ValueError("bundle human review status must remain pending")
    return manifest


def archive_locked_skills(
    source_repo: Path, commit: str, destination: Path
) -> dict[str, object]:
    """Archive the approved PlotRail skill closure from a clean Git source."""
    source_repo = source_repo.resolve(strict=True)
    status = subprocess.run(
        ["git", "-C", str(source_repo), "status", "--porcelain"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    if status.stdout:
        raise ValueError("PlotRail source repository must be clean")
    archive = subprocess.run(
        [
            "git",
            "-C",
            str(source_repo),
            "archive",
            "--format=tar",
            commit,
            *SKILL_ARCHIVE_PATHS,
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=BytesIO(archive.stdout)) as bundle:
        bundle.extractall(destination, filter="data")
    files = [
        {
            "path": path.relative_to(destination).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mode": path.stat().st_mode & 0o777,
        }
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    ]
    return {
        "schema_version": 1,
        "commit": commit,
        "human_review_status": "pending",
        "files": files,
    }


def _skill_source_from_links(plugin_root: Path) -> Path:
    targets = [
        (plugin_root / "skill-links" / name).resolve(strict=True)
        for name in ("plotrail", "plotrail-intake")
    ]
    if targets[0].parent != targets[1].parent:
        raise ValueError("PlotRail skill links must share one source repository")
    return targets[0].parent


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def materialize(plugin_root: Path, skill_source: Path | None = None) -> Path:
    plugin_root = plugin_root.resolve(strict=True)
    if plugin_root.name != "writing-ops":
        raise ValueError(f"unexpected plugin root: {plugin_root}")

    dist_root = plugin_root / ".dist"
    dist_root.mkdir(exist_ok=True)
    staging = dist_root / f"staging-{uuid.uuid4().hex}"
    current = dist_root / "current"
    previous = dist_root / "previous"

    shutil.copytree(plugin_root, staging, ignore=_ignored)
    lock_path = plugin_root / "skill-lock.json"
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        snapshot_root = staging / "skills"
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root)
        snapshot = archive_locked_skills(
            skill_source or _skill_source_from_links(plugin_root),
            str(lock["commit"]),
            snapshot_root,
        )
        if snapshot != lock:
            raise ValueError("PlotRail skill archive does not match skill-lock.json")
    seal_bundle(staging, source_root=plugin_root)

    if previous.exists():
        shutil.rmtree(previous)
    if current.exists():
        _replace_with_retry(current, previous)
    try:
        _replace_with_retry(staging, current)
    except PermissionError:
        if previous.exists() and not current.exists():
            _replace_with_retry(previous, current)
        raise
    if previous.exists():
        shutil.rmtree(previous)
    return current
