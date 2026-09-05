from __future__ import annotations

import unittest
from importlib.metadata import PackageNotFoundError

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
