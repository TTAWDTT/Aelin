import { fetchJson } from './client'
import type {
  AgentConfigOut, AgentConfigUpdate, AgentTestResponse,
  ModelCatalogResponse, AgentTodoCreate, AgentTodoUpdate, AelinTodoItem,
} from './types'

export const agentApi = {
  config: () => fetchJson<AgentConfigOut>('/api/v1/agent/config'),

  updateConfig: (body: AgentConfigUpdate) =>
    fetchJson<AgentConfigOut>('/api/v1/agent/config', { method: 'PATCH', body: JSON.stringify(body) }),

  test: () =>
    fetchJson<AgentTestResponse>('/api/v1/agent/test', { method: 'POST' }),

  catalog: () =>
    fetchJson<ModelCatalogResponse>('/api/v1/agent/catalog'),

  memory: () => fetchJson('/api/v1/agent/memory'),

  addNote: (content: string, kind = 'note') =>
    fetchJson('/api/v1/agent/memory/notes', { method: 'POST', body: JSON.stringify({ content, kind }) }),

  deleteNote: (id: number) =>
    fetchJson<void>(`/api/v1/agent/memory/notes/${id}`, { method: 'DELETE' }),

  summarize: (text: string) =>
    fetchJson<{ summary: string }>('/api/v1/agent/summarize', { method: 'POST', body: JSON.stringify({ text }) }),

  draftReply: (text: string, tone = 'friendly') =>
    fetchJson<{ draft: string }>('/api/v1/agent/draft-reply', { method: 'POST', body: JSON.stringify({ text, tone }) }),

  dailyBrief: () => fetchJson('/api/v1/agent/daily-brief'),

  pinRecommendations: () => fetchJson('/api/v1/agent/pin-recommendations'),

  todos: () => fetchJson<AelinTodoItem[]>('/api/v1/agent/todos'),

  createTodo: (body: AgentTodoCreate) =>
    fetchJson<AelinTodoItem>('/api/v1/agent/todos', { method: 'POST', body: JSON.stringify(body) }),

  updateTodo: (id: number, body: AgentTodoUpdate) =>
    fetchJson<AelinTodoItem>(`/api/v1/agent/todos/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  deleteTodo: (id: number) =>
    fetchJson<void>(`/api/v1/agent/todos/${id}`, { method: 'DELETE' }),

  advancedSearch: (body: Record<string, unknown>) =>
    fetchJson('/api/v1/agent/search/advanced', { method: 'POST', body: JSON.stringify(body) }),
}
