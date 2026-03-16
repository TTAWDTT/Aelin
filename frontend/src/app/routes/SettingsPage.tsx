import { useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Search, Settings, User } from 'lucide-react'
import { ProfileTab } from '@/features/settings/ProfileTab'
import { AIConfigTab } from '@/features/settings/AIConfigTab'
import { DeviceTab } from '@/features/settings/DeviceTab'
import { PageScaffold } from '@/shared/components/PageScaffold'

type Section = 'profile' | 'ai' | 'device'

const SETTINGS_SECTIONS: { key: Section; label: string; description: string }[] = [
  { key: 'profile', label: '个人', description: '账号与身份信息' },
  { key: 'ai', label: 'AI 模型', description: '提供商与模型连接' },
  { key: 'device', label: '设备', description: '桌面能力与设备状态' },
]
const SETTINGS_TITLE = '设置'
const SETTINGS_SUBTITLE = '配置您的偏好'

export default function SettingsPage() {
  const [search, setSearch] = useState('')
  const hasInitializedMounts = useRef(false)

  const visibleSections = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    if (!keyword) return SETTINGS_SECTIONS
    return SETTINGS_SECTIONS.filter((item) => `${item.label} ${item.description}`.toLowerCase().includes(keyword))
  }, [search])

  const sectionKeys = new Set(visibleSections.map((item) => item.key))
  const showProfile = sectionKeys.has('profile')
  const showAI = sectionKeys.has('ai')
  const showDevice = sectionKeys.has('device')
  const [mountedSections, setMountedSections] = useState<Record<Section, boolean>>({
    profile: true,
    ai: false,
    device: false,
  })

  useEffect(() => {
    setMountedSections((prev) => ({
      profile: prev.profile || showProfile,
      ai: prev.ai || showAI,
      device: prev.device || showDevice,
    }))

    if (search.trim() || hasInitializedMounts.current) {
      return
    }

    hasInitializedMounts.current = true

    const aiTimer = showAI
      ? window.setTimeout(() => {
          setMountedSections((prev) => ({ ...prev, ai: true }))
        }, 0)
      : null
    const deviceTimer = showDevice
      ? window.setTimeout(() => {
          setMountedSections((prev) => ({ ...prev, device: true }))
        }, 120)
      : null

    return () => {
      if (aiTimer !== null) window.clearTimeout(aiTimer)
      if (deviceTimer !== null) window.clearTimeout(deviceTimer)
    }
  }, [search, showProfile, showAI, showDevice])

  return (
    <PageScaffold
      title={SETTINGS_TITLE}
      subtitle={SETTINGS_SUBTITLE}
      className="overflow-hidden"
      headerTitle={
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[16px] bg-[linear-gradient(180deg,#dfc98f_0%,#c8ab69_100%)] text-[var(--color-primary-soft-text)] shadow-[0_16px_28px_-24px_rgba(200,171,105,0.55)]">
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
            className="aelin-input h-12 rounded-[18px] border-[color-mix(in_srgb,var(--color-border)_78%,white_22%)] bg-[color-mix(in_srgb,var(--color-panel)_86%,transparent)] pr-4 text-sm shadow-[0_14px_28px_-24px_rgba(27,24,16,0.24)]"
            style={{ paddingLeft: '2.9rem' }}
          />
        </label>
      }
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1140px] flex-col gap-6">
        {!visibleSections.length ? (
          <section className="aelin-card rounded-[24px] border-[color-mix(in_srgb,var(--color-border)_84%,white_16%)] px-5 py-6 shadow-[0_22px_42px_-38px_rgba(27,24,16,0.28)]">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-[20px] bg-[linear-gradient(180deg,#dfc98f_0%,#c8ab69_100%)] text-[var(--color-primary-soft-text)] shadow-[0_18px_36px_-22px_rgba(200,171,105,0.5)]">
                <Settings size={24} />
              </div>
              <div>
                <h3 className="font-heading text-[1.35rem] font-semibold leading-none">无匹配结果</h3>
                <p className="mt-2 text-sm text-[var(--color-text-muted)]">尝试调整搜索关键词以查看可用设置项。</p>
              </div>
            </div>
          </section>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_220px]">
            <div className="space-y-7">
              {mountedSections.profile && (
                <section className={`relative px-1 pb-7 ${showProfile ? '' : 'hidden'}`}>
                  <div className="mb-4 flex items-start gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-[16px] bg-[var(--color-nav-active-bg)] text-[var(--color-nav-active-text)]">
                      <User size={18} />
                    </div>
                    <div>
                      <h3 className="font-heading text-[1.15rem] font-semibold leading-none">个人</h3>
                      <p className="mt-1 text-xs text-[var(--color-text-muted)]">账号与身份信息</p>
                    </div>
                  </div>
                  <ProfileTab />
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-[linear-gradient(90deg,transparent_0%,color-mix(in_srgb,var(--color-border)_28%,transparent)_12%,color-mix(in_srgb,var(--color-border)_72%,transparent)_50%,color-mix(in_srgb,var(--color-border)_28%,transparent)_88%,transparent_100%)]" />
                </section>
              )}

              {mountedSections.ai && (
                <section className={`px-1 ${showAI ? '' : 'hidden'}`}>
                  <div className="mb-4 flex items-start gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-[16px] bg-[var(--color-nav-active-bg)] text-[var(--color-nav-active-text)]">
                      <Bot size={18} />
                    </div>
                    <div>
                      <h3 className="font-heading text-[1.15rem] font-semibold leading-none">AI 模型</h3>
                      <p className="mt-1 text-xs text-[var(--color-text-muted)]">提供商与模型连接</p>
                    </div>
                  </div>
                  {mountedSections.ai ? (
                    <AIConfigTab />
                  ) : (
                    <div className="text-sm text-[var(--color-text-muted)]">正在加载 AI 模型设置…</div>
                  )}
                </section>
              )}
            </div>

            <div className="flex flex-col xl:justify-end xl:pb-4">
              {mountedSections.device && (
                <section className={`xl:ml-auto xl:w-full xl:max-w-[220px] ${showDevice ? '' : 'hidden'}`}>
                  {mountedSections.device ? (
                    <DeviceTab />
                  ) : (
                    <div className="text-xs text-[var(--color-text-muted)]">正在加载设备型号…</div>
                  )}
                </section>
              )}
            </div>
          </div>
        )}
      </div>
    </PageScaffold>
  )
}
