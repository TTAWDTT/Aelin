# Agent Loop Preflight Performance Notes

## Goal

Reduce non-LLM latency before `AelinAgentLoop.run()` starts, especially on the
normal chat happy path.

## Changes In This PR

- replace eager base-context construction with a lightweight summary fetch for
  chat preflight
- defer attachment prefetch until it is actually needed for fallback handling
- reuse shared memory primitives when building the heavier context bundle
- remove repeated config/API-key work in `resolve_llm_service()`
- lazily initialize and cache `openai.Client` instances
- avoid repeated `tool_definitions()` rebuilding and `context_get()` snapshots

## Expected Impact

- `resolve_service` should become effectively negligible compared to model time
- chat startup should no longer pay full `_build_cached_base_context_bundle()`
  cost just to obtain `memory_summary`
- attachment-backed fallback remains available, but no longer penalizes the
  happy path
- memory-heavy endpoints reuse aggregation outputs instead of recomputing the
  same focus/todo/brief layers multiple times
