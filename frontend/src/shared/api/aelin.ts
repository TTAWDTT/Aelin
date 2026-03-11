import { fetchFormData, fetchJson } from './client'
import type {
  AelinChatRequest, AelinChatResponse, AelinContextResponse,
  AelinNotificationResponse, AelinProactivePollResponse,
  AelinTrackConfirmRequest, AelinTrackConfirmResponse,
  AelinBrowserConfirmRequest, AelinBrowserConfirmResponse,
  AelinBrowserLoginCheckpointListResponse,
  AelinTrackingFileMemoryContentResponse, AelinDiaryTreeResponse,
  DeskFeedResponse, DeskTagItem, DeskTagResponse,
  AelinDeviceCapabilitiesResponse, AelinDeviceProcessResponse,
  AelinDeviceModeApplyResponse, AelinDeviceOptimizeResponse, AelinDeviceScreenCaptureRequest, AelinDeviceScreenCaptureResponse,
  AelinAttachmentUploadResponse,
} from './types'

export const aelinApi = {
  chat: (body: AelinChatRequest) =>
    fetchJson<AelinChatResponse>('/api/v1/aelin/chat', { method: 'POST', body: JSON.stringify(body) }),

  uploadAttachment: (file: File, params?: { workspace?: string; session_id?: string }) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('workspace', params?.workspace || 'default')
    if (params?.session_id) {
      fd.append('session_id', params.session_id)
    }
    return fetchFormData<AelinAttachmentUploadResponse>('/api/v1/aelin/attachments/upload', fd)
  },

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

  deviceScreenCapture: (body?: AelinDeviceScreenCaptureRequest) =>
    fetchJson<AelinDeviceScreenCaptureResponse>('/api/v1/aelin/device/screen/capture', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),

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
