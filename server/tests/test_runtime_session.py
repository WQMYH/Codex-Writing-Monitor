from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import writing_ops.adapters as adapters
import writing_ops.runtime as runtime
from writing_ops.materialize import seal_bundle
from writing_ops.service import WritingOpsService
from writing_ops.state import StateStore


def sealed_plugin(tmp_path: Path) -> Path:
    root = tmp_path / "writing-ops"
    component = root / "ui" / "dist" / "component.js"
    component.parent.mkdir(parents=True)
    component.write_text("export {}", encoding="utf-8")
    manifest = root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"writing-ops","version":"0.1.0+codex.test"}', encoding="utf-8")
    (root / "browser-worker").mkdir()
    seal_bundle(root)
    return root


def test_runtime_session_owns_loopback_storyforge_edge_and_harness_until_close(
    tmp_path, monkeypatch
) -> None:
    root = sealed_plugin(tmp_path)
    service = WritingOpsService(plugin_root=root, store=StateStore(tmp_path / "state.sqlite3"))
    configuration = runtime.RuntimeConfiguration(
        storyforge_root=tmp_path,
        storyforge_origin="http://127.0.0.1:5173",
        configuration_fingerprint="test-fingerprint",
        storyforge_command=(sys.executable, "-c", "import time; time.sleep(60)"),
    )
    edge_path = tmp_path / "msedge.exe"
    edge_path.write_bytes(b"edge")
    handoff_evidence = tmp_path / "handoff.txt"
    edge_profile_dir = tmp_path / "WritingOps" / "edge-profile"
    harness_script = tmp_path / "fake_browser_harness.py"
    harness_script.write_text(
        "import json\n"
        "import sys\n"
        "import time\n"
        "if sys.argv[-1] == '--health':\n"
        "    print(json.dumps({'state': 'ready', 'browser_use_version': '0.13.8', "
        "'autonomous_agent': False}))\n"
        "    raise SystemExit()\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runtime,
        "_browser_worker_command",
        lambda _: (sys.executable, str(harness_script), "--daemon"),
    )
    edge = replace(
        adapters.build_edge_launch_spec(
            edge_executable=edge_path,
            runtime_root=tmp_path / "WritingOps",
            storyforge_origin=configuration.storyforge_origin,
        ),
        command=(
            sys.executable,
            "-c",
            "from pathlib import Path; import sys, time; "
            f"Path({str(handoff_evidence)!r}).write_text(sys.argv[-1]); "
            f"Path({str(edge_profile_dir / 'DevToolsActivePort')!r}).write_text('49153\\n'); "
            "time.sleep(60)",
        ),
    )
    launch = getattr(runtime, "launch_runtime_session", None)
    assert callable(launch)

    session = launch(
        service=service,
        plugin_root=root,
        configuration=configuration,
        edge_spec=edge,
        supervisor_nonce="session-run",
    )
    try:
        for _ in range(50):
            if handoff_evidence.exists():
                break
            time.sleep(0.1)
        handoff = urlsplit(handoff_evidence.read_text(encoding="utf-8"))
        assert session.loopback.thread.is_alive()
        assert handoff.scheme == "http" and handoff.netloc == "127.0.0.1:5173"
        assert handoff.path == "/writing-ops" and not handoff.query and handoff.fragment
        assert adapters.windows_process_identity_matches(session.storyforge.identity)
        assert adapters.windows_process_identity_matches(session.edge.identity)
        assert session.edge.cdp_origin == "http://127.0.0.1:49153"
        assert adapters.windows_process_identity_matches(session.browser_harness.identity)
        assert session.reconciliation() == {
            "loopback": "running",
            "storyforge": "running",
            "edge": "running",
            "browser_worker": "running",
        }
    finally:
        session.close()

    assert session.storyforge.process.wait(timeout=5) != 0
    assert session.edge.process.wait(timeout=5) != 0
    assert session.browser_harness.process.wait(timeout=5) != 0
    assert not session.loopback.thread.is_alive()
    assert not edge.profile_lock.exists()
