from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
import time

import pytest

from writing_ops.adapters import windows_process_identity_matches


def test_runtime_configuration_allows_only_the_verified_storyforge_dev_entry(tmp_path) -> None:
    storyforge = tmp_path / "storyforge"
    storyforge.mkdir()
    (storyforge / "package.json").write_text(
        json.dumps(
            {
                "name": "storyforge",
                "scripts": {"dev": "node scripts/dev-with-writing-bridge.mjs"},
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "runtime.json"
    config.write_text(
        json.dumps(
            {
                "storyforgeRoot": str(storyforge),
                "storyforgeOrigin": "http://127.0.0.1:5173",
            }
        ),
        encoding="utf-8",
    )

    if importlib.util.find_spec("writing_ops.runtime") is None:
        pytest.fail("runtime configuration module is missing")
    runtime = importlib.import_module("writing_ops.runtime")
    load = getattr(runtime, "load_runtime_configuration", None)
    assert callable(load)
    settings = load(config)

    assert settings.storyforge_root == storyforge.resolve()
    assert settings.storyforge_origin == "http://127.0.0.1:5173"
    assert settings.storyforge_command == ("npm.cmd", "run", "dev")
    assert settings.configuration_fingerprint == hashlib.sha256(config.read_bytes()).hexdigest()

    (storyforge / "package.json").write_text(
        json.dumps({"name": "storyforge", "scripts": {"dev": "vite --host 0.0.0.0"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dev entry"):
        load(config)

    config.write_text(
        json.dumps(
            {
                "storyforgeRoot": str(storyforge),
                "storyforgeOrigin": "http://127.0.0.1:5173",
                "command": "powershell.exe -Command whoami",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="keys"):
        load(config)


def test_windows_job_terminates_its_managed_child() -> None:
    runtime = importlib.import_module("writing_ops.runtime")
    create_job = getattr(runtime, "create_windows_job", None)
    assert callable(create_job)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    job = None
    try:
        job = create_job()
        job.assign_pid(child.pid)
        job.close()
        assert child.wait(timeout=5) != 0
    finally:
        if job is not None:
            job.close()
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


def test_launch_storyforge_tracks_and_terminates_its_owned_process(tmp_path, monkeypatch) -> None:
    runtime = importlib.import_module("writing_ops.runtime")
    launch = getattr(runtime, "launch_storyforge", None)
    assert callable(launch)
    monkeypatch.setenv("WRITING_OPS_TEST_SECRET", "not-allowed")
    environment_evidence = tmp_path / "environment.txt"
    configuration = runtime.RuntimeConfiguration(
        storyforge_root=tmp_path,
        storyforge_origin="http://127.0.0.1:5173",
        configuration_fingerprint="test-fingerprint",
        storyforge_command=(
            sys.executable,
            "-c",
            "from pathlib import Path; import os, time; "
            f"Path({str(environment_evidence)!r}).write_text("
            "'leaked' if 'WRITING_OPS_TEST_SECRET' in os.environ else 'clean'); time.sleep(60)",
        ),
    )

    managed = launch(configuration, supervisor_nonce="test-run")
    try:
        for _ in range(50):
            if environment_evidence.exists():
                break
            time.sleep(0.1)
        assert environment_evidence.read_text(encoding="utf-8") == "clean"
        assert managed.configuration_fingerprint == "test-fingerprint"
        assert managed.identity.pid == managed.process.pid
        assert windows_process_identity_matches(managed.identity)
    finally:
        managed.close()

    assert managed.process.wait(timeout=5) != 0


def test_launch_browser_harness_owns_an_isolated_daemon_child(tmp_path, monkeypatch) -> None:
    runtime = importlib.import_module("writing_ops.runtime")
    launch = getattr(runtime, "launch_browser_harness", None)
    assert callable(launch)
    monkeypatch.setenv("WRITING_OPS_TEST_SECRET", "not-allowed")
    environment_evidence = tmp_path / "browser-harness-environment.json"
    worker_script = tmp_path / "fake_browser_harness.py"
    worker_script.write_text(
        "from pathlib import Path\n"
        "import json\n"
        "import os\n"
        "import time\n"
        "keys = ('WRITING_OPS_TEST_SECRET', 'WRITING_OPS_CDP_ORIGIN', "
        "'WRITING_OPS_RUNTIME_ROOT', 'WRITING_OPS_SUPERVISOR_NONCE')\n"
        "payload = {key: os.environ.get(key) for key in keys}\n"
        f"Path({str(environment_evidence)!r}).write_text(json.dumps(payload))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime,
        "_browser_worker_command",
        lambda _: (
            sys.executable,
            str(worker_script),
        ),
    )
    worker_root = tmp_path / "browser-worker"
    worker_root.mkdir()

    managed = launch(
        worker_root=worker_root,
        runtime_root=tmp_path / "WritingOps",
        cdp_origin="http://127.0.0.1:49152",
        supervisor_nonce="browser-run",
    )
    try:
        for _ in range(50):
            if environment_evidence.exists():
                break
            time.sleep(0.1)
        assert json.loads(environment_evidence.read_text(encoding="utf-8")) == {
            "WRITING_OPS_TEST_SECRET": None,
            "WRITING_OPS_CDP_ORIGIN": "http://127.0.0.1:49152",
            "WRITING_OPS_RUNTIME_ROOT": str((tmp_path / "WritingOps").resolve()),
            "WRITING_OPS_SUPERVISOR_NONCE": "browser-run",
        }
        assert windows_process_identity_matches(managed.identity)
    finally:
        managed.close()

    assert managed.process.wait(timeout=5) != 0
