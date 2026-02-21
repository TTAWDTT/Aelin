import { create } from 'zustand'

interface NotifStore {
  unreadCount: number
  notificationsMuted: boolean
  setUnreadCount: (n: number) => void
  setNotificationsMuted: (v: boolean) => void
}

export const useNotifStore = create<NotifStore>()((set) => ({
  unreadCount: 0,
  notificationsMuted: false,
  setUnreadCount: (n) => set({ unreadCount: n }),
  setNotificationsMuted: (v) => set({ notificationsMuted: v }),
}))
