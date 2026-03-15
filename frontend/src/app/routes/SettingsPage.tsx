import { useState } from 'react'
import { cn } from '@/shared/utils/cn'
import { User, Bot, Monitor } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { DeviceTab } from '@/features/settings/DeviceTab'
import { PageScaffold } from '@/shared/components/PageScaffold'

type Tab = 'profile' | 'ai' | 'device'

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')

  const tabs: { key: Tab; label: string; icon: typeof User }[] = [
    { key: 'profile', label: '个人', icon: User },
    { key: 'ai', label: 'AI 模型', icon: Bot },
    { key: 'device', label: '设备', icon: Monitor },
  ]

  return (
    <PageScaffold title="Settings" subtitle="账号、模型与设备设置">
      <div className="mx-auto w-full max-w-[1220px] space-y-4">
        <div className="flex gap-1 text-xs overflow-x-auto">
          {tabs.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={cn('flex items-center gap-1.5 px-3 py-1.5 rounded-full whitespace-nowrap transition-colors',
                tab === t.key
                  ? 'border border-[var(--color-nav-active-border)] bg-[var(--color-nav-active-bg)] text-[var(--color-nav-active-text)]'
                  : 'border border-transparent text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
              )}>
              <t.icon size={13} /> {t.label}
            </button>
          ))}
        </div>

        {tab === 'profile' && <ProfileTab />}
        {tab === 'ai' && <AIConfigTab />}
        {tab === 'device' && <DeviceTab />}
      </div>
    </PageScaffold>
  )
}
