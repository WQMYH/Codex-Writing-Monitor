from __future__ import annotations

import json
from pathlib import Path

from writing_ops.materialize import materialize


def test_materialize_builds_reviewable_bundle_without_development_state(tmp_path: Path) -> None:
    root = tmp_path / "writing-ops"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "secret").write_text("not distributable", encoding="utf-8")
    (root / ".test-tmp").mkdir()
    (root / ".test-tmp" / "transient").write_text("ignored", encoding="utf-8")
    (root / "ui" / "node_modules").mkdir(parents=True)
    (root / "ui" / "node_modules" / "large.js").write_text("ignored", encoding="utf-8")
    (root / "README.md").write_text("first", encoding="utf-8")

    current = materialize(root)
    assert (current / "README.md").read_text(encoding="utf-8") == "first"
    assert not (current / ".git").exists()
    assert not (current / ".test-tmp").exists()
    assert not (current / "ui" / "node_modules").exists()
    manifest = json.loads((current / "bundle-manifest.json").read_text(encoding="utf-8"))
    assert manifest["humanReviewStatus"] == "pending"
    assert any(item["path"] == "README.md" for item in manifest["files"])

    (root / "README.md").write_text("second", encoding="utf-8")
    replaced = materialize(root)
    assert replaced == current
    assert (replaced / "README.md").read_text(encoding="utf-8") == "second"
