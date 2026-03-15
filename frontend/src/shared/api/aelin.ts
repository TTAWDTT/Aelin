import { fetchFormData, fetchJson } from './client'
import type {
  AelinChatRequest, AelinChatResponse, AelinContextResponse,
  AelinNotificationResponse, AelinProactivePollResponse,
  AelinBrowserConfirmRequest, AelinBrowserConfirmResponse,
  AelinBrowserLoginCheckpointListResponse,
  AelinDeviceCapabilitiesResponse,
  AelinDeviceScreenCaptureRequest, AelinDeviceScreenCaptureResponse,
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

  confirmBrowserAction: (body: AelinBrowserConfirmRequest) =>
    fetchJson<AelinBrowserConfirmResponse>('/api/v1/aelin/agent/browser/confirm', { method: 'POST', body: JSON.stringify(body) }),

  browserLoginCheckpoints: (workspace = 'default', status = 'awaiting_login,continue_failed', limit = 20) =>
    fetchJson<AelinBrowserLoginCheckpointListResponse>(
      `/api/v1/aelin/agent/browser/login-checkpoints?workspace=${encodeURIComponent(workspace)}&status=${encodeURIComponent(status)}&limit=${limit}`,
    ),

  // Device
  deviceCapabilities: () =>
    fetchJson<AelinDeviceCapabilitiesResponse>('/api/v1/aelin/device/capabilities'),

  deviceScreenCapture: (body?: AelinDeviceScreenCaptureRequest) =>
    fetchJson<AelinDeviceScreenCaptureResponse>('/api/v1/aelin/device/screen/capture', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),
}
