import { fetchJson, fetchFormData } from './client'
import type { Token, UserCreate, UserOut, UserUpdate } from './types'

export const authApi = {
  register: (body: UserCreate) =>
    fetchJson<UserOut>('/api/v1/register', { method: 'POST', body: JSON.stringify(body) }),

  login: (email: string, password: string) => {
    const form = new URLSearchParams()
    form.set('username', email)
    form.set('password', password)
    return fetchJson<Token>('/api/v1/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form.toString(),
    })
  },

  me: () => fetchJson<UserOut>('/api/v1/me'),

  updateMe: (body: UserUpdate) =>
    fetchJson<UserOut>('/api/v1/me', { method: 'PATCH', body: JSON.stringify(body) }),

  uploadAvatar: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetchFormData<UserOut>('/api/v1/me/avatar', fd)
  },
}
