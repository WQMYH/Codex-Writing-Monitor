from __future__ import annotations

import json
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
        "human_review_status": "pending",
    }
    assert launched["configuration"].storyforge_root == storyforge_root.resolve()
    assert launched["configuration"].storyforge_origin == "http://127.0.0.1:5173"
    assert launched["edge_spec"].command[2:4] == (
        "--no-first-run",
        "--no-default-browser-check",
    )


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
