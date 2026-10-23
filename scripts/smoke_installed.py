"""Check the installed console entry point, retaining synthetic evidence and outputs."""

import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import axiom_forge


def main():
    fixtures = Path(sys.argv[1]).resolve()
    package = Path(axiom_forge.__file__).resolve()
    assert package.is_relative_to(Path(sys.prefix)), package
    print(f"Installed package: {package}")
    cli = Path(sys.executable).parent / "axiom-forge"

    def run(label, *args, expected_code=0):
        result = subprocess.run([str(cli), *map(str, args)], capture_output=True,
                                text=True, timeout=30, check=False)
        Path(f"{label}.stdout").write_text(result.stdout, encoding="utf-8")
        Path(f"{label}.stderr").write_text(result.stderr, encoding="utf-8")
        print(f"{label}: exit {result.returncode} (expected {expected_code})")
        assert result.returncode == expected_code, result.stderr
        if expected_code == 0:
            assert result.stderr == "", result.stderr
        return result.stdout

    version = run("version", "--version")
    assert version.strip() == f"Axiom_FoRgE {importlib.metadata.version('axiom-forge')}"
    run("help", "--help")
    inspected = json.loads(run("inspect", "inspect", fixtures / "baseline.json"))
    assert not Path(".axiom-forge").exists()
    event = json.loads(run("run", "run", fixtures / "baseline.json", "--store", "evidence"))
    assert event["sequence"] == 1
    raw = (fixtures / "baseline.json").read_bytes()
    assert (Path("evidence/objects") / event["artifacts"]["input"]).read_bytes() == raw
    replay = json.loads(run("replay", "replay", "1", "--store", "evidence"))
    assert replay == inspected["comparison"]
    expected = json.loads((fixtures / "expected.json").read_bytes())
    actual = {c["id"]: [c["status"], c["reason"], c["plain_baseline"]]
              for c in replay["candidates"]}
    assert actual == expected, actual
    assert replay["totals"] == {"accepted": 1, "refused": 1, "unknown": 3}
    assert replay["plain_baseline_totals"] == {"accepted": 3, "refused": 2, "unknown": 0}
    assert replay["human_approval"] == "pending"
    report = run("report", "report", "1", "--store", "evidence")
    assert "Human approval: pending" in report
    assert '"genuine_regression": refused' in report
    assert run("missing-input", "inspect", "missing.json", expected_code=2) == ""
    assert run("missing-event", "replay", "2", "--store", "evidence", expected_code=2) == ""
    print("Installed CLI smoke checks passed; fixture approval remains pending.")


if __name__ == "__main__":
    main()
