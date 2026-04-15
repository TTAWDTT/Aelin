import type { AssistantGraph, Client } from '@langchain/langgraph-sdk'

const DEEPAGENTS_GRAPH_ID = 'agent'
const DEFAULT_ASSISTANT_LOOKUP_MAX_ATTEMPTS = 12
const DEFAULT_ASSISTANT_LOOKUP_RETRY_DELAY_MS = 500

let deepagentsAssistantIdCache: string | null = null
let deepagentsAssistantIdPromise: Promise<string> | null = null

type AssistantSearchRow = {
  assistant_id?: string
  graph_id?: string
  name?: string
}

type AssistantClientLike = Pick<Client, 'assistants' | 'threads'>

type AssistantLookupOptions = {
  maxAttempts?: number
  retryDelayMs?: number
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

async function lookupAssistantIdOnce(
  client: AssistantClientLike,
  graphId: string,
): Promise<string> {
  const items = await client.assistants.search()
  const match = (items as AssistantSearchRow[]).find((item) => {
    const itemGraphId = String(item?.graph_id || '').trim()
    const itemName = String(item?.name || '').trim()
    return itemGraphId === graphId || itemName === graphId
  })
  const assistantId = String(match?.assistant_id || '').trim()
  if (!assistantId) {
    throw new Error(`Agent Server assistant "${graphId}" not found`)
  }
  return assistantId
}

export function getDeepAgentsGraphId(): string {
  return DEEPAGENTS_GRAPH_ID
}

export function resetDeepAgentsAssistantRuntimeCache(): void {
  deepagentsAssistantIdCache = null
  deepagentsAssistantIdPromise = null
}

export async function findAssistantId(
  client: AssistantClientLike,
  graphId = DEEPAGENTS_GRAPH_ID,
  options?: AssistantLookupOptions,
): Promise<string> {
  if (deepagentsAssistantIdCache) return deepagentsAssistantIdCache
  if (deepagentsAssistantIdPromise) return deepagentsAssistantIdPromise

  const maxAttempts = Math.max(
    1,
    Number(options?.maxAttempts || DEFAULT_ASSISTANT_LOOKUP_MAX_ATTEMPTS),
  )
  const retryDelayMs = Math.max(
    0,
    Number(options?.retryDelayMs || DEFAULT_ASSISTANT_LOOKUP_RETRY_DELAY_MS),
  )

  deepagentsAssistantIdPromise = (async () => {
    let lastError: Error | null = null
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const assistantId = await lookupAssistantIdOnce(client, graphId)
        deepagentsAssistantIdCache = assistantId
        return assistantId
      } catch (error: unknown) {
        lastError = error instanceof Error ? error : new Error(String(error))
        if (attempt >= maxAttempts) break
        await sleep(retryDelayMs)
      }
    }
    throw lastError ?? new Error(`Agent Server assistant "${graphId}" not found`)
  })()
    .finally(() => {
      if (!deepagentsAssistantIdCache) deepagentsAssistantIdPromise = null
    })

  return deepagentsAssistantIdPromise
}

export async function fetchAssistantGraph(
  client: AssistantClientLike,
  assistantId: string,
): Promise<AssistantGraph> {
  return client.assistants.getGraph(assistantId, { xray: 2 })
}

export async function ensureThreadExists(
  client: AssistantClientLike,
  threadId: string,
): Promise<void> {
  const nextId = String(threadId || '').trim()
  if (!nextId) return
  await client.threads.create({
    threadId: nextId,
    ifExists: 'do_nothing',
  })
}
