# First-Class Paper Lifecycle Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote delete and re-extract use cases to independently injectable services and prevent orchestration code from piercing `PaperService._paper_repo`.

**Architecture:** `PaperDeleteService` and `ReextractService` directly own injected `PaperRepository` and `PaperPipelineOpsService` dependencies. `PaperService` remains the HTTP-facing facade but only delegates to these services. The AST gate is a **capability-based** owner check (role globs for core/repository/facade/coordinator/pipeline-ops); lifecycle services are non-owners and store the inject as `_paper_repository` so any `._paper_repo` / `._pipeline_repo` mention (including foreign pierce) melts in CI.

**Tech Stack:** Python 3.11+, FastAPI service layer, SQLAlchemy async repositories, pytest, AST architecture checks, Ruff, Pyright.

## Global Constraints

- Preserve REST/API behavior and error codes.
- Remove the old module-level `delete_paper(paper_service, ...)` and `force_reextract(paper_service, ...)` contracts.
- Do not expand the refactor into VectorStore resolution or PaperWarningService.
- Keep all filesystem I/O off the event-loop thread.
- New public classes and functions require docstrings and complete type signatures.

---

### Task 1: Lock the service contracts with failing tests

**Files:**
- Modify: `tests/services/test_paper_delete_service.py`
- Modify: `tests/services/test_reextract_service.py`
- Create: `tests/scripts/test_paper_repo_lod.py`

**Interfaces:**
- Produces: `PaperDeleteService(paper_repo, pipeline_ops).delete(...)`
- Produces: `ReextractService(paper_repo, pipeline_ops).force_reextract(...)`
- Produces: AST rule allowing `self._paper_repo` and rejecting non-self access.

- [x] Add construction/delegation tests that import the new classes.
- [x] Add AST tests for legal self access and illegal foreign-object access.
- [x] Run the tests and verify they fail because classes/gate support do not exist.

### Task 2: Implement first-class lifecycle services

**Files:**
- Modify: `backend/services/paper_delete_service.py`
- Modify: `backend/services/reextract_service.py`
- Modify: `backend/services/paper_service.py`

**Interfaces:**
- `PaperDeleteService.delete(paper_id: str, *, force: bool = False, vector_store: _VectorStoreDelete | None = None) -> None`
- `ReextractService.force_reextract(...) -> PaperStatusData`
- Cached getters for production defaults; explicit constructors for tests.

- [x] Convert delete orchestration into `PaperDeleteService`.
- [x] Convert re-extract orchestration into `ReextractService`.
- [x] Replace `PaperService` calls with thin delegation.
- [x] Update direct test call sites to instantiate the service or use its getter.
- [x] Run focused delete/re-extract/concurrency tests until green.

### Task 3: Extend and enforce the LoD architecture gate

**Files:**
- Modify: `scripts/check_pipeline_repo_lod.py`
- Modify: `scripts/check_backend.py` only if the check name/output changes.
- Test: `tests/scripts/test_paper_repo_lod.py`

**Interfaces:**
- Existing `check_pipeline_repo_lod() -> list[str]` remains stable.
- Visitor scans `_pipeline_repo` by file allowlist and `_paper_repo` by owner expression.

- [x] Add `_paper_repo` scanning: allow `self._paper_repo`, reject any other receiver.
- [x] Run AST unit tests and the repository-wide gate.
- [x] Confirm delete/reextract contain no `paper_service._paper_repo`.

### Task 4: Verification

**Files:** all changed files.

- [x] Run focused pytest suites for delete, reextract, wipe races, APIs, generation guard.
- [x] Run Ruff check/format and Pyright on changed backend modules.
- [x] Run `scripts/check_pipeline_repo_lod.py`.
- [ ] Run thread-trail audit to ensure `run_async=0/0`.
- [x] Review `git diff` for scope creep and document results.
