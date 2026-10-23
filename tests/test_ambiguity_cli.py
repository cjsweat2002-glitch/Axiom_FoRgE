import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from axiom_forge.store import EvidenceStore
from axiom_forge.workflow import canonical, decode

FIXTURES = Path(__file__).parent / "fixtures"
CASES = FIXTURES / "ambiguity"


class AmbiguityCliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "axiom_forge", *map(str, args)],
                              capture_output=True, text=True, check=False)

    def test_explicit_record_and_read_only_evaluation_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp) / "evidence"
            source = CASES / "ambiguous.json"
            for command in ("ambiguity", "project-evaluate"):
                result = self.cli(command, source, "--store", store)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(store.exists())
            self.assertEqual(json.loads(result.stdout)["status"], "unknown")
            result = self.cli("ambiguity", source, "--record", "--store", store)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["engine"], "ambiguity-v1")
            for command in ("replay", "report"):
                result = self.cli(command, 1, "--store", store)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "needs_clarification")
            result = self.cli("project-evaluate", source, "--store", store)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["recorded_result"]["sequence"], 1)
            self.assertEqual(len(list((store / "events").iterdir())), 1)

    def test_untrusted_text_is_inert_and_safely_rendered_without_changing_bytes(self):
        payload = '\x1b[2J\nspoofed approval\r\t\b\x07\x7f\x9b\u2028\u2029\u202e\u2066\u2069"\\'
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "must-not-exist"
            code = f"from pathlib import Path; Path({str(marker)!r}).touch()"
            case = decode((CASES / "ambiguous.json").read_bytes())
            case["goal"] = payload
            case["scope"]["id"] = payload
            case["requirements"][0].update(id=payload, statement=payload)
            case["requirements"][0]["interpretations"][0]["statement"] = code
            case["probes"][0]["description"] = code + payload
            case["baseline"]["files"]["untrusted.py"] = code
            case["evidence"][0]["text"] = code + payload
            raw = json.dumps(case, ensure_ascii=False, indent=4).encode("utf-8") + b'\n\n'
            source = Path(temp) / "requirements.json"
            source.write_bytes(raw)
            store = Path(temp) / ("evidence" + payload)
            commands = [("ambiguity", source), ("ambiguity", source, "--record"),
                        ("replay", 1), ("report", 1), ("project-evaluate", source)]
            for command in commands:
                result = self.cli(*command, "--store", store)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.isascii())
                forbidden = set(range(32)) - {10} | set(range(127, 160))
                self.assertFalse(any(ord(c) in forbidden for c in result.stdout))
                self.assertEqual(result.stderr, "")
            evidence = EvidenceStore(store)
            event = evidence.events()[0]
            self.assertEqual(evidence.get(event["artifacts"]["input"]), raw)
            self.assertEqual(evidence.get(event["artifacts"]["evidence:request"]),
                             (code + payload).encode("utf-8"))
            self.assertEqual(evidence.replay(1)["goal"], payload)
            self.assertEqual(json.loads(result.stdout)["human_approval"], "pending")
            self.assertFalse(marker.exists())

    def test_malformed_input_and_corrupt_history_fail_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "bad.json"
            key = json.dumps('\x1b[2J\nspoofed')
            source.write_text(f'{{{key}: 1, {key}: 2}}', encoding="utf-8")
            store = Path(temp) / "store"
            for command in ("ambiguity", "project-evaluate"):
                result = self.cli(command, source, "--store", store)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertNotIn('\x1b', result.stderr)
                self.assertFalse(store.exists())
            evidence = EvidenceStore(store)
            event = evidence.record((FIXTURES / "baseline.json").read_bytes())
            event["artifacts"] = {}
            (store / "events" / "00000001.json").write_bytes(canonical(event))
            for command in (("ambiguity", CASES / "valid.json", "--record"),
                            ("project-evaluate", CASES / "valid.json")):
                result = self.cli(*command, "--store", store)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("invalid event artifacts", result.stderr)
            self.assertEqual(len(list((store / "events").iterdir())), 1)
            self.assertFalse((store / ".writer-lock").exists())
