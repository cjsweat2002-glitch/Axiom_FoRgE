# Curated structural ambiguity cases

These synthetic inputs are proposals for reviewer acceptance, not evidence of
independent review or real execution. `expected.json` is a hand-authored oracle;
do not regenerate it from the implementation.

- `valid.json`: explicit requirement, one interpretation, compatible assumption,
  named checks and supplied source/observation text. Expect no structural findings,
  while semantic correctness and approval remain unknown/pending.
- `ambiguous.json`: three supplied interpretations of digit-string operands.
  Expect one multiple-interpretations finding. `digit-pair` distinguishes each
  pair with declared outcomes `5`, `23`, and `TypeError`. `zero-pair` is an
  alternative for the first pair; stable ID ordering chooses `digit-pair`.
- `conflicting.json`: the same `operand-type` key declares `integer` and `string`
  in one component scope. Expect one declared-assumption conflict, without deciding
  which value is right.
- `insufficient-evidence.json`: project scope with no requirement check links,
  requirement source, interpretations, assumption source, or acceptance evidence.
  Expect three high and three medium findings; absence is not refusal or success.

All cases retain the foundation's baseline/contract/policy shape. Context matches
allow the review cycle to display existing fixture comparisons alongside their
plain baseline; they do not imply those comparisons establish the requirement's
meaning. Regression tests separately cover unknown discriminators, stale inputs,
empty contracts, invalid references, authority expansion, corrupted mixed history,
original byte preservation, safe terminal output, and inert code-like text.
