"""Local content-addressed objects and an append-only, hash-linked event log."""

import os
from pathlib import Path

from .workflow import ENGINE, canonical, decode, evaluate, fingerprint, require


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, data: bytes) -> str:
        digest = fingerprint(data)
        directory = self.root / "objects"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / digest
        try:
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            require(path.read_bytes() == data, f"corrupt existing object: {digest}")
        return digest

    def get(self, digest: str) -> bytes:
        require(isinstance(digest, str) and len(digest) == 64 and
                all(c in "0123456789abcdef" for c in digest), "invalid object digest")
        data = (self.root / "objects" / digest).read_bytes()
        require(fingerprint(data) == digest, f"object fingerprint mismatch: {digest}")
        return data

    def events(self) -> list[dict]:
        events = []
        previous = None
        for sequence, path in enumerate(sorted((self.root / "events").glob("*.json")), 1):
            require(path.name == f"{sequence:08d}.json", "event sequence has a gap")
            data = path.read_bytes()
            event = decode(data)
            require(event.get("sequence") == sequence and event.get("previous") == previous,
                    "event lineage mismatch")
            require(event.get("engine") == ENGINE, "unsupported event engine")
            # Verify every referenced object, including older runs.
            require(isinstance(event.get("artifacts"), dict), "invalid event artifacts")
            for digest in event["artifacts"].values():
                self.get(digest)
            previous = fingerprint(data)
            events.append(event)
        return events

    def record(self, raw: bytes) -> dict:
        case = decode(raw)
        report = evaluate(case)
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / ".writer-lock"
        try:
            lock.mkdir()
        except FileExistsError:
            raise ValueError("evidence store is locked; another writer or interrupted run needs review") from None
        try:
            events = self.events()
            artifacts = {"input": self.put(raw), "report": self.put(canonical(report))}
            for name in ("baseline", "contract", "policy"):
                artifacts[name] = self.put(canonical(case[name]))
            for candidate in case["candidates"]:
                artifacts[f"patch:{candidate['id']}"] = self.put(candidate["patch"].encode("utf-8"))
            directory = self.root / "events"
            directory.mkdir(exist_ok=True)
            sequence = len(events) + 1
            previous = None
            if events:
                previous = fingerprint((directory / f"{sequence - 1:08d}.json").read_bytes())
            event = {"sequence": sequence, "previous": previous, "engine": ENGINE,
                     "artifacts": artifacts}
            with (directory / f"{sequence:08d}.json").open("xb") as stream:
                stream.write(canonical(event))
                stream.flush()
                os.fsync(stream.fileno())
            return event
        finally:
            lock.rmdir()

    def replay(self, sequence: int) -> dict:
        events = self.events()
        require(1 <= sequence <= len(events), "event does not exist")
        event = events[sequence - 1]
        artifacts = event["artifacts"]
        case = decode(self.get(artifacts["input"]))
        report = evaluate(case)
        require(canonical(report) == self.get(artifacts["report"]), "replay result mismatch")
        expected = {"input": artifacts["input"], "report": fingerprint(canonical(report)),
                    **report["context"],
                    **{f"patch:{c['id']}": fingerprint(c['patch'].encode("utf-8"))
                       for c in case["candidates"]}}
        require(artifacts == expected, "artifact lineage mismatch")
        return report
