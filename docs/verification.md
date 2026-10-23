# Reproducible delivery contract

This increment starts from merged main revision
`d1a12a56f1aa2cc624edbe667e2fda3002190d77` (foundation PR #1). Its intent is to
verify delivery of the existing fixture CLI, following the project's proposed
reproducible-delivery stage. It adds no execution adapter or acceptance authority.

## Checks and invariants

`pyproject.toml` declares `requires-python = ">=3.11"` and no runtime dependencies.
The CI matrix covers that minimum and Python 3.14, a current supported release,
on Ubuntu 24.04. Keep the matrix minimum aligned with metadata when support changes.
Patch releases float; each run prints the actual interpreter and operating system.

`scripts/verify.sh` requires a clean tracked checkout and a new, absolute output
directory. It fails on any unsuccessful step and prints commands, the exact Git
revision, interpreter, installed tooling versions, and distribution SHA-256 hashes.
It performs the following proposed acceptance checks:

1. Run the full existing regression suite from source, including historical
   corruption, append refusal without mutation, and terminal-injection cases.
2. Build an sdist and then a wheel **from the sdist**, with the delivery tooling
   pinned in `requirements-verification.txt`. No runtime dependency is added.
3. Install that wheel without dependency resolution or index access in a second
   fresh virtual environment, then run `pip check`.
4. From a directory outside the checkout, verify the installed package location
   and console script: version/help, inspect, run, replay, report, and missing
   input/event errors. Compare results with the unchanged curated oracle, retain
   exact fixture input bytes, and require human approval to remain pending.
5. Run the full regression suite again against the installed package. Python's
   isolated mode and cleared `PYTHONPATH`/`PYTHONHOME` prevent source imports from
   masking a broken installation, including in CLI subprocesses.

Fixture source and candidate patches remain inert data. Existing source modules,
fixtures, oracles, and evidence format are unchanged. These checks exercise the
trusted project CLI and tests; they do not run untrusted candidate code, apply
patches, approve candidates, promote recipes, merge, or deploy. Passing them is
implementation verification, not independent acceptance approval.

## Reproduce

On Linux with Bash, Git, and the desired Python interpreter installed, create a
fresh checkout of the revision under review. Tool installation needs network
access to the Python package index. For example, replace `REVISION` below with
the exact commit SHA:

```sh
git clone https://github.com/cjsweat2002-glitch/Axiom_FoRgE.git axiom-verification
cd axiom-verification
git checkout --detach REVISION
# Put Python 3.11 or 3.14 on PATH as python3; repeat in a fresh checkout for each.
python3 --version
verification_parent=$(mktemp -d)
set -o pipefail
bash scripts/verify.sh "$verification_parent/results" 2>&1 | tee "$verification_parent/verification.log"
```

The output directory must not already exist. Failed runs are retained for
investigation; rerun with a new directory instead of repairing old evidence.
`dist/` holds both distributions; `working/` holds the synthetic evidence store
and each smoke command's stdout/stderr. The log captures command exits through
the fail-fast shell, regression results, environment, revision, and artifact
hashes. Keep it together with the output directory. A failed early step leaves
later checks unperformed, not successful.

GitHub Actions runs the same script for pull requests, pushes to main, and manual
runs, with read-only repository permissions. It retains logs, distributions, and
smoke outputs for 14 days even on failure. PR runs may test GitHub's synthetic
merge revision; the printed `git rev-parse HEAD` identifies what was actually
checked. Consult the run linked to that revision before claiming CI success.

## Observed results and limits

Implementation-side checks on 2026-10-23 used fresh local clones at
`b5fc3ce5afe886e11547733d6c385d548f9f3a8c` on Linux x86_64. The subsequent
documentation-only commit records these results; it was not the tested revision.

| Interpreter | Source regressions | Sdist → wheel / install / pip check | Installed smoke | Installed regressions |
| --- | --- | --- | --- | --- |
| CPython 3.11.17 | 24 passed | passed | 8 commands passed | 24 passed |
| CPython 3.14.9 | 24 passed | passed | 8 commands passed | 24 passed |

Both runs used the pinned build tooling. The installed environments used bundled
pip 26.2.2 (and bundled setuptools 79.0.1 on 3.11). Each installed wheel had SHA-256
`b5449d4f03a8a28698a43505fc15fde35239c4314093685bdb40e52e92da7bcc`.
Local logs and outputs are retained under `/tmp/axiom-mon8-3.11-jX8I4q/` and
`/tmp/axiom-mon8-3.14-Fz23ye/`; these are session-local evidence, not durable CI
artifacts. `actionlint` 1.7.7, `bash -n scripts/verify.sh`, and `git diff --check`
also passed. GitHub-hosted CI has not been observed for this increment.

Two initial invocations accidentally selected Python 3.15.1 through a shell
startup hook. Their source regressions passed, but build 1.3.0 failed in argument
parsing (`HelpFormatter.__init__()` rejected `color`); install and smoke checks
were not reached. Those logs remain under `/tmp/axiom-mon8-3.11-S11jHl/` and
`/tmp/axiom-mon8-3.14-VJuPsn/` despite their intended-version directory labels.
The successful invocations used `mise exec python@3.11` / `python@3.14` followed
by `env -u BASH_ENV bash --noprofile --norc scripts/verify.sh OUTPUT` to preserve
the selected interpreter. The pinned delivery toolchain is verified only on the
matrix versions; Python 3.15 packaging remains a known gap, distinct from the
CLI's declared runtime minimum.

This is repeatable functional verification, not a bit-for-bit reproducible build
claim. OS images, Python patch releases, package-index availability, and bundled
installer versions can vary; tooling pins do not authenticate downloads. Other
operating systems and Python versions are not covered by this matrix. CI artifacts
expire and are not an authenticated provenance ledger or approval record. A
revision-bound verification manifest with mismatch detection remains a proposed
follow-up, not an implemented guarantee.

## Next expansion gate

Before the smallest real execution slice, define one bounded Python repository
task with an exact frozen baseline, independently reviewed acceptance checks,
explicit permissions, command-output capture, and time/resource limits. Review
and validate isolation before running any untrusted candidate code. Require a
reproducible baseline/candidate comparison with failures and unknowns preserved;
no automatic patch application. A passing delivery check alone does not open
that gate. Authenticated approval, comparative performance, recipe reuse, and
domain adapters remain separate later increments.
