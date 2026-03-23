import { fetchJson } from './client'
import type {
  AgentConfigOut, AgentConfigUpdate, AgentTestResponse,
  ModelCatalogResponse,
} from './types'

export const agentApi = {
  config: () => fetchJson<AgentConfigOut>('/api/v1/agent/config'),

  updateConfig: (body: AgentConfigUpdate) =>
    fetchJson<AgentConfigOut>('/api/v1/agent/config', { method: 'PATCH', body: JSON.stringify(body) }),

  test: () =>
    fetchJson<AgentTestResponse>('/api/v1/agent/test', { method: 'POST' }),

  catalog: () =>
    fetchJson<ModelCatalogResponse>('/api/v1/agent/catalog'),
}
