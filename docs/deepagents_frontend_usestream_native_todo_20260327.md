# DeepAgents Frontend useStream Native Todo

## 1. Replace custom chat-stream state machine with official `useStream`

- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), remove local message mirror logic based on `displayMessages`.
- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), remove `sameImages` and `sameChatMessages`.
- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), remove `setSessionMessages(...)` as the runtime source of truth for active streaming messages.
- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), keep only:
  - assistant lookup
  - thread bootstrap
  - `send`
  - `stop`
  - `uploadAttachments`
  - `sendWithAttachments`
  - `captureAndSend`
- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), make official `useStream` the only source of runtime messages and values.
- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), keep submit payload limited to:
  - `messages`
  - `context.workspace`
  - `context.source`
  - `context.attachment_ids`
- [x] In [frontend/src/features/chat/hooks/useChatStream.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.ts), remove manual streaming-status reconciliation that duplicates `stream.isLoading`.

## 2. Shrink helper/runtime files to thin wrappers

- [x] In [frontend/src/features/chat/hooks/chatStreamHelpers.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamHelpers.ts), delete helpers that exist only to rebuild runtime messages from our own mirror state.
- [x] In [frontend/src/features/chat/hooks/chatStreamHelpers.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamHelpers.ts), keep only helpers still required after the migration:
  - `buildHumanStreamMessage`
  - `buildSessionHistoryMessages`
  - `trimQueryForApi`
  - `formatBytes`
- [x] Delete `streamMessagesToChatMessages` from [frontend/src/features/chat/hooks/chatStreamHelpers.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamHelpers.ts) if no longer referenced after migration.
- [x] In [frontend/src/features/chat/hooks/chatStreamRuntime.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamRuntime.ts), keep the file limited to:
  - assistant id discovery
  - assistant graph fetch
  - thread creation/bootstrap
- [x] Do not add new runtime parsing logic to [frontend/src/features/chat/hooks/chatStreamRuntime.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamRuntime.ts).

## 3. Make `ChatView` consume official stream data directly

- [x] In [frontend/src/features/chat/ChatView.tsx](/D:/Github/Aelin/frontend/src/features/chat/ChatView.tsx), stop mixing local stored messages with runtime stream messages.
- [x] In [frontend/src/features/chat/ChatView.tsx](/D:/Github/Aelin/frontend/src/features/chat/ChatView.tsx), read chat messages directly from the migrated `useChatStream` output that is backed by `useStream`.
- [x] In [frontend/src/features/chat/ChatView.tsx](/D:/Github/Aelin/frontend/src/features/chat/ChatView.tsx), keep `values` sourced directly from `stream.values`.
- [x] In [frontend/src/features/chat/ChatView.tsx](/D:/Github/Aelin/frontend/src/features/chat/ChatView.tsx), keep execution-pane auto-open behavior, but make it depend only on official execution runtime presence.

## 4. Remove graph inference and keep only official graph data

- [x] In [frontend/src/features/chat/executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts), delete any graph synthesis from stream metadata when no official assistant graph exists.
- [x] In [frontend/src/features/chat/executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts), keep graph nodes/edges sourced only from `assistantGraph`.
- [x] In [frontend/src/features/chat/executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts), keep runtime overlays limited to:
  - node visit counts
  - node running/completed state
  - node tool-call counts
  - node subagent counts
  - traversed edge counts
- [x] In [frontend/src/features/chat/executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts), when no official graph exists, return an empty graph and let the UI explicitly say so.
- [x] In [frontend/src/features/chat/executionStreamUtils.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.ts), keep tools/subagents/lanes sourced only from official runtime data:
  - `getToolCalls`
  - `getMessagesMetadata`
  - `subagents`
  - `values`

## 5. Simplify the execution pane around official runtime data

- [x] In [frontend/src/features/chat/components/ExecutionPane.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx), keep Graph tab based only on official graph + runtime overlays.
- [x] In [frontend/src/features/chat/components/ExecutionPane.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx), keep Tools tab based only on official tool-call data.
- [x] In [frontend/src/features/chat/components/ExecutionPane.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx), keep State tab based only on `stream.values`.
- [x] In [frontend/src/features/chat/components/ExecutionPane.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPane.tsx), remove any remaining dependence on legacy trace/stage semantics.
- [x] In [frontend/src/features/chat/components/ExecutionPaneParts.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPaneParts.tsx), keep `GraphBoard` as a pure renderer of provided nodes/edges.
- [x] In [frontend/src/features/chat/components/ExecutionPaneParts.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ExecutionPaneParts.tsx), do not let `GraphBoard` infer or create graph structure.
- [x] In [frontend/src/features/chat/components/ChatStatusBar.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ChatStatusBar.tsx), make status summaries depend only on official runtime execution data.

## 6. Clean up message/tool presentation to match the new runtime model

- [x] In [frontend/src/features/chat/components/ChatTimeline.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ChatTimeline.tsx), attach tool-call UI only from `getMessageToolCallMap(stream)`.
- [x] In [frontend/src/features/chat/components/ChatTimeline.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/ChatTimeline.tsx), remove assumptions based on old locally synthesized execution state.
- [x] In [frontend/src/features/chat/components/MarkdownMessage.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/MarkdownMessage.tsx), fix heading rendering so leading `#` is not displayed as plain text.
- [x] In [frontend/src/features/chat/components/MarkdownMessage.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/MarkdownMessage.tsx), ensure markdown tables render correctly.
- [x] In [frontend/src/features/chat/components/MarkdownMessage.tsx](/D:/Github/Aelin/frontend/src/features/chat/components/MarkdownMessage.tsx), reduce streaming layout jitter while content is being appended.

## 7. Reduce store/type surface area after migration

- [x] In [frontend/src/features/chat/stores/chatStore.ts](/D:/Github/Aelin/frontend/src/features/chat/stores/chatStore.ts), remove fields that duplicate runtime messages or old stream-stage state.
- [x] In [frontend/src/features/chat/stores/chatStore.ts](/D:/Github/Aelin/frontend/src/features/chat/stores/chatStore.ts), keep only:
  - session metadata
  - active session id
  - streaming/error UI flags that are still needed
- [x] In [frontend/src/features/chat/chatTypes.ts](/D:/Github/Aelin/frontend/src/features/chat/chatTypes.ts), remove legacy SSE/trace/stage types that are no longer used after the migration.
- [x] In [frontend/src/features/chat/chatHistoryStorage.ts](/D:/Github/Aelin/frontend/src/features/chat/chatHistoryStorage.ts), restrict the file to local history persistence, not active runtime truth.

## 8. Delete obsolete tests and replace them with official-runtime tests

- [x] Update [frontend/src/features/chat/hooks/useChatStream.test.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/useChatStream.test.ts) to validate the thin `useStream` wrapper rather than a custom runtime parser.
- [x] Delete assertions in [frontend/src/features/chat/hooks/chatStreamHelpers.test.ts](/D:/Github/Aelin/frontend/src/features/chat/hooks/chatStreamHelpers.test.ts) that only verify removed helper behavior.
- [x] Update [frontend/src/features/chat/executionStreamUtils.test.ts](/D:/Github/Aelin/frontend/src/features/chat/executionStreamUtils.test.ts) so it asserts:
  - official graph is used directly
  - no graph is synthesized when official graph is absent
  - tool calls come from official runtime data
  - subagents come from official runtime data

## 9. Run concrete validation after the migration

- [x] Run frontend test/build validation for the migrated stream path.
- [x] Run a real plain chat round and verify:
  - one user message appears once
  - one assistant reply appears as one message
  - streaming stays stable
- [x] Run a real web-search round and verify:
  - tool calls appear in the execution pane
  - final markdown renders correctly
- [x] Run a real attachment QA round and verify:
  - uploaded attachment is used
  - tool call appears once
  - answer renders as one assistant message
- [ ] Run a real remote-control round and verify:
  - remote control still works
  - execution pane reflects the action without relying on old trace code
  - Current blocker in this workstation run: `desktop_plugin_unreachable: [WinError 10061]`

## 10. Final cleanup target

- [x] After all steps above, ensure the chat frontend follows this structure:
  - `ChatView` = page composition
  - thin hook around official `useStream`
  - execution utilities that only read official runtime data
  - execution pane as pure presentation
- [x] Remove any remaining file, function, type, or test that still exists only to support the old self-built stream/trace model.
