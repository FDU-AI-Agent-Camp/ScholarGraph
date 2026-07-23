# Async Thread-Trail Audit

- label: `candidate`
- commit: `ac286f9aa1ad1748922bf7d776a4f63a8315f38c`
- candidate_async: `True`
- passed: **True**
- expected: loop-affinity sites share the main event-loop thread; GraphStore.save runs off-loop via to_thread; no run_async / publish_sync

## Thread identity summary

- main loop thread id: `65220`
- loop-affinity unified ids: `[65220]`
- loop-affinity all on main: `True`
- GraphStore.save left main: `True`
- run_async callers/executors: 0/0
- publish_sync count: `0`
- cross-thread hop detected: `False`

## Chronological trail

| seq | site | thread_id | thread_name | main | bridge | to_thread |
|---|---|---|---|---|---|---|
| 1 | `finalize.entry` | 65220 | MainThread | True | False | False |
| 2 | `graph_persistence.save.entry` | 65220 | MainThread | True | False | False |
| 3 | `graph.GraphStore.save` | 28696 | asyncio_0 | False | False | True |
| 4 | `complete_paper_pipeline.entry` | 65220 | MainThread | True | False | False |
| 5 | `repo.PaperRepository.update_classification` | 65220 | MainThread | True | False | False |
| 6 | `repo.PaperRepository.update_paths` | 65220 | MainThread | True | False | False |
| 7 | `repo.PaperRepository.update_graph_version` | 65220 | MainThread | True | False | False |
| 8 | `repo.PipelineRepository.save_status` | 65220 | MainThread | True | False | False |
| 9 | `event_bus.publish` | 65220 | MainThread | True | False | False |
| 10 | `repo.PipelineRepository.clear_preview_graph` | 65220 | MainThread | True | False | False |
