from __future__ import annotations

import os
import sys
import time
from dataclasses import replace

import pytest

import writing_ops.adapters as adapters
import writing_ops.runtime as runtime


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
    handoff = (
        "http://127.0.0.1:5173/writing-ops"
        "#endpoint=http%3A%2F%2F127.0.0.1%3A43210%2Fapi%2Fwriting-ops%2Fdashboard"
        "&session=session-value&csrf=csrf-value&mount=writing-ops-root"
    )
    assert spec.command_with_handoff(handoff) == spec.command + (handoff,)
    with pytest.raises(ValueError, match="handoff"):
        spec.command_with_handoff("https://example.test/writing-ops#not-allowed")
    with pytest.raises(ValueError, match="handoff"):
        spec.command_with_handoff("http://127.0.0.1:5173/writing-ops?session=not-allowed")

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


def test_edge_profile_lock_only_releases_for_its_owner_nonce(tmp_path) -> None:
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"edge")
    spec = adapters.build_edge_launch_spec(
        edge_executable=edge,
        runtime_root=tmp_path / "WritingOps",
        storyforge_origin="http://127.0.0.1:5173",
    )
    adapters.acquire_edge_profile_lock(spec, owner_nonce="run-42")

    assert not adapters.release_edge_profile_lock(spec, owner_nonce="run-43")
    assert spec.profile_lock.exists()
    assert adapters.release_edge_profile_lock(spec, owner_nonce="run-42")
    assert not spec.profile_lock.exists()


def test_windows_process_identity_binds_pid_to_its_creation_time() -> None:
    identity = adapters.get_windows_process_identity(os.getpid())

    assert identity.pid == os.getpid()
    assert identity.created_at_100ns > 0
    assert adapters.windows_process_identity_matches(identity)
    assert not adapters.windows_process_identity_matches(
        adapters.WindowsProcessIdentity(identity.pid, identity.created_at_100ns + 1)
    )


def test_launch_edge_owns_its_profile_and_managed_process(tmp_path, monkeypatch) -> None:
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"edge")
    spec = adapters.build_edge_launch_spec(
        edge_executable=edge,
        runtime_root=tmp_path / "WritingOps",
        storyforge_origin="http://127.0.0.1:5173",
    )
    monkeypatch.setenv("WRITING_OPS_TEST_SECRET", "not-allowed")
    environment_evidence = tmp_path / "edge-environment.txt"
    spec = replace(
        spec,
        command=(
            sys.executable,
            "-c",
            "from pathlib import Path; import os, time; "
            f"Path({str(environment_evidence)!r}).write_text("
            "'leaked' if 'WRITING_OPS_TEST_SECRET' in os.environ else 'clean'); time.sleep(60)",
        ),
    )
    handoff = "http://127.0.0.1:5173/writing-ops#session=test"
    launch = getattr(runtime, "launch_edge", None)
    assert callable(launch)

    managed = launch(spec, handoff_url=handoff, supervisor_nonce="edge-run")
    try:
        for _ in range(50):
            if environment_evidence.exists():
                break
            time.sleep(0.1)
        assert environment_evidence.read_text(encoding="utf-8") == "clean"
        assert spec.profile_lock.read_text(encoding="utf-8") == "edge-run"
        assert adapters.windows_process_identity_matches(managed.identity)
    finally:
        managed.close()

    assert managed.process.wait(timeout=5) != 0
    assert not spec.profile_lock.exists()
