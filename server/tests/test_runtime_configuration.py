from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys

import pytest


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
