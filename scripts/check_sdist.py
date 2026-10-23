"""Check reproduction assets in the built sdist without extracting the archive."""

from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
from urllib.parse import unquote, urlsplit


REQUIRED_FILES = {
    "README.md", "AGENTS.md", "MANIFEST.in", "pyproject.toml",
    "docs/verification.md", "requirements-verification.txt",
    "scripts/verify.sh", "scripts/smoke_installed.py", "scripts/check_sdist.py",
}


def reproduction_files(source_root):
    required = set(REQUIRED_FILES)
    # Include the suite and curated inputs needed by source and installed checks.
    required.update(path.relative_to(source_root).as_posix()
                    for path in (source_root / "tests").rglob("*")
                    if path.is_file() and path.suffix in {".py", ".json", ".md"})
    # Follow local inline Markdown links in the delivery entry points as well.
    for document in ("README.md", "docs/verification.md"):
        content = (source_root / document).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^\s)]+)\)", content):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            path = (source_root / document).parent / unquote(url.path)
            required.add(path.resolve().relative_to(source_root.resolve()).as_posix())
    return required


def check_sdist(archive_path, source_root):
    required = reproduction_files(source_root)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1:
            raise ValueError("sdist must have exactly one top-level directory")
        root = roots.pop()
        for name in sorted(required):
            matches = [member for member in members if member.name == f"{root}/{name}"]
            if len(matches) != 1 or not matches[0].isfile():
                raise ValueError(f"missing, duplicate, or non-file reproduction asset: {name}")
            with archive.extractfile(matches[0]) as archived:
                if archived.read() != (source_root / name).read_bytes():
                    raise ValueError(f"reproduction asset differs from source: {name}")
    return len(required)


if __name__ == "__main__":
    count = check_sdist(Path(sys.argv[1]), Path(__file__).resolve().parents[1])
    print(f"Sdist completeness: {count} reproduction assets match source bytes.")
