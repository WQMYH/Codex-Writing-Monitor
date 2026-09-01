from __future__ import annotations

from pathlib import Path

from writing_ops.materialize import materialize


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(materialize(root))
