from __future__ import annotations

import argparse
from pathlib import Path

from writing_ops.materialize import seal_bundle, verify_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("plugin_root", type=Path)
    args = parser.parse_args()
    manifest = seal_bundle(args.plugin_root)
    verify_bundle(args.plugin_root)
    print(manifest)


if __name__ == "__main__":
    main()
