# RAG Vector Store Branch Plan

## Purpose

This note explains our specific V2 job: `feature/backend/rag-vector-store`.
It is meant for review by a more experienced engineer before implementation.

Our branch is the foundation for the later RAG work. We are not building the final
QA answer generator, the Patrol enhancement, or the database persistence layer.
Our job is to make each processed paper searchable by meaning.

In plain language:

> After ScholarGraph finishes reading a paper, we prepare searchable records from
> the paper text, graph nodes, and graph edges, then store them in ChromaDB so
> later modules can retrieve the right evidence.

## Scope

Our branch should implement RAG Phase 1 from `docs/v2/rag-requirements.md`.

Expected files:

```text
backend/rag/
|-- __init__.py
|-- models.py
|-- chunking.py
|-- indexing.py
|-- vector_store.py
`-- handlers.py

tests/rag/
|-- test_chunking.py
|-- test_indexing.py
`-- test_vector_store.py
```

Expected dependency change:

```text
pyproject.toml: add chromadb
```

## Non-scope

We should avoid these areas unless the team lead explicitly asks us to handle them:

- Do not implement the persistence-core database migration.
- Do not directly modify `backend/services/pipeline_completion_service.py`.
- Do not implement final QA generation or prompt streaming.
- Do not implement HybridRetriever routing logic, except for data models needed by our branch.
- Do not implement new Patrol modes.
- Do not change frontend UI.

## Inputs and Outputs

### Inputs

Our indexing code needs:

- `paper_id`
- `full_text`
- `UnifiedPaperGraph`
- embedding client from `backend/llm/embeddings.py`

Eventually, these should arrive through a `PipelineFinalized` event created by
the persistence/core branch. Before that event exists, we can keep the indexing
function callable directly in tests.

### Outputs

We provide a `VectorStore` API:

```python
await store.index_chunks(chunks)
await store.index_entities(entities)
await store.index_relations(relations)
await store.replace_paper_index(
    paper_id,
    chunks=chunks,
    entities=entities,
    relations=relations,
)

await store.query_chunks(query_text, paper_id=paper_id, top_k=5)
await store.query_entities(query_text, paper_id=paper_id, top_k=5)
await store.query_relations(query_text, paper_id=paper_id, top_k=5)

await store.delete_by_paper(paper_id)
await store.exists(paper_id)
```

Downstream teammates should be able to use those methods without knowing how
ChromaDB is configured internally.

## Core Strategy

We will create three independent vector collections:

| Collection | Stores | Why |
|---|---|---|
| `paper_chunks` | Original paper text chunks | Supports detailed evidence retrieval |
| `paper_entities` | Graph nodes as searchable text | Supports entity-level semantic search |
| `paper_relations` | Graph edges as searchable text | Supports relation/evidence search |

Keeping them separate avoids mixing incomparable distances. A chunk, an entity,
and a relation are different kinds of evidence, so later retrieval should get
Top-K results from each collection separately.

Every record must include `paper_id` metadata. Single-paper QA must filter by
`paper_id` to avoid retrieving evidence from the wrong paper.

## Chunking Strategy

The goal is not to cut text randomly. The goal is to preserve academic meaning.

Recommended pipeline:

1. Normalize the text lightly.
2. Detect section headings.
3. Split by sections first.
4. Split long sections into smaller chunks.
5. Use overlap between neighboring chunks.
6. Merge or skip tiny useless chunks.
7. Preserve metadata for citation and debugging.

### Section-aware first

We should detect headings such as:

- Abstract
- Introduction
- Related Work
- Background
- Methods
- Methodology
- Experiments
- Results
- Discussion
- Conclusion
- Appendix
- References

This keeps a Methods paragraph from being mixed with Results or References.

### Fixed window second

If a section is too long, split it into smaller windows.

Initial default:

```text
chunk_size_chars = 1500
chunk_overlap_ratio = 0.20
min_chunk_chars = 200
```

The V2 doc mentions 512 tokens or around 1500 chars. Since the current project
does not have a dedicated tokenizer dependency, character-based splitting is a
simple and testable first version. We can name the setting clearly so it can be
replaced by token-aware splitting later.

### Overlap

Use about 20 percent overlap. This prevents a claim and its evidence from being
split across two chunks with no shared context.

Example:

```text
chunk 000: chars 0-1500
chunk 001: chars 1200-2700
chunk 002: chars 2400-3900
```

### References handling

References can pollute semantic search. My suggested first version:

- Detect `References` as a section.
- Keep it as metadata if we need traceability.
- Do not index references by default, or allow `include_references=False`.

This should be confirmed with the reviewer.

## Data Models

### PaperChunk

```python
class PaperChunk(BaseModel):
    chunk_id: str
    paper_id: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None
    chunk_index: int
    source: str
    char_start: int
    char_end: int
```

`chunk_id` should be deterministic and namespaced:

```text
{paper_id}:chunk:{chunk_index}
```

### PaperEntity

```python
class PaperEntity(BaseModel):
    entity_id: str
    paper_id: str
    label: str
    node_type: str
    description: str
    source_span: str | None
```

The embedding text should combine:

```text
label + node_type + rationale/source_span if available
```

### PaperRelation

```python
class PaperRelation(BaseModel):
    relation_id: str
    paper_id: str
    source_id: str
    target_id: str
    relation_type: str
    description: str
    rationale: str | None
    source_span: str | None
```

The embedding text should include:

```text
source_label --[relation_type]--> target_label
rationale
source_span
```

## Indexing Strategy

`backend/rag/indexing.py` should convert a graph into searchable records.

Functions:

```python
def graph_to_entities(paper_id: str, graph: UnifiedPaperGraph) -> list[PaperEntity]:
    ...

def graph_to_relations(paper_id: str, graph: UnifiedPaperGraph) -> list[PaperRelation]:
    ...
```

Important rules:

- Do not discard graph IDs.
- Preserve raw node IDs as `entity_id`.
- Preserve raw edge IDs as `relation_id`.
- Use namespaced Chroma IDs for storage:
  - `{paper_id}:entity:{graph_node_id}`
  - `{paper_id}:relation:{graph_edge_id}`

This keeps citations and later retrieval explainable.

## VectorStore Strategy

`backend/rag/vector_store.py` should hide ChromaDB details behind a small API.

Implementation expectations:

- ChromaDB local persistent path: `./data/chroma`
- One collection per evidence type.
- Use `EmbeddingClient.embed_texts`.
- Batch embedding and writes.
- Store text in documents.
- Store structured fields in metadata.
- Clean metadata before passing it to ChromaDB: omit `None` values and avoid raw nested objects.
- Use deterministic IDs so re-indexing is idempotent.
- Use namespaced IDs so graph node/edge IDs cannot collide across papers.
- `delete_by_paper` should remove all chunks, entities, and relations for one paper.
- `replace_paper_index` should be the main re-indexing operation:
  1. delete current paper evidence
  2. upsert chunks, entities, and relations
- Query methods must support `paper_id` filtering.
- `exists(paper_id)` should mean any indexed evidence exists, not all three evidence types.
- Embeddings should be produced explicitly through `EmbeddingClient.embed_texts` and passed into ChromaDB.

For tests, we should allow dependency injection:

- temporary Chroma path
- fake embedding client

This keeps tests fast and avoids real network/API calls.

## Event Integration Strategy

The V2 plan says the persistence/core branch should publish a `PipelineFinalized`
event after a paper finishes processing.

Our branch should provide a handler like:

```python
async def index_paper_for_rag(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
    vector_store: VectorStore | None = None,
) -> None:
    ...
```

Then `handlers.py` can later connect that function to the event bus.

Until the event bus exists, this function remains directly testable and does not
block our branch.

Failure policy:

- RAG indexing failure should not make the paper pipeline fail.
- Log the exception.
- Later, when the warning API is ready, add `rag_index_failed` to extract warnings.

## Test Strategy

### Chunking tests

Cover:

- Section heading detection.
- Long section split into multiple chunks.
- Overlap behavior.
- Tiny chunk merge or skip behavior.
- References skip behavior, if accepted.
- Deterministic chunk IDs and character offsets.

### Indexing tests

Cover:

- Graph nodes become `PaperEntity`.
- Graph edges become `PaperRelation`.
- Missing rationale/source_span still produces useful descriptions.
- IDs are preserved.
- Labels and relation text are included in descriptions.

### Vector store tests

Use a fake embedding client. The fake can return deterministic small vectors.

Cover:

- Index chunks/entities/relations.
- Query each collection.
- `paper_id` filter prevents cross-paper retrieval.
- `delete_by_paper` deletes all three evidence types for one paper.
- `exists(paper_id)` returns true only after data is indexed.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| ChromaDB dependency may be heavy or version-sensitive | Keep wrapper thin and test with temp path |
| Event bus not ready | Implement direct `index_paper_for_rag` first |
| Real embedding API not available in tests | Use fake embedding client |
| Section detection imperfect | Start with rules and preserve fallback single-section chunking |
| References pollute retrieval | Skip or flag references by default |
| Cross-paper retrieval contamination | Always store and filter by `paper_id` |

## Open Questions for Senior Review

1. Should references be skipped entirely, or indexed with `section="references"` and filtered later?
2. Is character-based chunking acceptable for V2 Phase 1, or should we add token-aware splitting now?
3. Should we keep page numbers nullable for now, given `full_text` may not preserve page boundaries?
4. Should `VectorStore` expose async methods even though ChromaDB calls may be sync internally?
5. Should we define a formal interface/protocol for the embedding client to make tests cleaner?
6. What is the preferred strategy for ChromaDB collection reset in tests?
7. Should `exists(paper_id)` require all three collections to contain data, or any one collection?

## Proposed Implementation Order

1. Add `backend/rag/models.py`.
2. Implement and test `chunking.py`.
3. Implement and test `indexing.py`.
4. Add `chromadb` dependency.
5. Implement `vector_store.py` with fake-embedding-friendly injection.
6. Add `handlers.py` with direct indexing function.
7. Update `uv.lock`.
8. Run focused tests.
9. Run required static checks before PR.

## Definition of Done

Our branch is done when:

- `backend/rag/` exists with models, chunking, indexing, vector store, and handler entry point.
- Text chunks, graph entities, and graph relations can be indexed.
- Each evidence type can be queried by semantic search.
- Searches can be hard-filtered by `paper_id`.
- A paper can be re-indexed by deleting old records and inserting new ones.
- Unit tests cover chunking, indexing, vector store behavior, and paper isolation.
- We do not directly modify `pipeline_completion_service.py`.
- `ruff`, formatting check, pyright, and focused tests pass before PR.
