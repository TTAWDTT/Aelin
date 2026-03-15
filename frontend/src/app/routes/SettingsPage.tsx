import { useEffect, useMemo, useState } from 'react'
import { cn } from '@/shared/utils/cn'
import { Bot, Monitor, Search, Sparkles, User } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { DeviceTab } from '@/features/settings/DeviceTab'
import { PageScaffold } from '@/shared/components/PageScaffold'

type Tab = 'profile' | 'ai' | 'device'

const SETTINGS_TABS: { key: Tab; label: string; description: string; icon: typeof User }[] = [
  { key: 'profile', label: '个人', description: '账号与身份信息', icon: User },
  { key: 'ai', label: 'AI 模型', description: '提供商与模型连接', icon: Bot },
  { key: 'device', label: '设备', description: '桌面能力与设备状态', icon: Monitor },
]

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')
  const [search, setSearch] = useState('')

  const filteredTabs = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return SETTINGS_TABS
    return SETTINGS_TABS.filter((item) => `${item.label} ${item.description}`.toLowerCase().includes(keyword))
  }, [search])

  useEffect(() => {
    if (!filteredTabs.some((item) => item.key === tab) && filteredTabs[0]) {
      setTab(filteredTabs[0].key)
    }
  }, [filteredTabs, tab])

  const activeTab = filteredTabs.find((item) => item.key === tab) ?? SETTINGS_TABS.find((item) => item.key === tab) ?? SETTINGS_TABS[0]
  const ActiveIcon = activeTab.icon

  const renderActiveTab = () => {
    if (tab === 'profile') return <ProfileTab />
    if (tab === 'ai') return <AIConfigTab />
    return <DeviceTab />
  }

  return (
    <PageScaffold title="设置" subtitle="配置您的偏好" className="overflow-hidden">
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-col gap-4 border-b border-[var(--color-border)] px-6 py-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-[22px] bg-[linear-gradient(180deg,#4b5568_0%,#364152_100%)] text-white shadow-[0_18px_36px_-22px_rgba(54,65,82,0.58)]">
              <Sparkles size={28} />
            </div>
            <div>
              <h2 className="font-heading text-[2rem] font-semibold leading-none text-[var(--color-text)]">设置</h2>
              <p className="mt-2 text-base text-[var(--color-text-muted)]">配置您的偏好</p>
            </div>
          </div>

          <label className="relative block w-full max-w-[420px] shrink-0">
            <Search size={18} className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索设置..."
              className="aelin-input h-16 rounded-[22px] border-[color-mix(in_srgb,var(--color-border)_78%,white_22%)] bg-[color-mix(in_srgb,var(--color-panel)_86%,transparent)] pr-5 text-lg shadow-[0_14px_28px_-24px_rgba(27,24,16,0.24)]"
              style={{ paddingLeft: '2.9rem' }}
            />
          </label>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="border-b border-[var(--color-border)] px-5 py-5 md:border-b-0 md:border-r">
            <div className="space-y-2">
              {filteredTabs.map((item) => {
                const ItemIcon = item.icon
                const active = item.key === tab
                return (
                  <button
                    key={item.key}
                    onClick={() => setTab(item.key)}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-[20px] border px-4 py-3 text-left transition-colors',
                      active
                        ? 'border-[var(--color-nav-active-border)] bg-[var(--color-nav-active-bg)] text-[var(--color-nav-active-text)] shadow-[0_18px_34px_-30px_var(--color-nav-active-shadow)]'
                        : 'border-transparent text-[var(--color-text-muted)] hover:bg-[var(--color-accent-soft)]'
                    )}
                  >
                    <ItemIcon size={18} />
                    <div className="min-w-0">
                      <div className={cn('truncate text-base font-medium', active ? 'text-[var(--color-nav-active-text)]' : 'text-[var(--color-text)]')}>
                        {item.label}
                      </div>
                      <div className="truncate text-xs text-[var(--color-text-muted)]">{item.description}</div>
                    </div>
                  </button>
                )
              })}
            </div>
          </aside>

          <div className="min-h-0 overflow-y-auto px-6 py-6">
            <div className="mx-auto w-full max-w-[1120px] space-y-6">
              <section className="aelin-card rounded-[28px] border-[color-mix(in_srgb,var(--color-border)_84%,white_16%)] px-6 py-6 shadow-[0_24px_48px_-38px_rgba(27,24,16,0.28)]">
                <div className="flex items-center gap-4">
                  <div className="flex h-[72px] w-[72px] items-center justify-center rounded-[24px] bg-[linear-gradient(180deg,#d9c59a_0%,#c3a96d_100%)] text-[var(--color-primary-soft-text)] shadow-[0_20px_34px_-24px_rgba(195,169,109,0.65)]">
                    <ActiveIcon size={30} />
                  </div>
                  <div>
                    <h3 className="font-heading text-[2rem] font-semibold leading-none">{activeTab.label}</h3>
                    <p className="mt-2 text-lg text-[var(--color-text-muted)]">{activeTab.description}</p>
                  </div>
                </div>
              </section>

              <section className="aelin-card rounded-[28px] border-[color-mix(in_srgb,var(--color-border)_84%,white_16%)] px-6 py-6 shadow-[0_26px_54px_-42px_rgba(27,24,16,0.24)]">
                {filteredTabs.length > 0 ? (
                  renderActiveTab()
                ) : (
                  <div className="py-12 text-center text-[var(--color-text-muted)]">
                    没有匹配当前搜索的设置项。
                  </div>
                )}
              </section>
            </div>
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
