import argparse
import json
import os
import runpy
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit


EXPECTED_BROWSER_USE_VERSION = "0.13.8"


def health_report(version_reader):
    try:
        installed_version = version_reader("browser-use")
    except PackageNotFoundError:
        return {
            "state": "blocked",
            "reason": "browser_use_unavailable",
            "autonomous_agent": False,
        }
    if installed_version == EXPECTED_BROWSER_USE_VERSION:
        return {
            "state": "ready",
            "browser_use_version": installed_version,
            "autonomous_agent": False,
        }
    return {
        "state": "blocked",
        "reason": "browser_use_version_mismatch",
        "browser_use_version": installed_version,
        "autonomous_agent": False,
    }


def harness_environment(cdp_origin: str, runtime_root: Path) -> dict[str, str]:
    parsed = urlsplit(cdp_origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or not parsed.port
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("CDP origin must be a loopback HTTP origin")
    home = runtime_root / "browser-harness"
    return {
        "BU_CDP_URL": cdp_origin,
        "BU_NAME": "writing-ops",
        "BH_HOME": str(home),
        "BH_CONFIG_DIR": str(home),
        "BH_RUNTIME_DIR": str(home / "runtime"),
        "BH_TMP_DIR": str(home / "tmp"),
        "BH_AGENT_WORKSPACE": str(home / "workspace"),
        "BROWSER_USE_SETUP_LOGGING": "false",
    }


def daemon_environment(environment: Mapping[str, str]) -> dict[str, str]:
    return harness_environment(
        environment["WRITING_OPS_CDP_ORIGIN"],
        Path(environment["WRITING_OPS_RUNTIME_ROOT"]).resolve(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--health", action="store_true")
    operation.add_argument("--daemon", action="store_true")
    arguments = parser.parse_args()
    if arguments.health:
        print(json.dumps(health_report(version), sort_keys=True))
        return
    os.environ.update(daemon_environment(os.environ))
    runpy.run_module("browser_harness.daemon", run_name="__main__")


if __name__ == "__main__":
    main()
