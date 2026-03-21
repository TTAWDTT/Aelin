# Aelin Browser Plane Architecture

Last updated: 2026-03-07

## Goal

Aelin should evolve from "an agent with browser tools" into "a main agent that delegates browser-domain work to a dedicated Browser Plane."

The Browser Plane is the browser execution backend. It owns browser runtime state, checkpoints, and task execution. Aelin remains the top-level orchestrator.

## Target Architecture

### 1. Aelin Orchestrator

Responsibilities:

- Interpret the user request
- Decide whether work belongs to browser use, computer use, search, or memory
- Create a task for the correct plane
- Ask for user confirmation when needed
- Merge plane results back into the chat experience

Aelin should not directly own low-level browser runtime state.

### 2. Browser Plane

Responsibilities:

- Manage browser profiles, sessions, tabs, and snapshots
- Execute browser-domain actions
- Produce structured page state for the orchestrator
- Create checkpoints for login, confirmation, or blocked flows
- Resume a previously blocked browser task

The Browser Plane may internally use multiple roles or local planners, but externally it should behave like one execution backend with a stable API.

### 3. Computer Use Plane

Responsibilities:

- Manage screenshot-based desktop automation
- Execute pointer/keyboard/window actions
- Handle cross-application and non-DOM tasks

Computer Use is not the replacement for Browser Plane. It is the fallback path when browser-domain execution is insufficient.

### 4. Human Control Surface

Responsibilities:

- Show blocked browser/computer-use tasks
- Let the user confirm or continue
- Show task progress, snapshots, and recent execution state

## Integration Principle

Aelin should communicate with Browser Plane through an adapter boundary.

The adapter is not just a "launch tool." It is the integration surface used to:

- ensure the plane is ready
- create or continue work
- fetch snapshots and task state
- resolve checkpoints

## Target Browser Plane API Shape

Minimum conceptual API:

- `browser_task_create`
- `browser_task_get`
- `browser_task_resume`
- `browser_snapshot_get`
- `browser_checkpoint_list`
- `browser_checkpoint_resolve`

The current codebase is not there yet. The first step is to introduce an adapter boundary around the existing browser runtime and move new logic behind that boundary.

## Current Problems

The current browser runtime is useful but still tool-first:

- Browser work is exposed mainly as `browser_state_get` and `browser_use`
- Browser execution is coupled to thread ownership
- Confirmation follow-up does not fully share the same execution path as chat streaming
- DOM extraction exists, but not all of it survives into model-visible tool results
- Explicit `external` intent can be overridden by sticky `cdp` preference

These issues make the browser layer feel like a set of tools instead of a stable execution plane.

## Phase Plan

### Phase 1: Stabilize the Current Runtime

Implement now:

- Introduce a Browser Plane adapter around the current browser runtime
- Route browser integrations through that adapter
- Run confirmation follow-up chat in a dedicated worker context
- Preserve useful DOM targeting hints in model-visible browser state results
- Respect explicit `scope=external`
- Preserve attachment context and chat-session ownership during resumed flows

### Phase 2: Extract Browser Runtime Ownership

Planned next:

- Split browser runtime state from generic chat/tool orchestration
- Introduce browser task/checkpoint entities
- Persist checkpoints instead of storing them only in memory
- Move browser continuation from "re-run chat" toward "resume browser task"

### Phase 3: Promote Browser Plane to a Real Subsystem

Planned later:

- Separate browser plane service/runtime from the main backend process
- Add task lifecycle APIs
- Add task history, artifacts, and replay-friendly state
- Use Browser Plane as the primary path for web work and Computer Use as fallback

## Scope of This Integration Slice

This branch implements the first integration slice only:

- adapter boundary
- unified worker execution for resumed browser follow-up
- browser-state signal preservation
- scope semantics cleanup
- small UX correctness fixes around resumed chat output

It does not yet implement a full browser task backend.
