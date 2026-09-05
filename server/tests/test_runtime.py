from __future__ import annotations

import pytest

import writing_ops.adapters as adapters


def test_edge_launch_spec_uses_an_isolated_profile_and_exact_storyforge_origin(tmp_path) -> None:
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"edge")

    spec = adapters.build_edge_launch_spec(
        edge_executable=edge,
        runtime_root=tmp_path / "WritingOps",
        storyforge_origin="http://127.0.0.1:5173",
    )

    assert spec.edge_executable == edge.resolve()
    assert spec.profile_dir == (tmp_path / "WritingOps" / "edge-profile").resolve()
    assert spec.profile_lock == (tmp_path / "WritingOps" / "edge-profile.lock").resolve()
    assert spec.storyforge_origin == "http://127.0.0.1:5173"
    assert spec.command == (
        str(edge.resolve()),
        f"--user-data-dir={spec.profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    )

    other_browser = tmp_path / "browser.exe"
    other_browser.write_bytes(b"browser")
    with pytest.raises(ValueError, match="msedge.exe"):
        adapters.build_edge_launch_spec(
            edge_executable=other_browser,
            runtime_root=tmp_path / "WritingOps",
            storyforge_origin="http://127.0.0.1:5173",
        )
    with pytest.raises(ValueError, match="origin"):
        adapters.build_edge_launch_spec(
            edge_executable=edge,
            runtime_root=tmp_path / "WritingOps",
            storyforge_origin="http://127.0.0.1:5173/not-allowed",
        )


def test_edge_profile_lock_is_atomic_and_preserves_an_unknown_owner(tmp_path) -> None:
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"edge")
    spec = adapters.build_edge_launch_spec(
        edge_executable=edge,
        runtime_root=tmp_path / "WritingOps",
        storyforge_origin="http://127.0.0.1:5173",
    )

    lock = adapters.acquire_edge_profile_lock(spec, owner_nonce="run-42")

    assert lock == spec.profile_lock
    assert lock.read_text(encoding="utf-8") == "run-42"
    with pytest.raises(FileExistsError, match="profile lock"):
        adapters.acquire_edge_profile_lock(spec, owner_nonce="run-43")
    assert lock.read_text(encoding="utf-8") == "run-42"
