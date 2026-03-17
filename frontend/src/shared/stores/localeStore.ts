import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type AppLocale = 'zh' | 'en'

interface LocaleStore {
  locale: AppLocale
  setLocale: (v: AppLocale) => void
}

export const useLocaleStore = create<LocaleStore>()(
  persist(
    (set) => ({
      locale: 'zh',
      setLocale: (v) => set({ locale: v }),
    }),
    {
      name: 'aelin-locale',
      version: 1,
    }
  )
)

