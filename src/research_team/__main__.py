"""Run a CrewAI brief over a local source pack."""

import argparse
import json
from pathlib import Path

from .schema import SourcePack
from .team import run_team


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled-source CrewAI research brief")
    parser.add_argument("pack", type=Path, help="source pack JSON")
    parser.add_argument("--output", type=Path, help="save the evaluated brief JSON")
    args = parser.parse_args()
    pack = SourcePack.model_validate_json(args.pack.read_text())
    report = run_team(pack)
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n")
    print(serialized)


if __name__ == "__main__":
    main()
