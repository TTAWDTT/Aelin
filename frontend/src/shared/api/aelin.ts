import { fetchFormData, fetchJson } from './client'
import type {
  AttachmentUploadResponse,
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
    return fetchFormData<AttachmentUploadResponse>('/api/v1/attachments/upload', fd)
  },

  // Device
  deviceCapabilities: () =>
    fetchJson<DeviceCapabilitiesResponse>('/api/v1/aelin/device/capabilities'),

  deviceScreenCapture: (body?: DeviceScreenCaptureRequest) =>
    fetchJson<DeviceScreenCaptureResponse>('/api/v1/aelin/device/screen/capture', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),
}
