import { useMemo, useState } from 'react'
import { Search, Settings } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { PageScaffold } from '@/shared/components/PageScaffold'

type Section = 'profile' | 'ai'

const SETTINGS_SECTIONS: { key: Section; label: string; description: string }[] = [
  { key: 'profile', label: '个人', description: '账号与身份信息' },
  { key: 'ai', label: 'AI 模型', description: '提供商与模型连接' },
]
const SETTINGS_TITLE = '设置'
const SETTINGS_SUBTITLE = '配置您的偏好'

export default function SettingsPage() {
  const [search, setSearch] = useState('')

  const visibleSections = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return SETTINGS_SECTIONS
    return SETTINGS_SECTIONS.filter((item) => `${item.label} ${item.description}`.toLowerCase().includes(keyword))
  }, [search])

  return (
    <PageScaffold
      title={SETTINGS_TITLE}
      subtitle={SETTINGS_SUBTITLE}
      className="overflow-hidden"
      headerTitle={
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[16px] bg-[var(--color-panel-alt)] text-[var(--color-accent)]">
            <Settings size={18} />
          </div>
          <div className="min-w-0 self-center pt-0.5">
            <h1 className="font-heading text-[1.18rem] font-semibold leading-none text-[var(--color-text)]">{SETTINGS_TITLE}</h1>
            <p className="mt-1 truncate text-[0.82rem] leading-none text-[var(--color-text-muted)]">{SETTINGS_SUBTITLE}</p>
          </div>
        </div>
      }
      headerActions={
        <label className="relative block w-full max-w-[420px] shrink-0">
          <Search size={18} className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索设置..."
            aria-label="搜索设置"
            className="aelin-input h-12 rounded-[18px] bg-[color-mix(in_srgb,var(--color-panel-alt)_40%,var(--color-panel)_60%)] pr-4 text-sm"
            style={{ paddingLeft: '2.9rem' }}
          />
        </label>
      }
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1140px] flex-col gap-6">
        {!visibleSections.length ? (
          <section className="rounded-[24px] bg-[var(--color-panel)] px-5 py-6">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-[20px] bg-[var(--color-panel-alt)] text-[var(--color-accent)]">
                <Settings size={24} />
              </div>
              <div>
                <h3 className="font-heading text-[1.35rem] font-semibold leading-none">无匹配结果</h3>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">尝试调整搜索关键词以查看可用设置项。</p>
              </div>
            </div>
          </section>
        ) : (
          <div className="min-h-0 flex-1 space-y-10">
            {visibleSections.map((section) => {
              if (section.key === 'profile') {
                return (
                  <section
                    key={section.key}
                    className="space-y-6"
                  >
                    <ProfileTab />
                  </section>
                )
              }

              if (section.key === 'ai') {
                return (
                  <section
                    key={section.key}
                    className="space-y-6"
                  >
                    <AIConfigTab />
                  </section>
                )
              }

              return null
            })}

          </div>
        )}
      </div>
    </PageScaffold>
  )
}
