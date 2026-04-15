import { fetchFormData, fetchJson } from './client'
import type {
  ArtifactResolveResponse,
  AttachmentUploadResponse,
  DeviceCapabilitiesResponse,
  DeviceScreenCaptureRequest,
  DeviceScreenCaptureResponse,
  FileMemoryContentResponse,
  FileMemorySearchResponse,
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

  fileMemorySearch: (params: { workspace?: string; query: string; top_k?: number; kinds?: string[] }) => {
    const searchParams = new URLSearchParams()
    searchParams.set('workspace', params.workspace || 'default')
    searchParams.set('query', params.query)
    if (params.top_k != null) searchParams.set('top_k', String(params.top_k))
    if (params.kinds?.length) searchParams.set('kinds', params.kinds.join(','))
    return fetchJson<FileMemorySearchResponse>(`/api/v1/attachments/file-memory/search?${searchParams.toString()}`)
  },

  fileMemoryContent: (params: { workspace?: string; path: string }) => {
    const searchParams = new URLSearchParams()
    searchParams.set('workspace', params.workspace || 'default')
    searchParams.set('path', params.path)
    return fetchJson<FileMemoryContentResponse>(`/api/v1/attachments/file-memory/content?${searchParams.toString()}`)
  },

  // Device
  deviceCapabilities: () =>
    fetchJson<DeviceCapabilitiesResponse>('/api/v1/aelin/device/capabilities'),

  resolveArtifactPath: (params: { workspace?: string; path: string }) => {
    const searchParams = new URLSearchParams()
    searchParams.set('workspace', params.workspace || 'default')
    searchParams.set('path', params.path)
    return fetchJson<ArtifactResolveResponse>(`/api/v1/aelin/artifact/resolve?${searchParams.toString()}`)
  },

  deviceScreenCapture: (body?: DeviceScreenCaptureRequest) =>
    fetchJson<DeviceScreenCaptureResponse>('/api/v1/aelin/device/screen/capture', {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),
}
