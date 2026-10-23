#!/usr/bin/env bash
# Run from a clean checkout or explicitly selected unpacked source archive.
set -euo pipefail
set -x

source_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$source_root"
case "${2:-}" in
    "")
        git rev-parse HEAD
        git diff --exit-code
        git diff --cached --exit-code
        test -z "$(git ls-files --others --exclude-standard)"
        ;;
    --source-archive)
        test -f PKG-INFO
        test ! -e .git
        printf '%s\n' 'Verifying unpacked source archive; Git revision is unknown.'
        ;;
    *) printf 'Unknown verification mode: %s\n' "$2" >&2; exit 2 ;;
esac
test "$#" -le 2

# Require a new directory: never overwrite a prior verification or evidence store.
verification_root=${1:?Usage: bash scripts/verify.sh /absolute/new-output-directory [--source-archive]}
[[ "$verification_root" = /* ]]
mkdir "$verification_root"
unset PYTHONPATH PYTHONHOME
python3 --version
uname -a
python3 -m venv "$verification_root/build-env"
build_python="$verification_root/build-env/bin/python"
"$build_python" -m pip install -r requirements-verification.txt
"$build_python" -m pip freeze --all
"$build_python" -m unittest discover -s tests -v

# By default build makes an sdist, then builds the wheel FROM that sdist.
# All build dependencies are pinned above, so avoid another resolver environment.
"$build_python" -m build --no-isolation --outdir "$verification_root/dist"
sha256sum "$verification_root"/dist/*
"$build_python" scripts/check_sdist.py "$verification_root"/dist/*.tar.gz

python3 -m venv "$verification_root/installed-env"
installed_python="$verification_root/installed-env/bin/python"
"$installed_python" -m pip install --no-index --no-deps "$verification_root"/dist/*.whl
"$installed_python" -m pip check
"$installed_python" -m pip freeze --all

# Neither the checkout nor its package may satisfy imports in these checks.
mkdir "$verification_root/working"
cd "$verification_root/working"
"$installed_python" -I "$source_root/scripts/smoke_installed.py" "$source_root/tests/fixtures"
"$installed_python" -I -m unittest discover -s "$source_root/tests" -v
