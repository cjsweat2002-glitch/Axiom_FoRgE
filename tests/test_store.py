from pathlib import Path
import tempfile
import unittest

from axiom_forge.store import EvidenceStore
from axiom_forge.workflow import canonical, decode, fingerprint

FIXTURE = Path(__file__).parent / "fixtures" / "baseline.json"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EvidenceStore(Path(self.temp.name))
        self.raw = FIXTURE.read_bytes()

    def test_exact_inputs_deduplication_and_append_only_history(self):
        first = self.store.record(self.raw)
        path = self.store.root / "events" / "00000001.json"
        original = path.read_bytes()
        objects = set((self.store.root / "objects").iterdir())
        second = self.store.record(self.raw)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(second["previous"], fingerprint(original))
        self.assertEqual(objects, set((self.store.root / "objects").iterdir()))
        self.assertEqual(self.store.get(first["artifacts"]["input"]), self.raw)
        self.assertEqual(self.store.replay(1), self.store.replay(2))

    def test_contract_changes_preserve_historical_outcomes(self):
        self.store.record(self.raw)
        case = decode(self.raw)
        case["contract"]["version"] = "add-v2"
        self.store.record(canonical(case))
        self.assertEqual(self.store.replay(1)["totals"]["accepted"], 1)
        self.assertEqual(self.store.replay(2)["totals"]["unknown"], 5)

    def test_modified_object_is_detected_and_never_overwritten(self):
        event = self.store.record(self.raw)
        path = self.store.root / "objects" / event["artifacts"]["input"]
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            self.store.replay(1)
        with self.assertRaisesRegex(ValueError, "corrupt existing"):
            self.store.put(self.raw)
        self.assertEqual(path.read_bytes(), b"tampered")

    def test_broken_chain_and_deleted_event_are_detected(self):
        self.store.record(self.raw)
        self.store.record(self.raw)
        path = self.store.root / "events" / "00000001.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "lineage mismatch"):
            self.store.replay(2)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "sequence has a gap"):
            self.store.replay(2)

    def test_replay_rejects_forged_result_and_artifact_links(self):
        event = self.store.record(self.raw)
        path = self.store.root / "events" / "00000001.json"
        report = self.store.replay(1)
        report["human_approval"] = "approved"
        original_digest = event["artifacts"]["report"]
        event["artifacts"]["report"] = self.store.put(canonical(report))
        path.write_bytes(canonical(event))
        with self.assertRaisesRegex(ValueError, "replay result mismatch"):
            self.store.replay(1)
        event["artifacts"]["report"] = original_digest
        event["artifacts"]["contract"] = event["artifacts"]["policy"]
        path.write_bytes(canonical(event))
        with self.assertRaisesRegex(ValueError, "artifact lineage mismatch"):
            self.store.replay(1)

    def assert_append_refuses_without_changes(self, message):
        def snapshot():
            return {path.relative_to(self.store.root): path.read_bytes()
                    for path in self.store.root.rglob("*") if path.is_file()}

        before = snapshot()
        with self.assertRaisesRegex(ValueError, message):
            self.store.record(self.raw)
        self.assertEqual(snapshot(), before)
        self.assertFalse((self.store.root / ".writer-lock").exists())

    def test_append_refuses_empty_historical_artifacts(self):
        event = self.store.record(self.raw)
        event["artifacts"] = {}
        (self.store.root / "events" / "00000001.json").write_bytes(canonical(event))
        self.assert_append_refuses_without_changes("invalid event artifacts")

    def test_append_refuses_historical_report_with_valid_hash_but_false_approval(self):
        event = self.store.record(self.raw)
        report = self.store.replay(1)
        report["human_approval"] = "approved"
        event["artifacts"]["report"] = self.store.put(canonical(report))
        (self.store.root / "events" / "00000001.json").write_bytes(canonical(event))
        self.assert_append_refuses_without_changes("replay result mismatch")

    def test_append_validates_historical_structure_and_artifact_bindings(self):
        root = self.store.root
        mutations = [
            (lambda e: e.pop("previous"), "event must contain exactly"),
            (lambda e: e.update(sequence=True), "event lineage mismatch"),
            (lambda e: e.update(extra=True), "event must contain exactly"),
            (lambda e: e.update(artifacts=[]), "invalid event artifacts"),
            (lambda e: e["artifacts"].pop("input"), "invalid event artifacts"),
            (lambda e: e["artifacts"].pop("report"), "invalid event artifacts"),
            (lambda e: e["artifacts"].pop("contract"), "invalid event artifacts"),
            (lambda e: e["artifacts"].pop("patch:passing"), "artifact lineage mismatch"),
            (lambda e: e["artifacts"].update(extra=e["artifacts"]["input"]),
             "artifact lineage mismatch"),
            (lambda e: e["artifacts"].update(contract=e["artifacts"]["policy"]),
             "artifact lineage mismatch"),
        ]
        for index, (mutate, message) in enumerate(mutations):
            with self.subTest(index=index):
                self.store = EvidenceStore(root / str(index))
                event = self.store.record(self.raw)
                path = self.store.root / "events" / "00000001.json"
                mutate(event)
                path.write_bytes(canonical(event))
                self.assert_append_refuses_without_changes(message)

    def test_replaying_later_event_rejects_incoherent_earlier_evidence(self):
        first = self.store.record(self.raw)
        second = self.store.record(self.raw)
        report = self.store.replay(1)
        report["human_approval"] = "approved"
        false_report = self.store.put(canonical(report))
        for artifacts, message in (({}, "invalid event artifacts"),
                                   ({**first["artifacts"], "report": false_report},
                                    "replay result mismatch")):
            with self.subTest(message=message):
                altered = canonical({**first, "artifacts": artifacts})
                (self.store.root / "events" / "00000001.json").write_bytes(altered)
                # Keep the hash chain valid to isolate semantic history validation.
                second["previous"] = fingerprint(altered)
                (self.store.root / "events" / "00000002.json").write_bytes(canonical(second))
                with self.assertRaisesRegex(ValueError, message):
                    self.store.replay(2)

    def test_lock_blocks_writers_without_changing_history(self):
        (self.store.root / ".writer-lock").mkdir()
        with self.assertRaisesRegex(ValueError, "locked"):
            self.store.record(self.raw)
        self.assertFalse((self.store.root / "events").exists())

    def test_invalid_input_does_not_create_evidence(self):
        with self.assertRaises(ValueError):
            self.store.record(b'{}')
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_invalid_event_and_digest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "event does not exist"):
            self.store.replay(1)
        with self.assertRaisesRegex(ValueError, "invalid object digest"):
            self.store.get("../secret")
