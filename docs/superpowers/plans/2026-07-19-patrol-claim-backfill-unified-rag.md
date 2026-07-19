# Patrol Claim Backfill Unified RAG Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Claim Evolution claim-missing backfill through `PatrolRAGService.retrieve_backfill_chunks`, sharing circuit breaker / index readiness / typed degradation with `enrich_context`.

**Architecture:** One shared `PatrolRAGService` instance owns all Claim Evolution VectorStore I/O. Backfill returns `tuple[list[str], PatrolDegradationProfile | None]`. Claim Evolution merges profiles and always stamps degraded empty results.

**Tech Stack:** Python 3.11+, pytest-asyncio, PatrolRAGService, VectorStoreCircuitBreaker, PatrolDegradationProfile.

## Global Constraints

- Scope is Claim Evolution only; do not expand Contradiction / Method Overlap.
- Preserve outer `run_patrol(..., vector_store=...)` API.
- Degraded empty ≠ clean no-claim: keep `INSUFFICIENT_DATA` but attach degradation fields.
- Delete `_retrieve_claim_backfill_chunks`; forbid raw `query_chunks` from claim evolution.

---

### Task 1: Lock `retrieve_backfill_chunks` defense matrix (RED)

**Files:**
- Modify: `tests/patrol/test_patrol_rag_service.py`
- Modify: `backend/patrol/rag_service.py` (later)

**Interfaces:**
- Produces: `PatrolRAGService.retrieve_backfill_chunks(paper_id, node_label, top_k) -> tuple[list[str], PatrolDegradationProfile | None]`

- [ ] **Step 1: Write failing unit tests**

Add tests for OPEN breaker (zero query calls), index missing, timeout → `QUERY_FAILED`, connection refused → `VECTOR_STORE_UNAVAILABLE` + breaker OPEN, and success returning stripped texts.

- [ ] **Step 2: Run tests and confirm RED**

Run: `uv run pytest tests/patrol/test_patrol_rag_service.py -q --tb=short`  
Expected: missing attribute / import failure for `retrieve_backfill_chunks`.

- [ ] **Step 3: Implement minimal method**

Reuse existing circuit / exists / exception mapping from `enrich_context`; return plain text chunks instead of formatted sections.

- [ ] **Step 4: Re-run tests GREEN**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(patrol): add guarded retrieve_backfill_chunks API"
```

---

### Task 2: Migrate Claim Evolution to shared `rag_service` (RED → GREEN)

**Files:**
- Modify: `backend/patrol/claim_evolution.py`
- Modify: `backend/patrol/service.py`
- Modify: `tests/patrol/test_claim_evolution.py`
- Modify: related claim-evolution callers/tests that pass `vector_store=`

**Interfaces:**
- Consumes: `retrieve_backfill_chunks`
- Produces: `build_claim_evolution_insight(..., rag_service: PatrolRAGService | None = None)`
- Produces: shared-instance wiring from `run_patrol`

- [ ] **Step 1: Write failing Claim Evolution defense tests**

Cover:
1. breaker OPEN → `query_chunks` call count == 0 and insight carries degradation
2. query timeout → degraded stamp + breaker failure recorded
3. clean empty recall remains non-degraded `INSUFFICIENT_DATA`
4. claim evolution path does not call a module-level `_retrieve_claim_backfill_chunks`

- [ ] **Step 2: Confirm RED**

- [ ] **Step 3: Implement migration**

- Delete `_retrieve_claim_backfill_chunks`
- Accept `rag_service` and construct locally only if None (`PatrolRAGService(None)` / wrap temporary store only at service boundary)
- Merge left/right backfill profiles with enrich-context profile
- Attach degradation on both READY and INSUFFICIENT_DATA exits when profile exists
- Pass the same `rag_service` into `_build_claim_evolution_context`

- [ ] **Step 4: Update existing tests to `rag_service=PatrolRAGService(vector_store)`**

- [ ] **Step 5: Run focused Claim Evolution + RAG service tests GREEN**

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(patrol): route claim backfill through PatrolRAGService"
```

---

### Task 3: Sterilize VectorStore bypass and verify

**Files:**
- Modify: `tests/patrol/test_claim_evolution.py` (or new focused test)
- Optional: lightweight AST assertion that `claim_evolution.py` source no longer contains `query_chunks(` / `_retrieve_claim_backfill_chunks`

- [ ] **Step 1: Add sterilization / source-level assertions**

- [ ] **Step 2: Run patrol regression suite**

Run:
`uv run pytest tests/patrol/test_patrol_rag_service.py tests/patrol/test_claim_evolution.py tests/patrol/test_claim_evolution_rq_checkpoints.py -q --tb=short`

- [ ] **Step 3: Run ruff/pyright on touched modules**

- [ ] **Step 4: Commit verification fixes if needed**

```bash
git commit -m "test(patrol): lock claim backfill safety cocoon"
```

## Spec coverage checklist

- Unique RAG proxy for Claim Evolution → Task 2
- Defense lifecycle shared with enrich → Task 1
- Degraded empty stamped, clean empty unstamped → Task 2
- OPEN breaker zero I/O → Tasks 1 and 2
- Timeout / connectivity mapping + breaker accounting → Tasks 1 and 2
- Non-goals respected → no contradiction/method-overlap rewrite
