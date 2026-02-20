import { useState } from 'react'
import { authApi } from '@/shared/api/auth'
import toast from 'react-hot-toast'

interface Props { onAuth: () => void }

export function AuthGate({ onAuth }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password.trim()) return
    setLoading(true)
    try {
      if (mode === 'register') {
        await authApi.register({ email, password })
        toast.success('注册成功，正在登录…')
      }
      const token = await authApi.login(email, password)
      localStorage.setItem('token', token.access_token)
      onAuth()
    } catch (err: any) {
      toast.error(err?.message ?? (mode === 'login' ? '登录失败' : '注册失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)] text-[var(--color-text)] p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
        <div className="text-center">
          <h1 className="text-2xl font-bold" style={{ fontFamily: 'var(--font-heading)' }}>Aelin</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-1">你的私人信息管家</p>
        </div>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">邮箱</span>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus
            className="w-full px-3 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]" />
        </label>

        <label className="block text-xs space-y-1">
          <span className="text-[var(--color-text-muted)]">密码</span>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            className="w-full px-3 py-2.5 text-sm rounded-xl border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]" />
        </label>

        <button type="submit" disabled={loading}
          className="w-full py-2.5 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90 disabled:opacity-50">
          {loading ? '请稍候…' : mode === 'login' ? '登录' : '注册'}
        </button>

        <button type="button" onClick={() => setMode(m => m === 'login' ? 'register' : 'login')}
          className="w-full text-xs text-[var(--color-accent)] hover:underline">
          {mode === 'login' ? '没有账号？注册' : '已有账号？登录'}
        </button>
      </form>
    </div>
  )
}
