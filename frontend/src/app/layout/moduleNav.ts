import type { LucideIcon } from 'lucide-react'
import { BookOpenText, Focus, MessageCircle, Radar, Settings, Workflow } from 'lucide-react'

export interface ModuleNavItem {
  to: string
  icon: LucideIcon
  label: string
  mobileLabel?: string
  match?: (pathname: string) => boolean
}

export const MODULE_NAV_ITEMS: ModuleNavItem[] = [
  { to: '/', icon: MessageCircle, label: 'Chat', match: (pathname) => pathname === '/' },
  { to: '/desk', icon: Radar, label: 'Desk', match: (pathname) => pathname.startsWith('/desk') || pathname.startsWith('/tracking') },
  { to: '/processes', icon: Workflow, label: 'Processes', match: (pathname) => pathname.startsWith('/processes') },
  { to: '/diary', icon: BookOpenText, label: 'Aelinの日记', mobileLabel: '日记', match: (pathname) => pathname.startsWith('/diary') },
  { to: '/focus', icon: Focus, label: 'Focus', match: (pathname) => pathname.startsWith('/focus') },
  { to: '/settings', icon: Settings, label: 'Settings', match: (pathname) => pathname.startsWith('/settings') },
]
