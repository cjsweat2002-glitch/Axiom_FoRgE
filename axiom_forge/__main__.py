"""Command-line entry point. No command applies or executes candidate patches."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .store import EvidenceStore
from .workflow import canonical, decode, evaluate


def terminal_label(value: str) -> str:
    """Quote untrusted text as one ASCII line without altering stored evidence."""
    return json.dumps(value, ensure_ascii=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="axiom-forge", description="Axiom_FoRgE fixture workbench")
    parser.add_argument("--version", action="version", version=f"Axiom_FoRgE {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="review the goal, contract, policy, and proposed comparison")
    inspect.add_argument("case", type=Path)
    run = commands.add_parser("run", help="record a deterministic fixture comparison")
    run.add_argument("case", type=Path)
    run.add_argument("--store", type=Path, default=Path(".axiom-forge"))
    for name in ("replay", "report"):
        command = commands.add_parser(name, help=f"{name} a recorded event after verifying its evidence")
        command.add_argument("event", type=int)
        command.add_argument("--store", type=Path, default=Path(".axiom-forge"))
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            case = decode(args.case.read_bytes())
            report = evaluate(case)
            output = {"goal": case["goal"], "contract": case["contract"],
                      "policy": case["policy"], "comparison": report}
        elif args.command == "run":
            output = EvidenceStore(args.store).record(args.case.read_bytes())
        else:
            report = EvidenceStore(args.store).replay(args.event)
            if args.command == "report":
                print(f"Axiom_FoRgE — event {args.event}\n")
                print(f"Goal: {terminal_label(report['goal'])}\n")
                print("Fixture comparison only. Human approval: pending.\n")
                manifest = args.store / "events" / f"{args.event:08d}.json"
                print(f"Evidence manifest (exact input and artifact digests): "
                      f"{terminal_label(str(manifest))}\n")
                for candidate in report["candidates"]:
                    print(f"{terminal_label(candidate['id'])}: {candidate['status']} ({candidate['reason']}); "
                          f"plain baseline: {candidate['plain_baseline']}")
                    print(f"  Proposed next step: {candidate['diagnostic_proposal']}")
                    print(f"  Patch SHA-256: {candidate['patch_sha256']}")
                print(f"\nTotals: {report['totals']}")
                print(f"Plain baseline totals: {report['plain_baseline_totals']}")
                print(f"\nContext fingerprints: {report['context']}")
                for unknown in report["unknowns"]:
                    print(f"Unknown: {unknown}")
                return 0
            output = report
        print(canonical(output).decode("utf-8"), end="")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"axiom-forge: {terminal_label(str(error))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
