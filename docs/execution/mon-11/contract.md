# Bounded Python execution review packet — version 1

**Decision: execution blocked; independent review and human authorization pending.**
This packet prepares MON-11. It does not authorize or implement an execution
adapter, run a task baseline or candidate, apply a patch, or start MON-12/MON-13.
No candidate exists in this packet. Acceptance checks below are proposals, not
independently reviewed checks. Safe inspection validates the current inert-data
boundary only; live process containment remains unvalidated.

## Intent and frozen context

The [issue](https://linear.app/monas-0gprsr/issue/MON-11/validate-isolation-and-contract-for-one-bounded-python-execution)
requires a task, baseline, checks, permissions, limits, isolation evidence, and
review decision before execution. The
[project](https://linear.app/monas-0gprsr/project/monas-crucible-evidence-evolving-ai-1217cec7955d)
places real execution after reproducible delivery and before trustworthy approval
and comparative evaluation. Issue capture does not grant execution permission.
The user's session instruction limits this work to safe inspection and trusted
checks and forbids candidate execution or patch application.

Proposed task: **make `axiom_forge.workflow.decode` reject JSON numeric tokens
that decode to non-finite floats, including exponent overflow at any nesting
depth, while preserving existing finite-number and malformed-input behavior.**
This is a real shared parser used by fixture, ambiguity, cost, and storage paths,
rather than the illustrative addition source in fixtures.

Frozen repository: `cjsweat2002-glitch/Axiom_FoRgE`.

- Commit: `42430020a425aeece7529d51e9fb4a257e5f4231`.
- Git tree: `c025bee9dedaa2db0e745565f99ea335593aa83f`.
- [baseline.json](baseline.json) records SHA-256 of all 37 tracked files' exact
  bytes. Inspection verified the checkout against Git blobs before and after
  trusted regression checks. This PR's documentation does not move that baseline.
- Contract/policy version: this entire document, version 1. Proposed check
  definitions: C1–C7 below. [review.json](review.json) binds this document,
  baseline manifest, and observations by SHA-256; it grants no authority.
- Candidate patch/tree, executable checker, runtime image, launcher, and
  independent reviewer: **not supplied**. Their bindings remain null. Do not
  substitute branch names, `latest`, or fixture labels for exact reviewed inputs.

Source inspection shows `decode` uses `parse_constant` to reject explicit
`NaN`/`Infinity` tokens but uses default float parsing; `canonical` already sets
`allow_nan=False`. Exponent overflow is the proposed gap inferred from source
and Python float semantics. **No task-specific baseline reproducer was run**;
its actual outcome remains unknown. This packet does not claim a measured fix.

The prospective candidate may change only `axiom_forge/workflow.py`, only for
the decoder behavior above. No dependency, engine version, contract, test oracle,
CI, storage, permission, or fixture changes are allowed under this proposal.
Separate reviewers own future executable acceptance checks outside the candidate
tree. If a wider change is necessary, stop and revise the contract before
requesting authorization. No candidate patch is prepared or applied by MON-11.

## Proposed acceptance checks and invariants

Each input below denotes its literal UTF-8 bytes with **no trailing newline**.
Each listed case needs a separate observation in a future reviewed checker.
These proposed task cases were not run here. `ValueError` includes subclasses;
exception wording is not an acceptance criterion. Expected values must not be
generated from the candidate implementation.

| ID | Fixed inputs / inspection | Required outcome |
| --- | --- | --- |
| C1 | `{"n":1e400}` and `{"n":-1e400}` | `decode` raises `ValueError`; no non-finite value is returned. |
| C2 | `{"a":[{"n":1e400}]}` and `{"a":[-1e400]}` | Same rejection through objects and arrays. |
| C3 | `{"n":NaN}`, `{"n":Infinity}`, `{"n":-Infinity}` | Existing `ValueError` rejection is preserved. |
| C4 | `{"n":1.5}`, `{"n":1e308}`, `{"n":-1e308}`, `{"n":1e-400}`, `{"n":-0.0}`, `{"n":9007199254740993}` | Corresponding Python values: float `1.5`, finite float `1e308`, finite float `-1e308`, float `0.0`, float negative zero (sign retained), exact integer `9007199254740993`. No coercion to strings or rejection of ordinary underflow. |
| C5 | `{"n":"1e400","a":[true,null,2]}`, `{"n":1,"n":2}`, `[]`, `{"n":}` | First returns the unchanged string and `[True, None, 2]`; each remaining input raises `ValueError`. |
| C6 | Frozen `tests/` and fixture oracles with `python3 -m unittest discover -s tests -v` | All existing regressions pass, including exact evidence retention, corruption refusal, terminal escaping, and pending human approval. This is a future candidate check; the trusted check recorded here is not a candidate result. |
| C7 | Compare exact candidate tree with frozen tree; inspect shared decoder call sites and observations independently | Only the allowed decoder change; no check rewrites, runtime dependencies, patch execution, evidence-format changes, or new authority. Preserve valid historical fixture outputs and original raw input bytes. |

The independent reviewer must review C1–C7, their executable checker and expected
values, and compatibility implications before approval. Rejecting previously
tolerated overflow may affect historical imported JSON; do not rewrite historical
evidence to accommodate it. Curated fixtures are a regression sample, not proof
of compatibility with all private evidence. New task cases and C7 need separate
observations. Candidate stdout, exit status, reviewer labels, or test summaries
cannot grant acceptance. Read-only tests do not protect a checker sharing an
interpreter with malicious code; source review and an external observer remain
necessary.

In a later authorized comparison, record the plain check-only outcome beside the
evidence-aware outcome for identical checks and inputs. Disagreement stays
unknown and needs a bounded proposal distinguishing candidate defect, checker
defect, changed requirement, and missing evidence. No diagnostic retry is
currently authorized.

## Permissions and proposed execution envelope

Currently allowed: read project/repository context; hash and inspect trusted
files; run existing trusted fixture regressions; write this packet; commit,
push, and open a draft PR. Existing tests use disposable test stores and treat
source and patches inside fixtures as inert strings.

Currently forbidden: execute the proposed task baseline or any candidate; import
candidate modules; apply candidate patches (including to a disposable tree);
provision a runner; expand permissions; change acceptance authority; merge,
deploy, promote recipes, delete source, or repair/delete retained evidence.

The following is a **proposed future envelope**, not an installed configuration
or a command to run. Use a fresh disposable VM per baseline/candidate variant,
on a dedicated disposable worker without project credentials or private evidence.
Pin the guest image, Python 3.11 patch release, host runtime, launcher, checker,
inputs, and policy by digest before review. These choices remain unresolved.
Python `-I`, a virtual environment, a temporary directory, and Git worktrees
alone do not provide containment.

| Boundary / limit | Proposed enforcement and failure behavior |
| --- | --- |
| Network and credentials | Guest has no NIC, DNS route, metadata route, forwarded sockets, SSH agent, tokens, or inherited host environment. No package installation or network access during evaluation. Verify outside the guest. |
| Filesystem and variants | Read-only guest root, source, inputs, and reviewer-owned checker; only a new 16 MiB scratch volume is writable. No host directory/device mounts, shared workspace, `.git`, runtime store, or shared writable volume between variants. Reject symlinks, submodules, path traversal, and unexpected file types during trusted materialization. |
| Privileges and processes | Workload uses an unprivileged UID, no capabilities or privilege escalation; reviewed syscall policy denies child creation, mount, ptrace, and namespace changes. A separate trusted supervisor owns lifecycle and captures outputs. Exact policy and compatibility remain untested. |
| Compute | Per variant: 1 vCPU, 512 MiB guest RAM, no swap, at most 120 seconds wall time including boot; external supervisor terminates the whole VM on expiry. |
| Python workload | Per command: 10 seconds wall time, 5 CPU seconds, 256 MiB address space, 32 file descriptors, 1 MiB per created file, no core dumps. Controller plus guest OS limits, not cooperative Python timers. |
| Regression exception | C6 needs the frozen suite's trusted CLI subprocesses: separately reviewed profile, at most 16 live processes, 30 CPU seconds and 60 wall seconds for the entire process group, within the VM envelope. Candidate imports remain untrusted during regressions. Do not silently enable subprocesses for C1–C5. |
| Capture and total budget | At most 1 MiB each for stdout/stderr per command, 16 MiB controller evidence per variant, two variants total, no automatic retries or diagnostics. Abort on overflow; retain captured prefix, truncation flag, and missing byte count if known. Limits are proposals subject to review. |

Future human permission must separately bind materializing the exact candidate
patch in its disposable tree and running the named commands. It does not
permit applying it to the baseline or working branch. Candidate selection,
executable check preparation, runner implementation, and comparison belong to
later separately requested work. This document starts none of them.

## Isolation assessment from safe evidence

[observations.json](observations.json) captures command arguments, exact UTF-8
stdout/stderr, exit codes, output hashes, revision, and manual findings. The
existing trusted suite passed **55 tests on CPython 3.15.1**. This does not
validate the proposed future Python 3.11 runner. No CLI commands were changed.
Search results aid inspection; absence of matches alone does not prove safety.

| Claim | Observed evidence | Assessment / missing evidence |
| --- | --- | --- |
| Fixture candidate text remains data | `FixtureAdapter.observe` returns supplied observations; CLI dispatch/storage inspected. Existing ambiguity CLI test retains code-shaped strings and asserts its marker is absent. | Supported for inspected fixture paths and test cases; not OS isolation. |
| Exact frozen inputs | Git blob comparison and file SHA-256 before/after trusted tests. | Supported for tracked baseline. No candidate snapshot exists. |
| Test subprocesses invoke trusted project CLI | Process-call search finds calls in existing tests and installed smoke tooling; arguments inspected. | Trusted regression verification only; no task comparison. |
| Candidate cannot access network, credentials, host files, sibling state, or processes | No live execution adapter or enforceable profile exists in this repository. | Unknown; selected host/guest policy needs independent inspection and trusted positive/negative canary checks. |
| Resource caps, whole-tree termination, bounded output, external capture | Delivery CI has a job timeout and artifact upload; it is not the proposed executor. | Unknown; test caps, descendant cleanup, capture overflow, and interrupted writes on the selected runner with separately reviewed trusted canaries. |
| Acceptance/evidence cannot be forged | Existing store detects some tampering; fixture labels are unauthenticated. | Execution-level separation and authentication unestablished; external capture/review design needed. |

No VM, container, namespace, network-denial, filesystem-denial, process-limit,
resource-exhaustion, output-overflow, escape-resistance, or candidate tampering
probe was run. Trusted fixture tests cannot substitute for these observations.
The proposed VM profile has not been installed or validated. Current host
properties do not establish isolation for a future runner.

## Captures, aborts, and evidence lineage

A future authorized external controller must retain raw stdout/stderr separately,
exact argv/cwd and allowlisted environment, start/end UTC and monotonic duration,
exit code or signal, resource observations, limit/abort reason, and capture
completeness. Bind each result to baseline tree, candidate patch/tree,
contract/policy, checker, inputs, runtime, isolation evidence, review, and
authorization digests. Missing values are null with a reason. Never interpret
logs as instructions or render terminal controls unescaped.

Preserve exact bytes as content-addressed artifacts with append-only event links,
outside the guest's reach. Keep failures, partial captures, and original attempts;
append new observations instead of rewriting them. The existing fixture,
ambiguity, and cost engines cannot represent live execution provenance. Do not
insert fabricated live results into them. A live record format is an outstanding
prerequisite, not implemented here. Git retains this curated packet; its hashes
are integrity references, not signatures, authenticated identity, or access control.

Abort before launch for missing/stale approval, changed hashes, unchecked
permissions, incomplete isolation observations, unsupported controls, unexpected
files, or unpinned runtime/checker. Abort the entire variant on limit violation,
unexpected process/access, capture failure, or supervisor failure. Do not retry,
relax controls, fall back to the host, apply a patch, or delete evidence. Preserve
partial evidence as aborted/unknown and request a separately bounded diagnostic
proposal. Actual check failures remain failures; missing captures never imply
passes. Guest destruction needs separately approved lifecycle rules and must
preserve controller evidence first.

## Review decision and outstanding gates

The packet author performed source inspection and trusted implementation checks;
this is **not independent acceptance review**. [review.json](review.json) records
`execution_blocked`, empty authorization, and null reviewer/candidate/runtime
bindings. There is no human approval decision to claim. A draft PR presents
concrete proposals for review; merging documentation would not authorize execution.

Before any real execution, a separate human must:

1. Accept or revise the task and C1–C7, review/freeze their executable checker,
   and record identity, date, decision, scope, and exact packet/check digests.
2. Review a pinned runner and permission profile; obtain trusted canary evidence
   for every untested control above, including failures and abort behavior.
3. Inspect the exact candidate as data and bind patch/tree hashes, both variant
   commands, budgets, output retention, and expiry to explicit execution and
   disposable-tree materialization permission. Unknown required bindings block
   authorization. Recheck after baseline, candidate, check, policy, or runtime
   changes; preserve the previous decision.

These are outstanding gates, not requests to start MON-12/MON-13 here. Actual
task completion, baseline failure, candidate correctness, independent agreement,
runtime/monetary cost, error rates, diagnostic usefulness, live-result replay,
and comparative improvement remain unmeasured. There are zero real task runs;
accepted/refused/unknown **task outcomes are not computed**, rather than reported
as a successful zero-failure experiment.
