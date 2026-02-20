import { create } from 'zustand'

interface NotifStore {
  unreadCount: number
  setUnreadCount: (n: number) => void
}

export const useNotifStore = create<NotifStore>()((set) => ({
  unreadCount: 0,
  setUnreadCount: (n) => set({ unreadCount: n }),
}))
