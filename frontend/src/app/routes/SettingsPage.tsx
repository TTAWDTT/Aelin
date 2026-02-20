import { useState } from 'react'
import { cn } from '@/shared/utils/cn'
import { User, Bot, Link2, Palette, Monitor } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { AccountsTab } from '@/features/settings/AccountsTab'
import { AppearanceTab } from '@/features/settings/AppearanceTab'
import { DeviceTab } from '@/features/settings/DeviceTab'

type Tab = 'profile' | 'ai' | 'accounts' | 'appearance' | 'device'

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')

  const tabs: { key: Tab; label: string; icon: typeof User }[] = [
    { key: 'profile', label: '个人', icon: User },
    { key: 'ai', label: 'AI 模型', icon: Bot },
    { key: 'accounts', label: '数据源', icon: Link2 },
    { key: 'appearance', label: '外观', icon: Palette },
    { key: 'device', label: '设备', icon: Monitor },
  ]

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-panel)] shrink-0">
        <h1 className="text-lg font-semibold mb-2" style={{ fontFamily: 'var(--font-heading)' }}>设置</h1>
        <div className="flex gap-1 text-xs overflow-x-auto scrollbar-none">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={cn('flex items-center gap-1.5 px-3 py-1.5 rounded-lg whitespace-nowrap transition-colors',
                tab === t.key ? 'bg-[var(--color-accent)] text-[var(--color-bg)]' : 'text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              )}>
              <t.icon size={13} /> {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'profile' && <ProfileTab />}
        {tab === 'ai' && <AIConfigTab />}
        {tab === 'accounts' && <AccountsTab />}
        {tab === 'appearance' && <AppearanceTab />}
        {tab === 'device' && <DeviceTab />}
      </div>
    </div>
  )
}
