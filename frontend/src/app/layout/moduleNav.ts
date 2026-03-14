import type { LucideIcon } from 'lucide-react'
import { Focus, MessageCircle, Settings, Workflow } from 'lucide-react'

export interface ModuleNavItem {
  to: string
  icon: LucideIcon
  label: string
  mobileLabel?: string
  match?: (pathname: string) => boolean
}

export const MODULE_NAV_ITEMS: ModuleNavItem[] = [
  { to: '/', icon: MessageCircle, label: 'Chat', match: (pathname) => pathname === '/' },
  { to: '/processes', icon: Workflow, label: 'Processes', match: (pathname) => pathname.startsWith('/processes') },
  { to: '/focus', icon: Focus, label: 'Focus', match: (pathname) => pathname.startsWith('/focus') },
  { to: '/settings', icon: Settings, label: 'Settings', match: (pathname) => pathname.startsWith('/settings') },
]
