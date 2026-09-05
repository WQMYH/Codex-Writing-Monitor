import argparse
import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    arguments = parser.parse_args()
    if not arguments.health:
        parser.error("only --health is supported")
    print(json.dumps(health_report(version), sort_keys=True))


if __name__ == "__main__":
    main()
