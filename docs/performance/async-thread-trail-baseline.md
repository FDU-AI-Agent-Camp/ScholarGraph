# Async Thread-Trail Audit

- label: `baseline`
- commit: `e847cc008e38dedc789858e0266b88e69d7cb3dc`
- candidate_async: `False`
- passed: **True**
- expected: run_async (or publish_sync) produces a main-loop → bridge-thread hop; GraphStore.save typically remains on the caller thread

## Thread identity summary

- main loop thread id: `67268`
- loop-affinity unified ids: `[64412, 67268]`
- loop-affinity all on main: `False`
- GraphStore.save left main: `False`
- run_async callers/executors: 16/16
- publish_sync count: `1`
- cross-thread hop detected: `True`

## Chronological trail

| seq | site | thread_id | thread_name | main | bridge | to_thread |
|---|---|---|---|---|---|---|
| 1 | `finalize.entry` | 67268 | MainThread | True | False | False |
| 2 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 3 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 4 | `graph_persistence.save.entry` | 67268 | MainThread | True | False | False |
| 5 | `graph.GraphStore.save` | 67268 | MainThread | True | False | False |
| 6 | `complete_paper_pipeline.entry` | 67268 | MainThread | True | False | False |
| 7 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 8 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 9 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 10 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 11 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 12 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 13 | `repo.PaperRepository.update_classification` | 64412 | async-bridge-loop | False | True | False |
| 14 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 15 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 16 | `repo.PaperRepository.update_paths` | 64412 | async-bridge-loop | False | True | False |
| 17 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 18 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 19 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 20 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 21 | `repo.PaperRepository.update_graph_version` | 64412 | async-bridge-loop | False | True | False |
| 22 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 23 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 24 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 25 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 26 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 27 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 28 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 29 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 30 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 31 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 32 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 33 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 34 | `repo.PipelineRepository.save_status` | 64412 | async-bridge-loop | False | True | False |
| 35 | `event_bus.publish_sync` | 67268 | MainThread | True | False | False |
| 36 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 37 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 38 | `event_bus.publish` | 64412 | async-bridge-loop | False | True | False |
| 39 | `run_async.caller` | 67268 | MainThread | True | False | False |
| 40 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
| 41 | `repo.PipelineRepository.clear_preview_graph` | 64412 | async-bridge-loop | False | True | False |
| 42 | `run_async.caller` | 71168 | asyncio_0 | False | False | True |
| 43 | `run_async.executor` | 64412 | async-bridge-loop | False | True | False |
