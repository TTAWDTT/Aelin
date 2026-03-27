import { fetchFormData, fetchJson } from './client'
import type {
  AttachmentUploadResponse,
  BrowserConfirmRequest,
  BrowserConfirmResponse,
  BrowserLoginCheckpointListResponse,
  ContextResponse,
  DeviceCapabilitiesResponse,
  DeviceScreenCaptureRequest,
  DeviceScreenCaptureResponse,
} from './types'

export const aelinApi = {
  uploadAttachment: (file: File, params?: { workspace?: string; session_id?: string }) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('workspace', params?.workspace || 'default')
    if (params?.session_id) {
      fd.append('session_id', params.session_id)
    }
    return fetchFormData<AttachmentUploadResponse>('/api/v1/aelin/attachments/upload', fd)
  },

  context: (workspace = 'default') =>
    fetchJson<ContextResponse>(`/api/v1/aelin/context?workspace=${workspace}`),

  confirmBrowserAction: (body: BrowserConfirmRequest) =>
    fetchJson<BrowserConfirmResponse>('/api/v1/aelin/agent/browser/confirm', { method: 'POST', body: JSON.stringify(body) }),

  browserLoginCheckpoints: (workspace = 'default', status = 'awaiting_login,continue_failed', limit = 20) =>
    fetchJson<BrowserLoginCheckpointListResponse>(
      `/api/v1/aelin/agent/browser/login-checkpoints?workspace=${encodeURIComponent(workspace)}&status=${encodeURIComponent(status)}&limit=${limit}`,
    ),

  // Device
  deviceCapabilities: () =>
    fetchJson<DeviceCapabilitiesResponse>('/api/v1/aelin/device/capabilities'),

  deviceScreenCapture: (body?: DeviceScreenCaptureRequest) =>
    fetchJson<DeviceScreenCaptureResponse>('/api/v1/aelin/device/screen/capture', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),
}
