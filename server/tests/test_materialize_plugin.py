from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from writing_ops.materialize import archive_locked_skills, materialize, seal_bundle, verify_bundle


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def test_materialize_builds_reviewable_bundle_without_development_state(tmp_path: Path) -> None:
    root = tmp_path / "writing-ops"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "secret").write_text("not distributable", encoding="utf-8")
    (root / ".test-tmp").mkdir()
    (root / ".test-tmp" / "transient").write_text("ignored", encoding="utf-8")
    (root / ".pytest-tmp").mkdir()
    (root / ".pytest-tmp" / "transient").write_text("ignored", encoding="utf-8")
    (root / "ui" / "node_modules").mkdir(parents=True)
    (root / "ui" / "node_modules" / "large.js").write_text("ignored", encoding="utf-8")
    (root / "README.md").write_text("first", encoding="utf-8")

    current = materialize(root)
    assert (current / "README.md").read_text(encoding="utf-8") == "first"
    assert not (current / ".git").exists()
    assert not (current / ".test-tmp").exists()
    assert not (current / ".pytest-tmp").exists()
    assert not (current / "ui" / "node_modules").exists()
    manifest = json.loads((current / "bundle-manifest.json").read_text(encoding="utf-8"))
    assert manifest["humanReviewStatus"] == "pending"
    assert any(item["path"] == "README.md" for item in manifest["files"])
    verify_bundle(current)

    (current / ".codex-plugin" / "plugin.json").write_text(
        '{"version":"0.1.0+codex.changed"}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="does not match"):
        verify_bundle(current)
    seal_bundle(current, source_root=root)
    verify_bundle(current)

    (root / "README.md").write_text("second", encoding="utf-8")
    replaced = materialize(root)
    assert replaced == current
    assert (replaced / "README.md").read_text(encoding="utf-8") == "second"
    verify_bundle(replaced)


def test_archive_locked_skills_uses_clean_git_snapshot_only(tmp_path: Path) -> None:
    source = tmp_path / "plotrail-source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "test@example.invalid")
    _git(source, "config", "user.name", "test")
    (source / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (source / "plotrail" / "references").mkdir(parents=True)
    (source / "plotrail" / "SKILL.md").write_text("plotrail\n", encoding="utf-8")
    (source / "plotrail" / "references" / "chapter-workflow.md").write_text(
        "workflow\n", encoding="utf-8"
    )
    (source / "plotrail-intake").mkdir()
    (source / "plotrail-intake" / "SKILL.md").write_text("intake\n", encoding="utf-8")
    (source / "examples").mkdir()
    (source / "examples" / "excluded.md").write_text("not a skill\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "skills")
    commit = _git(source, "rev-parse", "HEAD")

    snapshot = tmp_path / "snapshot"
    lock = archive_locked_skills(source, commit, snapshot)

    assert lock["commit"] == commit
    assert lock["human_review_status"] == "pending"
    assert (snapshot / "LICENSE").read_text(encoding="utf-8") == "MIT\n"
    assert (snapshot / "plotrail" / "SKILL.md").is_file()
    assert (snapshot / "plotrail-intake" / "SKILL.md").is_file()
    assert not (snapshot / "examples").exists()
    assert {item["path"] for item in lock["files"]} == {
        "LICENSE",
        "plotrail/SKILL.md",
        "plotrail/references/chapter-workflow.md",
        "plotrail-intake/SKILL.md",
    }

    (source / "README.md").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean"):
        archive_locked_skills(source, commit, tmp_path / "dirty-snapshot")


def test_materialize_includes_only_the_skill_lock_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "plotrail-source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "test@example.invalid")
    _git(source, "config", "user.name", "test")
    (source / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (source / "plotrail").mkdir()
    (source / "plotrail" / "SKILL.md").write_text("plotrail\n", encoding="utf-8")
    (source / "plotrail-intake").mkdir()
    (source / "plotrail-intake" / "SKILL.md").write_text("intake\n", encoding="utf-8")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "skills")
    commit = _git(source, "rev-parse", "HEAD")
    lock = archive_locked_skills(source, commit, tmp_path / "lock-source")

    root = tmp_path / "writing-ops"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (root / "skills").mkdir()
    (root / "skill-links").mkdir()
    (root / "skill-lock.json").write_text(json.dumps(lock), encoding="utf-8")

    current = materialize(root, skill_source=source)

    assert (current / "skills" / "plotrail" / "SKILL.md").is_file()
    assert (current / "skills" / "plotrail-intake" / "SKILL.md").is_file()
    assert not (current / "skill-links").exists()
    verify_bundle(current)
