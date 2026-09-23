"""PM-facing overlay status. Does not mutate baseline v2.0.0."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from warehouse_control.overlay.register import summary  # noqa: E402


def main() -> None:
    print(json.dumps(summary(), indent=2))


if __name__ == "__main__":
    main()
