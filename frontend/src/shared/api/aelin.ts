import { fetchJson } from './client'
import type {
  AelinChatRequest, AelinChatResponse, AelinContextResponse,
  AelinNotificationResponse, AelinProactivePollResponse,
  AelinTrackConfirmRequest, AelinTrackConfirmResponse,
  AelinBrowserConfirmRequest, AelinBrowserConfirmResponse,
  AelinBrowserLoginCheckpointListResponse,
  AelinTrackingListResponse, AelinTrackingTargetUpdateRequest,
  AelinTrackingItem, AelinTrackingRunResponse,
  AelinTrackingChangeListResponse, AelinTrackingSnapshotListResponse,
  AelinTrackingFileMemorySearchResponse, AelinTrackingFileMemoryContentResponse, AelinDiaryTreeResponse,
  DeskFeedResponse, DeskTagItem, DeskTagResponse,
  AelinDeviceCapabilitiesResponse, AelinDeviceProcessResponse,
  AelinDeviceModeApplyResponse, AelinDeviceOptimizeResponse, AelinDeviceScreenCaptureResponse,
} from './types'

export const aelinApi = {
  chat: (body: AelinChatRequest) =>
    fetchJson<AelinChatResponse>('/api/v1/aelin/chat', { method: 'POST', body: JSON.stringify(body) }),

  context: (workspace = 'default') =>
    fetchJson<AelinContextResponse>(`/api/v1/aelin/context?workspace=${workspace}`),

  notifications: () =>
    fetchJson<AelinNotificationResponse>('/api/v1/aelin/notifications'),

  proactivePoll: (workspace = 'default') =>
    fetchJson<AelinProactivePollResponse>(`/api/v1/aelin/proactive/poll?workspace=${workspace}`),

  trackConfirm: (body: AelinTrackConfirmRequest) =>
    fetchJson<AelinTrackConfirmResponse>('/api/v1/aelin/track/confirm', { method: 'POST', body: JSON.stringify(body) }),

  confirmBrowserAction: (body: AelinBrowserConfirmRequest) =>
    fetchJson<AelinBrowserConfirmResponse>('/api/v1/aelin/agent/browser/confirm', { method: 'POST', body: JSON.stringify(body) }),

  browserLoginCheckpoints: (workspace = 'default', status = 'awaiting_login,continue_failed', limit = 20) =>
    fetchJson<AelinBrowserLoginCheckpointListResponse>(
      `/api/v1/aelin/agent/browser/login-checkpoints?workspace=${encodeURIComponent(workspace)}&status=${encodeURIComponent(status)}&limit=${limit}`,
    ),

  trackingList: (params?: Record<string, string>) =>
    fetchJson<AelinTrackingListResponse>(`/api/v1/aelin/tracking${params ? '?' + new URLSearchParams(params) : ''}`),

  trackingUpdate: (targetId: number, body: AelinTrackingTargetUpdateRequest) =>
    fetchJson<AelinTrackingItem>(`/api/v1/aelin/tracking/targets/${targetId}`, { method: 'PATCH', body: JSON.stringify(body) }),

  trackingRun: (targetId: number) =>
    fetchJson<AelinTrackingRunResponse>(`/api/v1/aelin/tracking/targets/${targetId}/run`, { method: 'POST' }),

  trackingChanges: (targetId: number, params?: Record<string, string>) =>
    fetchJson<AelinTrackingChangeListResponse>(`/api/v1/aelin/tracking/targets/${targetId}/changes${params ? '?' + new URLSearchParams(params) : ''}`),

  trackingAck: (targetId: number, changeIds: number[]) =>
    fetchJson<AelinTrackingRunResponse>(`/api/v1/aelin/tracking/targets/${targetId}/changes/ack`, {
      method: 'POST', body: JSON.stringify({ change_ids: changeIds }),
    }),

  trackingSnapshots: (targetId: number, params?: Record<string, string>) =>
    fetchJson<AelinTrackingSnapshotListResponse>(`/api/v1/aelin/tracking/targets/${targetId}/snapshots${params ? '?' + new URLSearchParams(params) : ''}`),

  fileMemorySearch: (params: Record<string, string>) =>
    fetchJson<AelinTrackingFileMemorySearchResponse>(`/api/v1/aelin/tracking/file-memory/search?${new URLSearchParams(params)}`),

  fileMemoryContent: (params: Record<string, string>) =>
    fetchJson<AelinTrackingFileMemoryContentResponse>(`/api/v1/aelin/tracking/file-memory/content?${new URLSearchParams(params)}`),

  fileMemoryTree: (params: Record<string, string>) =>
    fetchJson<AelinDiaryTreeResponse>(`/api/v1/aelin/tracking/file-memory/tree?${new URLSearchParams(params)}`),

  // Device
  deviceCapabilities: () =>
    fetchJson<AelinDeviceCapabilitiesResponse>('/api/v1/aelin/device/capabilities'),

  deviceProcesses: (sortBy = 'cpu') =>
    fetchJson<AelinDeviceProcessResponse>(`/api/v1/aelin/device/processes?sort_by=${sortBy}`),

  deviceProcessAction: (pid: number, action: string) =>
    fetchJson(`/api/v1/aelin/device/processes/${pid}/action`, { method: 'POST', body: JSON.stringify({ action }) }),

  deviceOptimize: () =>
    fetchJson<AelinDeviceOptimizeResponse>('/api/v1/aelin/device/processes/optimize', { method: 'POST' }),

  deviceMode: () => fetchJson<AelinDeviceModeApplyResponse>('/api/v1/aelin/device/mode'),

  deviceModeApply: (mode: string) =>
    fetchJson<AelinDeviceModeApplyResponse>('/api/v1/aelin/device/mode/apply', { method: 'POST', body: JSON.stringify({ mode }) }),

  deviceScreenCapture: () =>
    fetchJson<AelinDeviceScreenCaptureResponse>('/api/v1/aelin/device/screen/capture', { method: 'POST' }),

  deskFeed: (params?: {
    tag?: string
    source?: string
    q?: string
    limit?: number
    before_received_at?: string
    before_id?: number
  }) => {
    const qs = new URLSearchParams()
    if (params?.tag) qs.set('tag', params.tag)
    if (params?.source) qs.set('source', params.source)
    if (params?.q) qs.set('q', params.q)
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.before_received_at) qs.set('before_received_at', params.before_received_at)
    if (params?.before_id) qs.set('before_id', String(params.before_id))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return fetchJson<DeskFeedResponse>(`/api/v1/desk/feed${suffix}`)
  },

  deskTags: () => fetchJson<DeskTagResponse>('/api/v1/desk/tags'),

  deskFollowTag: (tag: string) =>
    fetchJson<DeskTagItem>('/api/v1/desk/tags/follow', {
      method: 'POST',
      body: JSON.stringify({ tag }),
    }),

  deskUnfollowTag: (tag: string) =>
    fetchJson<{ deleted: boolean; tag: string }>(`/api/v1/desk/tags/follow/${encodeURIComponent(tag)}`, {
      method: 'DELETE',
    }),
}
