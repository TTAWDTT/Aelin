import { fetchJson } from './client'
import type { ContactOut, MessageOut, MessageDetail } from './types'

export const contactsApi = {
  list: (params?: Record<string, string>) =>
    fetchJson<ContactOut[]>(`/api/v1/contacts${params ? '?' + new URLSearchParams(params) : ''}`),

  messages: (contactId: number, params?: Record<string, string>) =>
    fetchJson<MessageOut[]>(`/api/v1/contacts/${contactId}/messages${params ? '?' + new URLSearchParams(params) : ''}`),

  markRead: (contactId: number) =>
    fetchJson<void>(`/api/v1/contacts/${contactId}/mark-read`, { method: 'POST' }),

  messageDetail: (id: number) =>
    fetchJson<MessageDetail>(`/api/v1/messages/${id}`),
}
