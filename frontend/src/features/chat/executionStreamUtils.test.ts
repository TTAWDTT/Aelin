import { describe, expect, it } from 'vitest'
import type { AssistantGraph } from '@langchain/langgraph-sdk'
import { analyzeExecutionStream, getExecutionRuntime, type ChatRuntimeStream } from './executionStreamUtils'
import { buildMessageArtifactMap, extractArtifactsFromState } from './artifactUtils'

function createStream(overrides: Partial<ChatRuntimeStream> = {}): ChatRuntimeStream {
  return {
    messages: [],
    values: { messages: [] },
    isLoading: false,
    subagents: new Map(),
    ...overrides,
  }
}

describe('executionStreamUtils', () => {
  it('normalizes the official assistant graph without inventing nodes', () => {
    const graph: AssistantGraph = {
      nodes: [
        { id: 'planner', name: 'Planner', data: { kind: 'node' } as any },
        { id: 'tools', name: 'Tools', data: { kind: 'tool' } as any },
      ],
      edges: [
        { source: 'planner', target: 'tools', conditional: false } as any,
      ],
    } as any

    const runtime = getExecutionRuntime(createStream(), graph)

    expect(runtime.hasOfficialGraph).toBe(true)
    expect(runtime.graph.nodes.map((item) => item.id)).toEqual(['planner', 'tools'])
    expect(runtime.graph.edges).toEqual([
      expect.objectContaining({ source: 'planner', target: 'tools', active: false }),
    ])
  })

  it('does not synthesize a graph from runtime metadata when no official graph exists', () => {
    const message = { id: 'm1', content: 'hello' } as any
    const runtime = getExecutionRuntime(
      createStream({
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm1',
          streamMetadata: {
            langgraph_node: 'planner',
            langgraph_checkpoint_ns: 'root',
          },
        }),
      }),
      null,
    )

    expect(runtime.hasOfficialGraph).toBe(false)
    expect(runtime.graph.nodes).toHaveLength(0)
    expect(runtime.graph.edges).toHaveLength(0)
    expect(runtime.lanes).toEqual([
      expect.objectContaining({
        key: 'root',
        currentNode: 'planner',
        nodes: ['planner'],
      }),
    ])
  })

  it('keeps live lanes available from stream metadata alone', () => {
    const message = { id: 'm2', content: 'use tool' } as any
    const runtime = getExecutionRuntime(
      createStream({
        isLoading: true,
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm2',
          streamMetadata: {
            langgraph_node: 'research',
            langgraph_checkpoint_ns: 'branch:search',
          },
        }),
      }),
      null,
    )

    expect(runtime.lanes).toEqual([
      expect.objectContaining({
        key: 'branch:search',
        status: 'running',
        currentNode: 'research',
      }),
    ])
  })

  it('reads tool calls only from the official runtime helpers', () => {
    const message = { id: 'm3', content: 'tool answer' } as any
    const runtime = getExecutionRuntime(
      createStream({
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm3',
          streamMetadata: {
            langgraph_node: 'tools',
            langgraph_checkpoint_ns: 'root',
          },
        }),
        getToolCalls: () => [
          {
            id: 'call-1',
            status: 'completed',
            call: {
              id: 'call-1',
              name: 'web_search',
              args: { query: 'github trending' },
            },
            result: { answer: 'done' },
          },
        ],
      }),
      null,
    )

    expect(runtime.tools).toEqual([
      expect.objectContaining({
        key: 'call-1',
        name: 'web_search',
        state: 'completed',
      }),
    ])
  })

  it('returns message tool-call maps from the same analysis pass', () => {
    const message = { id: 'm3', content: 'tool answer' } as any
    const analysis = analyzeExecutionStream(
      createStream({
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm3',
          streamMetadata: {
            langgraph_node: 'tools',
            langgraph_checkpoint_ns: 'root',
          },
        }),
        getToolCalls: () => [
          {
            id: 'call-1',
            status: 'completed',
            call: {
              id: 'call-1',
              name: 'web_search',
              args: { query: 'github trending' },
            },
            result: { answer: 'done' },
          },
        ],
      }),
      null,
    )

    expect(analysis.toolCallsByMessage.get('m3')).toEqual([
      expect.objectContaining({ key: 'call-1', name: 'web_search' }),
    ])
    expect(analysis.runtime.tools).toHaveLength(1)
  })

  it('reads subagents only from the official runtime map', () => {
    const runtime = getExecutionRuntime(
      createStream({
        subagents: new Map([
          ['sa-1', {
            id: 'sa-1',
            status: 'running',
            depth: 1,
            namespace: ['root', 'research'],
            toolCall: {
              id: 'sa-1',
              args: { subagent_type: 'researcher' },
            },
            messages: [{ content: 'looking things up' }],
          }],
        ]),
      }),
      null,
    )

    expect(runtime.subagents).toEqual([
      expect.objectContaining({
        key: 'sa-1',
        name: 'researcher',
        status: 'running',
      }),
    ])
  })

  it('builds live summary from running tools and todos', () => {
    const message = { id: 'm4', content: 'working' } as any
    const runtime = getExecutionRuntime(
      createStream({
        isLoading: true,
        values: {
          messages: [],
          todos: [
            { id: 'todo-1', title: 'Collect references', done: false },
          ],
        },
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm4',
          streamMetadata: {
            langgraph_node: 'research',
            langgraph_checkpoint_ns: 'root',
          },
        }),
        getToolCalls: () => [
          {
            id: 'call-1',
            status: 'running',
            call: {
              id: 'call-1',
              name: 'web_search',
              args: { query: 'tongji sakura festival' },
            },
            result: null,
          },
        ],
      }),
      null,
    )

    expect(runtime.live.currentNode).toBe('research')
    expect(runtime.live.runningTools).toEqual([
      expect.objectContaining({ key: 'call-1', name: 'web_search', state: 'running' }),
    ])
    expect(runtime.todos).toEqual([
      expect.objectContaining({ key: 'todo-1', title: 'Collect references', status: 'pending' }),
    ])
  })

  it('marks the latest pending tool call as preparing while args are still streaming', () => {
    const message = { id: 'm5', content: 'working', type: 'ai' } as any
    const runtime = getExecutionRuntime(
      createStream({
        isLoading: true,
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm5',
          streamMetadata: {
            langgraph_node: 'tools',
            langgraph_checkpoint_ns: 'root',
          },
        }),
        getToolCalls: () => [
          {
            id: 'call-prepare',
            status: 'pending',
            call: {
              id: 'call-prepare',
              name: 'write_file',
              args: { file_path: '/poster.html', content: '<html>' },
            },
            result: null,
          },
        ],
      }),
      null,
    )

    expect(runtime.tools).toEqual([
      expect.objectContaining({
        key: 'call-prepare',
        name: 'write_file',
        state: 'preparing',
      }),
    ])
    expect(runtime.live.runningTools).toEqual([
      expect.objectContaining({ key: 'call-prepare', state: 'preparing' }),
    ])
  })

  it('extracts state-backed artifacts and maps them to write_file tool calls', () => {
    const values = {
      messages: [],
      files: {
        '/poster.html': {
          content: ['<html><body>Poster</body></html>'],
          created_at: '2026-03-29T00:00:00Z',
          modified_at: '2026-03-29T00:00:01Z',
        },
      },
    }
    const artifactsByPath = extractArtifactsFromState(values)
    const artifactMap = buildMessageArtifactMap(
      new Map([
        ['m1', [{
          key: 'call-1',
          name: 'write_file',
          state: 'completed',
          args: '{"file_path":"/poster.html"}',
          result: '',
          filePath: '/poster.html',
          artifacts: [],
        }]],
      ]),
      artifactsByPath,
    )

    expect(artifactsByPath.get('/poster.html')).toEqual(
      expect.objectContaining({
        name: 'poster.html',
        mimeType: 'text/html',
        previewKind: 'html',
      }),
    )
    expect(artifactMap.get('m1')).toEqual([
      expect.objectContaining({
        path: '/poster.html',
        name: 'poster.html',
      }),
    ])
  })

  it('preserves execute-produced artifacts on tool calls', () => {
    const message = { id: 'm8', content: 'done' } as any
    const runtime = getExecutionRuntime(
      createStream({
        messages: [message],
        getMessagesMetadata: () => ({
          messageId: 'm8',
          streamMetadata: {
            langgraph_node: 'tools',
            langgraph_checkpoint_ns: 'root',
          },
        }),
        getToolCalls: () => [
          {
            id: 'call-execute',
            status: 'completed',
            call: {
              id: 'call-execute',
              name: 'execute',
              args: { command: 'python build.py' },
            },
            result: {
              artifact_count: 1,
              artifacts: [
                {
                  path: 'D:/Github/Aelin/output/poster.png',
                  relative_path: 'output/poster.png',
                  name: 'poster.png',
                  mime_type: 'image/png',
                  size_bytes: 16,
                  preview_kind: 'image-data-url',
                  content: 'data:image/png;base64,ZmFrZQ==',
                },
              ],
            },
          },
        ],
      }),
      null,
    )

    expect(runtime.tools).toEqual([
      expect.objectContaining({
        key: 'call-execute',
        name: 'execute',
        artifacts: [
          expect.objectContaining({
            path: 'D:/Github/Aelin/output/poster.png',
            previewKind: 'image-data-url',
          }),
        ],
      }),
    ])
  })

  it('marks earlier pending tool calls as running once execution has moved past arg generation', () => {
    const messages = [
      { id: 'm6', content: 'tool call', type: 'ai' } as any,
      { id: 'm7', content: 'next ai chunk', type: 'ai' } as any,
    ]
    const runtime = getExecutionRuntime(
      createStream({
        isLoading: true,
        messages,
        getMessagesMetadata: (_message, index) => ({
          messageId: index === 0 ? 'm6' : 'm7',
          streamMetadata: {
            langgraph_node: 'tools',
            langgraph_checkpoint_ns: 'root',
          },
        }),
        getToolCalls: (message) => (
          (message as any).id === 'm6'
            ? [
                {
                  id: 'call-running',
                  status: 'pending',
                  call: {
                    id: 'call-running',
                    name: 'web_search',
                    args: { query: 'tongji sakura festival' },
                  },
                  result: null,
                },
              ]
            : []
        ),
      }),
      null,
    )

    expect(runtime.tools).toEqual([
      expect.objectContaining({
        key: 'call-running',
        name: 'web_search',
        state: 'running',
      }),
    ])
  })
})
