import { describe, expect, it } from 'vitest'
import type { AssistantGraph } from '@langchain/langgraph-sdk'
import { getExecutionRuntime, type ChatRuntimeStream } from './executionStreamUtils'

function createStream(overrides: Partial<ChatRuntimeStream> = {}): ChatRuntimeStream {
  return {
    messages: [],
    values: { messages: [] },
    isLoading: false,
    toolCalls: [],
    activeSubagents: [],
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
})
