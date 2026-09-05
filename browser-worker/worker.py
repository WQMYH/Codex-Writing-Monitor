import argparse
import json
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    arguments = parser.parse_args()
    if not arguments.health:
        parser.error("only --health is supported")
    print(json.dumps(health_report(version), sort_keys=True))


if __name__ == "__main__":
    main()
