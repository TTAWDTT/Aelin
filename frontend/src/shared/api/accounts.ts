import { fetchJson } from './client'
import type {
  ConnectedAccountCreate, ConnectedAccountOut, OAuthStartResponse,
  OAuthCredentialConfigOut, OAuthCredentialConfigUpdate, ForwardAccountInfo,
  SyncJobStartResponse, SyncJobStatusResponse,
} from './types'

export const accountsApi = {
  list: () => fetchJson<ConnectedAccountOut[]>('/api/v1/accounts'),

  create: (body: ConnectedAccountCreate) =>
    fetchJson<ConnectedAccountOut>('/api/v1/accounts', { method: 'POST', body: JSON.stringify(body) }),

  remove: (id: number) =>
    fetchJson<void>(`/api/v1/accounts/${id}`, { method: 'DELETE' }),

  oauthStart: (provider: string) =>
    fetchJson<OAuthStartResponse>(`/api/v1/accounts/oauth/${provider}/start`),

  oauthConfig: (provider: string) =>
    fetchJson<OAuthCredentialConfigOut>(`/api/v1/accounts/oauth/${provider}/config`),

  oauthConfigUpdate: (provider: string, body: OAuthCredentialConfigUpdate) =>
    fetchJson<OAuthCredentialConfigOut>(`/api/v1/accounts/oauth/${provider}/config`, {
      method: 'PATCH', body: JSON.stringify(body),
    }),

  forwardInfo: (id: number) =>
    fetchJson<ForwardAccountInfo>(`/api/v1/accounts/${id}/forward-info`),

  sync: (id: number) =>
    fetchJson<SyncJobStartResponse>(`/api/v1/accounts/${id}/sync`, { method: 'POST' }),

  syncStatus: (jobId: string) =>
    fetchJson<SyncJobStatusResponse>(`/api/v1/accounts/sync-jobs/${jobId}`),

  xConfig: () => fetchJson<{ configured: boolean }>('/api/v1/accounts/x/config'),

  xConfigUpdate: (body: { bearer_token: string }) =>
    fetchJson('/api/v1/accounts/x/config', { method: 'PATCH', body: JSON.stringify(body) }),

  xCookiesUpdate: (body: { cookies: string }) =>
    fetchJson('/api/v1/accounts/x/cookies', { method: 'PATCH', body: JSON.stringify(body) }),
}
