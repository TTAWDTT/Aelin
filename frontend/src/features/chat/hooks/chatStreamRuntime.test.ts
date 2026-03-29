import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ensureThreadExists,
  fetchAssistantGraph,
  findAssistantId,
  getDeepAgentsGraphId,
  resetDeepAgentsAssistantRuntimeCache,
} from './chatStreamRuntime'

function createClientStub() {
  return {
    assistants: {
      search: vi.fn(),
      getGraph: vi.fn(),
    },
    threads: {
      create: vi.fn(),
    },
  }
}

describe('chatStreamRuntime', () => {
  beforeEach(() => {
    resetDeepAgentsAssistantRuntimeCache()
  })

  it('resolves the agent assistant id and reuses the cache', async () => {
    const client = createClientStub()
    client.assistants.search.mockResolvedValue([
      { assistant_id: 'assistant-1', graph_id: getDeepAgentsGraphId(), name: 'agent' },
    ])

    await expect(findAssistantId(client as any)).resolves.toBe('assistant-1')
    await expect(findAssistantId(client as any)).resolves.toBe('assistant-1')

    expect(client.assistants.search).toHaveBeenCalledTimes(1)
  })

  it('requests the official graph with xray enabled', async () => {
    const client = createClientStub()
    const graph = { nodes: [{ id: 'planner', name: 'Planner' }], edges: [] }
    client.assistants.getGraph.mockResolvedValue(graph)

    await expect(fetchAssistantGraph(client as any, 'assistant-1')).resolves.toBe(graph)
    expect(client.assistants.getGraph).toHaveBeenCalledWith('assistant-1', { xray: 2 })
  })

  it('bootstraps the thread with do_nothing semantics', async () => {
    const client = createClientStub()

    await ensureThreadExists(client as any, 'thread-1')

    expect(client.threads.create).toHaveBeenCalledWith({
      threadId: 'thread-1',
      ifExists: 'do_nothing',
    })
  })
})
