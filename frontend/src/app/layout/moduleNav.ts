import type { LucideIcon } from 'lucide-react'
import { MessageCircle, Settings } from 'lucide-react'

export interface ModuleNavItem {
  to: string
  icon: LucideIcon
  label: string
  mobileLabel?: string
  match?: (pathname: string) => boolean
}

export const MODULE_NAV_ITEMS: ModuleNavItem[] = [
  { to: '/', icon: MessageCircle, label: 'Chat', match: (pathname) => pathname === '/' },
  { to: '/settings', icon: Settings, label: 'Settings', match: (pathname) => pathname.startsWith('/settings') },
]
