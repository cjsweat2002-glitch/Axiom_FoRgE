# Deterministic comparison fixtures

`baseline.json` is synthetic evidence for a tiny Python addition workflow. Its
five candidates use inert unified diffs and asserted observations. Nothing here
is a record of model generation, authenticated review, or live patch execution.

`expected.json` is a hand-specified oracle: each candidate maps to its expected
status, diagnostic reason, and plain generate-and-test status. Review this oracle
independently of implementation changes; never regenerate it from the classifier.

`prior-contract.json` retains the old contract referenced by the changed-contract
candidate. Other candidates bind the current baseline, contract, and policy by
SHA-256 of canonical JSON. Updating those snapshots requires deliberate fixture
review and new fingerprints, not silently accepting stale observations.

The passing patch adds a docstring; the regression patch changes addition to
subtraction. The faulty-verifier case asserts a failing verifier alongside a
passing independent observation; its disposition remains unknown. The missing
evidence case uses null. The stale-contract case retains a prior fingerprint and
must be rechecked even though its supplied verifier says pass.
