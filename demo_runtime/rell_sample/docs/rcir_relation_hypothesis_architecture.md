# RCIR Relation Hypothesis Architecture

The language front end extracts explicit role and relation constraints. It does
not establish a physical relation. When a placement relation is omitted, the
relation hypothesis generator derives candidate `Predicate` objects from the
destination concept's functional affordances and the current read-only
`WorldFactLedger` projection.

```text
SituatedEventGraph + Concept/Affordance + read-only WorldFactLedger
  -> RelationHypothesisGenerator
  -> Predicate(modality=hypothesis) candidates
  -> unique candidate: goal candidate remains subject to P018 and P016
  -> competing candidates: InquiryContract and orchestration blocked
  -> P016 result: write through WorldFactLedger only
```

Each candidate carries structured provenance:

- `explicit_spatial_marker`, `current_verified_relation`, or
  `defaulted_from_affordance`;
- premise references;
- strength used for audit, never as permission to silently erase ambiguity;
- interaction turn, temporal anchor, world revision, and revision expiry.

The workset is task working memory. It cannot commit a runtime fact, cannot
retain a private history, and is locally invalidated when its graph, entities,
evidence, or world revision changes. A verified result is not written back to
the generator. P016 writes it to the ledger, which a later generation pass may
read as current evidence.

Formal invariants:

1. `ambiguous_relation_never_silently_becomes_unique`
2. `relation_generator_is_not_fact_authority`
3. `p016_writes_fact_only_through_world_fact_ledger`
4. `relation_generator_reads_only_current_ledger_projection`
5. `relation_candidates_are_ephemeral_task_memory`

Run the focused evidence check with:

```powershell
python .\demo_runtime\rell_sample\validate_relation_hypothesis_architecture.py
```
