import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from axiom_forge.store import EvidenceStore

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
            self.assertIn('"genuine_regression": refused', report.stdout)

    def test_errors_are_nonzero_and_do_not_claim_success(self):
        with tempfile.TemporaryDirectory() as temp:
            for args in (("inspect", Path(temp) / "missing.json"),
                         ("replay", "1", "--store", temp)):
                with self.subTest(args=args):
                    result = self.cli(*args)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("axiom-forge:", result.stderr)

    def assert_no_terminal_controls(self, output):
        forbidden = set(range(32)) - {10} | set(range(127, 160))
        forbidden.update((0x2028, 0x2029, 0x202E, 0x2066, 0x2069))
        self.assertFalse(any(ord(char) in forbidden for char in output), repr(output))

    def test_untrusted_labels_are_escaped_but_evidence_is_preserved(self):
        payload = ('\x1b[2J\x1b[HINJECTED HUMAN APPROVAL: approved\nspoofed'
                   '\r\t\b\x07\x7f\x9b2J\u2028\u2029\u202e\u2066\u2069"\\')
        case = json.loads(FIXTURE.read_bytes())
        case["goal"] = payload
        case["candidates"][0]["id"] = payload
        raw = json.dumps(case, ensure_ascii=False, indent=4).encode("utf-8") + b"\n\n"
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "case.json"
            source.write_bytes(raw)
            store = Path(temp) / "evidence\x1b[2J\nspoofed"
            inspected = self.cli("inspect", source)
            run = self.cli("run", source, "--store", store)
            replay = self.cli("replay", 1, "--store", store)
            rendered = self.cli("report", 1, "--store", store)
            for result in (inspected, run, replay, rendered):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_no_terminal_controls(result.stdout)
                self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(inspected.stdout)["goal"], payload)
            report = json.loads(replay.stdout)
            self.assertEqual(report["goal"], payload)
            self.assertEqual(report["candidates"][0]["id"], payload)
            self.assertEqual(report["human_approval"], "pending")
            manifest = json.loads(run.stdout)
            evidence = EvidenceStore(store)
            self.assertEqual(evidence.get(manifest["artifacts"]["input"]), raw)
            stored_report = json.loads(evidence.get(manifest["artifacts"]["report"]))
            self.assertEqual(stored_report, report)
            escaped = json.dumps(payload, ensure_ascii=True)
            self.assertIn(f"Goal: {escaped}\n", rendered.stdout)
            self.assertIn(f"{escaped}: accepted", rendered.stdout)
            self.assertIn(json.dumps(str(store / "events" / "00000001.json")), rendered.stdout)
            self.assertIn("Fixture comparison only. Human approval: pending.\n", rendered.stdout)
            self.assertFalse(any(line.startswith("spoofed") for line in rendered.stdout.splitlines()))

    def test_untrusted_error_details_are_escaped(self):
        key = json.dumps("\x1b[2J\nspoofed")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "bad.json"
            source.write_text(f"{{{key}: 1, {key}: 2}}", encoding="utf-8")
            result = self.cli("inspect", source)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assert_no_terminal_controls(result.stderr)
            self.assertEqual(len(result.stderr.splitlines()), 1)
            self.assertIn("duplicate JSON key", result.stderr)
