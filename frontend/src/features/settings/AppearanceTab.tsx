import { useLayoutStore } from '@/shared/stores/layoutStore'
import { cn } from '@/shared/utils/cn'
import { Sun, Moon, Monitor } from 'lucide-react'

const themes = [
  { key: 'light' as const, label: '浅色', icon: Sun },
  { key: 'dark' as const, label: '深色', icon: Moon },
  { key: 'system' as const, label: '跟随系统', icon: Monitor },
]

export function AppearanceTab() {
  const { theme, setTheme, applyTheme } = useLayoutStore()

  const handleTheme = (t: 'light' | 'dark' | 'system') => {
    setTheme(t)
    applyTheme(t)
  }

  return (
    <div className="max-w-md space-y-6">
      <div>
        <div className="text-xs text-[var(--color-text-muted)] mb-2">主题</div>
        <div className="flex gap-2">
          {themes.map(t => (
            <button key={t.key} onClick={() => handleTheme(t.key)}
              className={cn('flex flex-col items-center gap-1.5 px-4 py-3 rounded-xl border transition-colors',
                theme === t.key ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]' : 'border-[var(--color-border)] hover:border-[var(--color-border-strong)]'
              )}>
              <t.icon size={20} />
              <span className="text-xs">{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs text-[var(--color-text-muted)] mb-1.5">关于</div>
        <div className="aelin-card p-3 text-xs text-[var(--color-text-muted)] space-y-1">
          <p>Aelin — 你的私人信息管家</p>
          <p>Frontend v0.1.0 · React 19 + Vite 6</p>
        </div>
      </div>
    </div>
  )
}
