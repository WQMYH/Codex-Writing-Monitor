from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import writing_ops.runtime as runtime
from writing_ops.service import WritingOpsService
from writing_ops.state import StateStore


def test_runtime_start_blocks_without_the_fixed_local_configuration(tmp_path: Path) -> None:
    service = WritingOpsService(store=StateStore(tmp_path / "state.sqlite3"))

    assert service.runtime_start() == {
        "state": "blocked",
        "reason": "runtime_configuration_missing",
        "human_review_status": "pending",
    }


def test_runtime_start_rejects_an_invalid_fixed_configuration_before_launching(
    tmp_path: Path,
) -> None:
    configuration_path = tmp_path / "runtime.json"
    configuration_path.write_text("{}", encoding="utf-8")
    service = WritingOpsService(
        store=StateStore(tmp_path / "state.sqlite3"), runtime_config_path=configuration_path
    )

    assert service.runtime_start() == {
        "state": "blocked",
        "reason": "runtime_configuration_invalid",
        "human_review_status": "pending",
    }


def test_runtime_start_remembers_a_preflight_failure_as_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"test executable")
    launch_attempts: list[object] = []
    monkeypatch.setattr(
        runtime,
        "load_runtime_configuration",
        lambda _: SimpleNamespace(storyforge_origin="http://127.0.0.1:5173"),
    )
    monkeypatch.setattr("writing_ops.adapters.build_edge_launch_spec", lambda **_: object())

    def fail_launch(**_):
        launch_attempts.append(object())
        raise subprocess.TimeoutExpired("worker.py --health", 10)

    monkeypatch.setattr(runtime, "launch_runtime_session", fail_launch)
    service = WritingOpsService(
        store=StateStore(tmp_path / "state.sqlite3"),
        runtime_config_path=tmp_path / "runtime.json",
        edge_executable=edge,
    )
    (tmp_path / "runtime.json").write_text("{}", encoding="utf-8")

    expected = {
        "adapter": "runtime-supervisor",
        "state": "blocked",
        "reason": "runtime_start_failed",
        "human_review_status": "pending",
    }
    assert service.runtime_start() == expected
    assert service.runtime_status() == expected
    assert service.runtime_start() == expected
    assert len(launch_attempts) == 1
    assert service.runtime_stop()["state"] == "stopped"
    assert service.runtime_start() == expected
    assert len(launch_attempts) == 2


def test_runtime_start_uses_only_the_fixed_configuration_and_reports_owned_processes(
    tmp_path: Path, monkeypatch
) -> None:
    storyforge_root = tmp_path / "storyforge"
    storyforge_root.mkdir()
    (storyforge_root / "package.json").write_text(
        json.dumps(
            {
                "name": "storyforge",
                "scripts": {"dev": "node scripts/dev-with-writing-bridge.mjs"},
            }
        ),
        encoding="utf-8",
    )
    configuration_path = tmp_path / "runtime.json"
    configuration_path.write_text(
        json.dumps(
            {
                "storyforgeRoot": str(storyforge_root),
                "storyforgeOrigin": "http://127.0.0.1:5173",
            }
        ),
        encoding="utf-8",
    )
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"test executable")
    session = SimpleNamespace(
        loopback=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: True)),
        storyforge=SimpleNamespace(
            identity=SimpleNamespace(pid=101), configuration_fingerprint="configured-hash"
        ),
        edge=SimpleNamespace(identity=SimpleNamespace(pid=202)),
        browser_harness=SimpleNamespace(
            identity=SimpleNamespace(pid=303), browser_use_version="0.13.8"
        ),
        reconciliation=lambda: {
            "loopback": "running",
            "storyforge": "running",
            "edge": "running",
            "browser_worker": "running",
        },
    )
    launched: dict[str, object] = {}

    def launch(**kwargs):
        launched.update(kwargs)
        return session

    monkeypatch.setattr(runtime, "launch_runtime_session", launch)
    service = WritingOpsService(
        store=StateStore(tmp_path / "state.sqlite3"),
        runtime_config_path=configuration_path,
        edge_executable=edge,
    )

    assert service.runtime_start() == {
        "adapter": "runtime-supervisor",
        "state": "running",
        "loopback": "running",
        "storyforge": {"pid": 101, "configuration_fingerprint": "configured-hash"},
        "edge": {"pid": 202, "profile": "owned"},
        "browser_worker": {
            "pid": 303,
            "state": "running",
            "browser_use_version": "0.13.8",
            "autonomous_agent": False,
        },
        "reconciliation": {
            "loopback": "running",
            "storyforge": "running",
            "edge": "running",
            "browser_worker": "running",
        },
        "human_review_status": "pending",
    }
    assert launched["configuration"].storyforge_root == storyforge_root.resolve()
    assert launched["configuration"].storyforge_origin == "http://127.0.0.1:5173"
    assert launched["edge_spec"].command[2:4] == (
        "--no-first-run",
        "--no-default-browser-check",
    )


def test_runtime_status_blocks_when_an_owned_component_no_longer_matches() -> None:
    service = WritingOpsService()
    service._runtime_session = SimpleNamespace(
        loopback=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: True)),
        storyforge=SimpleNamespace(
            identity=SimpleNamespace(pid=101), configuration_fingerprint="configured-hash"
        ),
        edge=SimpleNamespace(identity=SimpleNamespace(pid=202)),
        browser_harness=SimpleNamespace(
            identity=SimpleNamespace(pid=303), browser_use_version="0.13.8"
        ),
        reconciliation=lambda: {
            "loopback": "running",
            "storyforge": "running",
            "edge": "stopped",
            "browser_worker": "running",
        },
    )

    assert service.runtime_status()["state"] == "blocked"
    assert service.runtime_status()["reason"] == "runtime_component_stopped"


def test_runtime_stop_closes_the_owned_session_and_clears_its_runtime_status(
    tmp_path: Path,
) -> None:
    closed: list[bool] = []
    service = WritingOpsService(store=StateStore(tmp_path / "state.sqlite3"))
    service._runtime_session = SimpleNamespace(close=lambda: closed.append(True))

    assert service.runtime_stop() == {
        "adapter": "runtime-supervisor",
        "state": "stopped",
        "human_review_status": "pending",
    }
    assert closed == [True]
