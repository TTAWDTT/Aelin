import { useMemo, useState } from 'react'
import { Globe2, Search, Settings } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { PageScaffold } from '@/shared/components/PageScaffold'
import { useLocaleStore } from '@/shared/stores/localeStore'

type Section = 'profile' | 'ai'

export default function SettingsPage() {
  const [search, setSearch] = useState('')
  const { locale, setLocale } = useLocaleStore()
  const isZh = locale === 'zh'

  const sections = useMemo(
    () =>
      [
        {
          key: 'profile' as const,
          label: isZh ? '个人' : 'Profile',
          description: isZh ? '账号与身份信息' : 'Account & identity',
        },
        {
          key: 'ai' as const,
          label: isZh ? 'AI 模型' : 'AI Model',
          description: isZh ? '提供商与模型连接' : 'Providers & models',
        },
      ] satisfies { key: Section; label: string; description: string }[],
    [isZh]
  )

  const visibleSections = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return sections
    return sections.filter((item) => `${item.label} ${item.description}`.toLowerCase().includes(keyword))
  }, [search, sections])

  const title = isZh ? '设置' : 'Settings'
  const subtitle = isZh ? '配置您的偏好' : 'Configure your preferences'
  const searchPlaceholder = isZh ? '搜索设置...' : 'Search settings...'
  const searchAriaLabel = isZh ? '搜索设置' : 'Search settings'
  const noMatchTitle = isZh ? '无匹配结果' : 'No results'
  const noMatchHint = isZh
    ? '尝试调整搜索关键词以查看可用设置项。'
    : 'Try updating your search keywords to see available settings.'

  return (
    <PageScaffold
      title={title}
      subtitle={subtitle}
      className="overflow-hidden"
      headerTitle={
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[16px] bg-[var(--color-panel-alt)] text-[var(--color-accent)]">
            <Settings size={18} />
          </div>
          <div className="min-w-0 self-center pt-0.5">
            <h1 className="font-heading text-[1.18rem] font-semibold leading-none text-[var(--color-text)]">{title}</h1>
            <p className="mt-1 truncate text-[0.82rem] leading-none text-[var(--color-text-muted)]">{subtitle}</p>
          </div>
        </div>
      }
      headerActions={
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
          <label className="relative block w-full max-w-[420px] shrink-0">
            <Search size={18} className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchAriaLabel}
              className="aelin-input h-12 rounded-[18px] bg-[color-mix(in_srgb,var(--color-panel-alt)_40%,var(--color-panel)_60%)] pr-4 text-sm"
              style={{ paddingLeft: '2.9rem' }}
            />
          </label>
          <div className="flex shrink-0 items-center gap-2 text-[0.8rem] text-[var(--color-text-muted)]">
            <Globe2 size={14} className="text-[var(--color-text-muted)]" />
            <div className="aelin-segment">
              <button
                type="button"
                data-active={locale === 'zh'}
                onClick={() => setLocale('zh')}
              >
                中文
              </button>
              <button
                type="button"
                data-active={locale === 'en'}
                onClick={() => setLocale('en')}
              >
                English
              </button>
            </div>
          </div>
        </div>
      }
    >
      <div className="mx-auto flex w-full max-w-[980px] flex-col gap-5 pb-6">
        {!visibleSections.length ? (
          <section className="rounded-[24px] bg-[var(--color-panel)] px-5 py-6">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-[20px] bg-[var(--color-panel-alt)] text-[var(--color-accent)]">
                <Settings size={24} />
              </div>
              <div>
                <h3 className="font-heading text-[1.35rem] font-semibold leading-none">{noMatchTitle}</h3>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">{noMatchHint}</p>
              </div>
            </div>
          </section>
        ) : (
          <>
            <div className="space-y-8">
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

            <section className="mt-2 rounded-[18px] bg-[color-mix(in_srgb,var(--color-panel-alt)_40%,var(--color-panel)_60%)] px-4 py-3 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              <p>
                {isZh
                  ? '这些设置会影响 Aelin 在所有入口的行为，包括主界面对话、远程控制（飞书 / QQ）等。'
                  : 'These settings affect how Aelin behaves across all entry points, including the main chat and remote control (Feishu / QQ).'
                }
              </p>
              <p className="mt-1">
                {isZh
                  ? '后续接入的 plane 与工具，也会在这里逐步出现统一的配置入口。'
                  : 'Upcoming planes and tools will also expose their unified configuration surfaces here.'
                }
              </p>
            </section>
          </>
        )}
      </div>
    </PageScaffold>
  )
}
