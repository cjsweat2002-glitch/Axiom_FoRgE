import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from axiom_forge import ambiguity
from axiom_forge.project import evaluate_project
from axiom_forge.store import EvidenceStore
from axiom_forge.workflow import canonical, decode, fingerprint

FIXTURES = Path(__file__).parent / "fixtures"
CASES = FIXTURES / "ambiguity"


class AmbiguityTests(unittest.TestCase):
    def test_curated_outcomes_determinism_and_pending_authority(self):
        for name, expected in decode((CASES / "expected.json").read_bytes()).items():
            with self.subTest(name=name):
                raw = (CASES / f"{name}.json").read_bytes()
                report = ambiguity.analyze(raw)
                self.assertEqual(report, ambiguity.analyze(raw))
                self.assertEqual(report["input_sha256"], fingerprint(raw))
                self.assertEqual(report["status"], expected["status"])
                self.assertEqual(report["totals"], expected["totals"])
                self.assertEqual([f["kind"] for f in report["findings"]], expected["kinds"])
                self.assertEqual(report["semantic_status"], "unknown")
                self.assertEqual(report["human_approval"], "pending")
                case = decode(raw)
                for finding in report["findings"]:
                    self.assertEqual(finding["approval"], "pending")
                    self.assertTrue(finding["uncertainty"])
                    self.assertTrue(finding["proposed_clarification"])
                    for pointer in finding["sources"]:
                        source = case
                        for part in pointer.strip("/").split("/"):
                            source = source[int(part)] if isinstance(source, list) else source[part]
                    self.assertLessEqual(set(finding["evidence_refs"]), set(report["evidence"]))

    def test_smallest_pairwise_proposals_and_unknown_discriminators(self):
        case = decode((CASES / "ambiguous.json").read_bytes())
        report = ambiguity.analyze(canonical(case))
        proposals = report["findings"][0]["proposed_checks"]
        self.assertEqual(len(proposals), 3)
        self.assertEqual([p["probe"] for p in proposals], ["digit-pair"] * 3)
        self.assertEqual(proposals[0]["expected_outcomes"], {"arithmetic": "5", "concatenation": "23"})
        case["requirements"][0]["interpretations"][2]["expectations"] = {}
        report = ambiguity.analyze(canonical(case))
        proposals = report["findings"][0]["proposed_checks"]
        self.assertEqual([p["status"] for p in proposals], ["proposed", "unknown", "unknown"])
        self.assertIsNone(proposals[1]["probe"])
        self.assertEqual(proposals[1]["expected_outcomes"], {})

    def test_only_explicit_structure_is_compared(self):
        case = decode((CASES / "valid.json").read_bytes())
        case["requirements"][0]["statement"] = "Maybe always never do the right thing."
        case["assumptions"].append({**case["assumptions"][0], "id": "duplicate-value"})
        self.assertEqual(ambiguity.analyze(canonical(case))["findings"], [])
        case["assumptions"][1].update(key="other-scope", value="string")
        self.assertEqual(ambiguity.analyze(canonical(case))["findings"], [])
        case["requirements"][0]["checks"] = []
        case["contract"]["checks"] = []
        case["acceptance_evidence"] = {}
        self.assertEqual(ambiguity.analyze(canonical(case))["findings"][0]["kind"], "missing_acceptance_checks")

    def test_strict_schema_rejects_malformed_inputs_and_authority_expansion(self):
        original = decode((CASES / "valid.json").read_bytes())
        mutations = [
            lambda c: c.update(version=True),
            lambda c: c.update(version=2),
            lambda c: c.update(approved=True),
            lambda c: c["policy"].update(human_approval_required=False),
            lambda c: c.update(requirements=[]),
            lambda c: c.update(requirements=[c["requirements"][0]] * 65),
            lambda c: c["requirements"].append(c["requirements"][0]),
            lambda c: c["requirements"][0].update(checks=["undeclared"]),
            lambda c: c["requirements"][0].update(evidence_refs=["missing"]),
            lambda c: c["requirements"][0].update(evidence_refs=["request", "request"]),
            lambda c: c["requirements"][0]["interpretations"][0].update(expectations={"unknown-probe": "pass"}),
            lambda c: c["requirements"][0]["interpretations"][0].update(expectations=[]),
            lambda c: c["assumptions"][0].update(value=False),
            lambda c: c["evidence"][0].update(text=""),
            lambda c: c.update(acceptance_evidence={"undeclared": []}),
            lambda c: c["scope"].update(kind="unbounded"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                case = copy.deepcopy(original)
                mutate(case)
                with self.assertRaises(ValueError):
                    ambiguity.analyze(canonical(case))
        for raw in (b'{"version":1,"version":1}', b'{"x": NaN}', b'[]', b' ' * (ambiguity.MAX_INPUT_BYTES + 1)):
            with self.assertRaises(ValueError):
                ambiguity.analyze(raw)


class RecordedAmbiguityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = EvidenceStore(Path(temp.name) / "store")
        self.raw = (CASES / "ambiguous.json").read_bytes()

    def snapshot(self):
        return {p.relative_to(self.store.root): p.read_bytes()
                for p in self.store.root.rglob("*") if p.is_file()}

    def test_mixed_history_preserves_raw_bytes_and_context(self):
        fixture = self.store.record((FIXTURES / "baseline.json").read_bytes())
        original = (self.store.root / "events" / "00000001.json").read_bytes()
        raw = b'\n ' + self.raw + b'\n\n'
        event = self.store.record(raw, engine=ambiguity.ENGINE)
        self.assertEqual(self.store.get(event["artifacts"]["input"]), raw)
        for evidence in decode(raw)["evidence"]:
            self.assertEqual(self.store.get(event["artifacts"][f"evidence:{evidence['id']}"]),
                             evidence["text"].encode("utf-8"))
        self.assertEqual(self.store.replay(2), ambiguity.analyze(raw))
        self.assertEqual((self.store.root / "events" / "00000001.json").read_bytes(), original)
        self.assertEqual(event["previous"], fingerprint(original))
        self.assertEqual(self.store.replay(fixture["sequence"])["totals"],
                         {"accepted": 1, "refused": 1, "unknown": 3})

    def test_evaluation_is_read_only_and_requires_exact_recorded_input(self):
        # No history means the evaluator must not invoke the tester at all.
        with patch.object(ambiguity, "analyze", side_effect=AssertionError("unexpected test run")):
            result = evaluate_project(self.raw, self.store)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["totals"])
        self.assertIsNone(result["recorded_result"])
        self.assertFalse(self.store.root.exists())
        self.store.record((FIXTURES / "baseline.json").read_bytes())
        first = self.store.record(self.raw, engine=ambiguity.ENGINE)
        before = self.snapshot()
        result = evaluate_project(self.raw, self.store)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(result["recorded_result"]["sequence"], first["sequence"])
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["tester_execution"], "not_requested")
        comparison = result["recorded_fixture_comparisons"][0]
        self.assertEqual(comparison["totals"], {"accepted": 1, "refused": 1, "unknown": 3})
        self.assertEqual(comparison["plain_baseline_totals"], {"accepted": 3, "refused": 2, "unknown": 0})
        self.assertEqual(evaluate_project(self.raw + b'\n', self.store)["status"], "unknown")
        for name in ("baseline", "contract", "policy"):
            changed = decode(self.raw)
            changed[name]["version"] += "-changed"
            result = evaluate_project(canonical(changed), self.store)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(len(result["other_inputs_same_scope"]), 1)
            self.assertEqual(result["recorded_fixture_comparisons"], [])
        self.assertEqual(self.snapshot(), before)

    def test_new_cycle_does_not_erase_previous_findings_or_grant_approval(self):
        first = self.store.record(self.raw, engine=ambiguity.ENGINE)
        valid = (CASES / "valid.json").read_bytes()
        second = self.store.record(valid, engine=ambiguity.ENGINE)
        self.store.record(valid, engine=ambiguity.ENGINE)
        result = evaluate_project(valid, self.store)
        self.assertEqual(result["recorded_result"]["sequence"], second["sequence"] + 1)
        self.assertEqual(result["status"], "no_structural_findings")
        self.assertEqual(result["human_approval"], "pending")
        self.assertEqual(self.store.replay(first["sequence"])["status"], "needs_clarification")
        self.assertEqual(evaluate_project(self.raw, self.store)["recorded_result"]["sequence"], 1)

    def test_forged_history_blocks_append_replay_and_evaluation_without_repair(self):
        first = self.store.record(self.raw, engine=ambiguity.ENGINE)
        second = self.store.record((FIXTURES / "baseline.json").read_bytes())
        report = self.store.replay(1)
        report["human_approval"] = "approved"
        first["artifacts"]["report"] = self.store.put(canonical(report))
        altered = canonical(first)
        (self.store.root / "events" / "00000001.json").write_bytes(altered)
        second["previous"] = fingerprint(altered)
        (self.store.root / "events" / "00000002.json").write_bytes(canonical(second))
        before = self.snapshot()
        for action in (lambda: self.store.replay(2),
                       lambda: self.store.record(self.raw, engine=ambiguity.ENGINE),
                       lambda: self.store.record((FIXTURES / "baseline.json").read_bytes()),
                       lambda: evaluate_project(self.raw, self.store)):
            with self.assertRaisesRegex(ValueError, "replay result mismatch"):
                action()
            self.assertEqual(self.snapshot(), before)
            self.assertFalse((self.store.root / ".writer-lock").exists())

    def test_evidence_binding_and_hash_corruption_are_detected(self):
        event = self.store.record(self.raw, engine=ambiguity.ENGINE)
        original = copy.deepcopy(event)
        path = self.store.root / "events" / "00000001.json"
        event["artifacts"]["evidence:request"] = event["artifacts"]["evidence:observations"]
        path.write_bytes(canonical(event))
        with self.assertRaisesRegex(ValueError, "artifact lineage mismatch"):
            evaluate_project(self.raw, self.store)
        path.write_bytes(canonical(original))
        evidence = self.store.root / "objects" / original["artifacts"]["evidence:request"]
        evidence.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            self.store.replay(1)
        self.assertEqual(evidence.read_bytes(), b"corrupt")
