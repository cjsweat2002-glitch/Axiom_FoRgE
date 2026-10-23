import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

FIXTURE = Path(__file__).parent / "fixtures" / "baseline.json"


class CliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "axiom_forge", *map(str, args)],
                              capture_output=True, text=True, check=False)

    def test_inspect_record_replay_and_export(self):
        inspected = self.cli("inspect", FIXTURE)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIn("contract", json.loads(inspected.stdout))
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / "evidence"
            run = self.cli("run", FIXTURE, "--store", store)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["sequence"], 1)
            replay = self.cli("replay", 1, "--store", store)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertEqual(json.loads(replay.stdout)["totals"]["unknown"], 3)
            report = self.cli("report", 1, "--store", store)
            self.assertEqual(report.returncode, 0, report.stderr)
            self.assertIn("Human approval: pending", report.stdout)
            self.assertIn("genuine_regression: refused", report.stdout)

    def test_errors_are_nonzero_and_do_not_claim_success(self):
        with tempfile.TemporaryDirectory() as temp:
            for args in (("inspect", Path(temp) / "missing.json"),
                         ("replay", "1", "--store", temp)):
                with self.subTest(args=args):
                    result = self.cli(*args)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("axiom-forge:", result.stderr)
