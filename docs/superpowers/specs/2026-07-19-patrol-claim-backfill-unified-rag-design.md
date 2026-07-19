# Patrol Claim Backfill Unified RAG Entry Design

**Date:** 2026-07-19  
**Status:** Approved for implementation  
**Scope:** Claim Evolution claim-missing backfill only

## Problem

`claim_evolution.py` has a dual VectorStore path:

1. `_retrieve_claim_backfill_chunks` calls `vector_store.query_chunks` directly when Claim/Finding nodes are missing.
2. Later `_build_claim_evolution_context` correctly goes through `PatrolRAGService.enrich_context` (circuit breaker, index readiness, typed degradation).

The bypass path creates silent quality degradation: no circuit breaker, no index probe, no typed degradation stamp, and empty results can be misread as “there is no claim”.

## Decision

Use **Route A**:

- Elevate `PatrolRAGService` as the only Patrol-domain VectorStore proxy for Claim Evolution.
- Add intent API:

```python
async def retrieve_backfill_chunks(
    self,
    paper_id: str,
    node_label: str,
    top_k: int,
) -> tuple[list[str], PatrolDegradationProfile | None]:
```

- Delete `_retrieve_claim_backfill_chunks`.
- `build_claim_evolution_insight` accepts `rag_service: PatrolRAGService | None` instead of consuming raw `VectorStore` for backfill/context.
- `run_patrol` constructs one shared `PatrolRAGService(vector_store)` for Claim Evolution so backfill and enrich share breaker state.

## Non-goals

- Do not rewrite Contradiction / Method Overlap call sites in this change.
- Do not redesign `enrich_context` into a fully structured batch result API.
- Do not parse formatted RAG section strings as a backfill transport.

## Defense lifecycle for `retrieve_backfill_chunks`

```text
start
  -> circuit OPEN? return ([], VECTOR_STORE_UNAVAILABLE)  # zero I/O
  -> exists(paper_id) false? return ([], INDEX_NOT_READY)
  -> exists probe outage? trip breaker, return ([], VECTOR_STORE_UNAVAILABLE)
  -> query_chunks(node_label)
       success -> return (texts, None) and record_success when healthy
       TimeoutError/generic -> ([], QUERY_FAILED)
       connectivity -> trip breaker, ([], VECTOR_STORE_UNAVAILABLE)
```

## Degradation merge semantics

- Merge left/right backfill profiles with context-enrichment profile via `merge_degradation_profiles`.
- Distinguish:
  - **non-degraded empty**: genuine no-claim / no-recall → `INSUFFICIENT_DATA` without degradation stamp.
  - **degraded empty**: infra failure → still may be `INSUFFICIENT_DATA`, but **must** attach `is_degraded=True` + `degradation_profile` via `attach_degradation_fields`.
- Never treat degraded empty as a clean “no claim exists” conclusion.

## Compatibility

- Prefer `rag_service=` as the Claim Evolution injection point.
- `run_patrol(..., vector_store=...)` remains the outer orchestration API; it wraps into `PatrolRAGService`.
- Existing Claim Evolution tests that pass `vector_store=` are updated to pass `rag_service=PatrolRAGService(vector_store)`.

## Tests

1. `retrieve_backfill_chunks` unit matrix: OPEN breaker / index missing / timeout / connectivity / success.
2. Claim Evolution zero-I/O when breaker OPEN.
3. Claim Evolution timeout propagates typed degradation and trips breaker.
4. Claim Evolution no longer imports/calls a direct VectorStore query helper.
5. Existing READY / INSUFFICIENT_DATA happy paths remain green.
