import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

  afterEach(() => {
    vi.useRealTimers()
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

  it('retries assistant discovery until the agent server becomes ready', async () => {
    vi.useFakeTimers()
    const client = createClientStub()
    client.assistants.search
      .mockRejectedValueOnce(new Error('connect ECONNREFUSED 127.0.0.1:8000'))
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { assistant_id: 'assistant-2', graph_id: getDeepAgentsGraphId(), name: 'agent' },
      ])

    const pending = findAssistantId(client as any)

    await vi.advanceTimersByTimeAsync(1000)

    await expect(pending).resolves.toBe('assistant-2')
    expect(client.assistants.search).toHaveBeenCalledTimes(3)
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
