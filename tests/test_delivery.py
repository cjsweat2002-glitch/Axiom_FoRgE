"""Regression checks for the archive verifier, without build-tool dependencies."""

import io
from pathlib import Path
import runpy
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = runpy.run_path(str(ROOT / "scripts" / "check_sdist.py"))


class SourceArchiveTests(unittest.TestCase):
    def make_archive(self, directory, *, omitted=None, changed=None, duplicate=None):
        path = Path(directory) / "source.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name in sorted(CHECKER["reproduction_files"](ROOT)):
                if name == omitted:
                    continue
                data = b"changed\n" if name == changed else (ROOT / name).read_bytes()
                member = tarfile.TarInfo(f"axiom_forge-0.1.0/{name}")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
                if name == duplicate:
                    archive.addfile(member, io.BytesIO(data))
        return path

    def test_complete_archive_matches_source(self):
        with tempfile.TemporaryDirectory() as directory:
            count = CHECKER["check_sdist"](self.make_archive(directory), ROOT)
            self.assertEqual(count, len(CHECKER["reproduction_files"](ROOT)))

    def test_missing_reproduction_assets_are_rejected(self):
        # Independently name the original omissions and inputs needed to reproduce.
        for name in ("docs/verification.md", "requirements-verification.txt",
                     "scripts/verify.sh", "scripts/smoke_installed.py",
                     "scripts/check_sdist.py", "tests/test_cli.py",
                     "tests/fixtures/baseline.json", "tests/fixtures/expected.json",
                     "docs/cost-evaluation.md"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self.make_archive(directory, omitted=name)
                with self.assertRaisesRegex(ValueError, "reproduction asset"):
                    CHECKER["check_sdist"](path, ROOT)

    def test_changed_or_duplicate_asset_is_rejected(self):
        for alteration in ("changed", "duplicate"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as directory:
                path = self.make_archive(directory, **{alteration: "scripts/verify.sh"})
                with self.assertRaisesRegex(ValueError, "reproduction asset"):
                    CHECKER["check_sdist"](path, ROOT)

    def test_new_local_readme_links_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "README.md").write_text(
                "[guide](docs/new-guide.md#reproduce) [remote](https://example.com)\n",
                encoding="utf-8")
            (root / "docs/verification.md").write_text("", encoding="utf-8")
            self.assertIn("docs/new-guide.md", CHECKER["reproduction_files"](root))
