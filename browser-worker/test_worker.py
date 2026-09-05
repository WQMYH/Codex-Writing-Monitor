from __future__ import annotations

import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from worker import daemon_environment
from worker import harness_environment
from worker import health_report


class BrowserWorkerHealthTest(unittest.TestCase):
    def test_health_requires_the_pinned_browser_use_distribution(self) -> None:
        self.assertEqual(
            health_report(lambda _: "0.13.8"),
            {
                "state": "ready",
                "browser_use_version": "0.13.8",
                "autonomous_agent": False,
            },
        )
        self.assertEqual(
            health_report(lambda _: "0.13.7"),
            {
                "state": "blocked",
                "reason": "browser_use_version_mismatch",
                "browser_use_version": "0.13.7",
                "autonomous_agent": False,
            },
        )
        self.assertEqual(
            health_report(lambda _: (_ for _ in ()).throw(PackageNotFoundError)),
            {
                "state": "blocked",
                "reason": "browser_use_unavailable",
                "autonomous_agent": False,
            },
        )

    def test_harness_environment_isolated_to_the_owned_loopback_runtime(self) -> None:
        root = Path("C:/WritingOps")

        self.assertEqual(
            harness_environment("http://127.0.0.1:49152", root),
            {
                "BU_CDP_URL": "http://127.0.0.1:49152",
                "BU_NAME": "writing-ops",
                "BH_HOME": str(root / "browser-harness"),
                "BH_CONFIG_DIR": str(root / "browser-harness"),
                "BH_RUNTIME_DIR": str(root / "browser-harness" / "runtime"),
                "BH_TMP_DIR": str(root / "browser-harness" / "tmp"),
                "BH_AGENT_WORKSPACE": str(root / "browser-harness" / "workspace"),
                "BROWSER_USE_SETUP_LOGGING": "false",
            },
        )
        with self.assertRaises(ValueError):
            harness_environment("https://example.test:49152", root)

    def test_daemon_environment_requires_the_supervisor_values(self) -> None:
        self.assertEqual(
            daemon_environment(
                {
                    "WRITING_OPS_CDP_ORIGIN": "http://127.0.0.1:49152",
                    "WRITING_OPS_RUNTIME_ROOT": "C:/WritingOps",
                }
            )["BU_CDP_URL"],
            "http://127.0.0.1:49152",
        )
        with self.assertRaises(KeyError):
            daemon_environment({})
