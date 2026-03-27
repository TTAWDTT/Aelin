import type { AssistantGraph, Client } from '@langchain/langgraph-sdk'

const DEEPAGENTS_GRAPH_ID = 'agent'

let deepagentsAssistantIdCache: string | null = null
let deepagentsAssistantIdPromise: Promise<string> | null = null

type AssistantSearchRow = {
  assistant_id?: string
  graph_id?: string
  name?: string
}

type AssistantClientLike = Pick<Client, 'assistants' | 'threads'>

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
): Promise<string> {
  if (deepagentsAssistantIdCache) return deepagentsAssistantIdCache
  if (deepagentsAssistantIdPromise) return deepagentsAssistantIdPromise

  deepagentsAssistantIdPromise = client.assistants
    .search()
    .then((items) => {
      const match = (items as AssistantSearchRow[]).find((item) => {
        const itemGraphId = String(item?.graph_id || '').trim()
        const itemName = String(item?.name || '').trim()
        return itemGraphId === graphId || itemName === graphId
      })
      const assistantId = String(match?.assistant_id || '').trim()
      if (!assistantId) {
        throw new Error(`Agent Server assistant "${graphId}" not found`)
      }
      deepagentsAssistantIdCache = assistantId
      return assistantId
    })
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
