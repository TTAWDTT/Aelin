import { useEffect, useMemo, useState } from 'react'
import { cn } from '@/shared/utils/cn'
import type { LucideIcon } from 'lucide-react'
import { Bot, Monitor, Search, Sparkles, User } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { DeviceTab } from '@/features/settings/DeviceTab'
import { PageScaffold } from '@/shared/components/PageScaffold'

type Tab = 'profile' | 'ai' | 'device'

const SETTINGS_TABS: { key: Tab; label: string; description: string; icon: LucideIcon }[] = [
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

  const effectiveTab = filteredTabs.some((item) => item.key === tab) ? tab : filteredTabs[0]?.key
  const activeTab = effectiveTab
    ? SETTINGS_TABS.find((item) => item.key === effectiveTab) ?? SETTINGS_TABS[0]
    : null

  useEffect(() => {
    if (effectiveTab && effectiveTab !== tab) {
      setTab(effectiveTab)
    }
  }, [effectiveTab, tab])

  const renderActiveTab = (currentTab: Tab) => {
    if (currentTab === 'profile') return <ProfileTab />
    if (currentTab === 'ai') return <AIConfigTab />
    return <DeviceTab />
  }

  return (
    <PageScaffold
      title="设置"
      subtitle="配置您的偏好"
      className="overflow-hidden"
      headerActions={
        <label className="relative block w-full max-w-[420px] shrink-0">
          <Search size={18} className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索设置..."
            aria-label="搜索设置"
            className="aelin-input h-16 rounded-[22px] border-[color-mix(in_srgb,var(--color-border)_78%,white_22%)] bg-[color-mix(in_srgb,var(--color-panel)_86%,transparent)] pr-5 text-lg shadow-[0_14px_28px_-24px_rgba(27,24,16,0.24)]"
            style={{ paddingLeft: '2.9rem' }}
          />
        </label>
      }
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="border-b border-[var(--color-border)] px-5 py-5 md:border-b-0 md:border-r">
            <div className="space-y-2">
              {filteredTabs.map((item) => {
                const ItemIcon = item.icon
                const active = item.key === effectiveTab
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
              {activeTab ? (
                (() => {
                  const ActiveIcon = activeTab.icon
                  return (
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
                  )
                })()
              ) : (
                <section className="aelin-card rounded-[28px] border-[color-mix(in_srgb,var(--color-border)_84%,white_16%)] px-6 py-6 shadow-[0_24px_48px_-38px_rgba(27,24,16,0.28)]">
                  <div className="flex items-center gap-4">
                    <div className="flex h-[72px] w-[72px] items-center justify-center rounded-[24px] bg-[linear-gradient(180deg,#4b5568_0%,#364152_100%)] text-white shadow-[0_18px_36px_-22px_rgba(54,65,82,0.58)]">
                      <Sparkles size={30} />
                    </div>
                    <div>
                      <h3 className="font-heading text-[2rem] font-semibold leading-none">无匹配结果</h3>
                      <p className="mt-2 text-lg text-[var(--color-text-muted)]">尝试调整搜索关键词以查看可用设置项。</p>
                    </div>
                  </div>
                </section>
              )}

              {effectiveTab && (
                <section className="aelin-card rounded-[28px] border-[color-mix(in_srgb,var(--color-border)_84%,white_16%)] px-6 py-6 shadow-[0_26px_54px_-42px_rgba(27,24,16,0.24)]">
                  {renderActiveTab(effectiveTab)}
                </section>
              )}
            </div>
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
