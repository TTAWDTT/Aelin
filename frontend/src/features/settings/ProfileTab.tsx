import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '@/shared/api/auth'
import toast from 'react-hot-toast'
import { Camera, LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export function ProfileTab() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: user, isLoading } = useQuery({ queryKey: ['me'], queryFn: authApi.me })

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const update = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = {}
      if (email.trim()) body.email = email
      if (password.trim()) body.password = password
      return authApi.updateMe(body)
    },
    onSuccess: () => { toast.success('已更新'); setPassword(''); qc.invalidateQueries({ queryKey: ['me'] }) },
    onError: () => toast.error('更新失败'),
  })

  const upload = useMutation({
    mutationFn: (file: File) => authApi.uploadAvatar(file),
    onSuccess: () => { toast.success('头像已更新'); qc.invalidateQueries({ queryKey: ['me'] }) },
    onError: () => toast.error('上传失败'),
  })

  const logout = () => {
    localStorage.removeItem('token')
    navigate('/')
    window.location.reload()
  }

  if (isLoading) return <div className="text-sm text-[var(--color-text-muted)]">加载中…</div>

  return (
    <div className="max-w-md space-y-6">
      {/* Avatar */}
      <div className="flex items-center gap-4">
        <div className="relative w-16 h-16 rounded-full bg-[var(--color-accent-soft)] overflow-hidden flex items-center justify-center cursor-pointer group"
          onClick={() => fileRef.current?.click()}>
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <span className="text-2xl">{user?.email?.[0]?.toUpperCase()}</span>
          )}
          <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
            <Camera size={18} className="text-white" />
          </div>
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={e => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
        </div>
        <div>
          <div className="text-sm font-medium">{user?.email}</div>
          <div className="text-[11px] text-[var(--color-text-muted)]">ID: {user?.id}</div>
        </div>
      </div>

      {/* Email */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">邮箱</span>
        <input type="email" value={email || user?.email || ''} onChange={e => setEmail(e.target.value)} placeholder={user?.email}
          className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]" />
      </label>

      {/* Password */}
      <label className="block text-xs space-y-1">
        <span className="text-[var(--color-text-muted)]">修改密码</span>
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="输入新密码（至少 8 位）"
          className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-transparent focus:outline-none focus:border-[var(--color-accent)]" />
      </label>

      <div className="flex gap-3">
        <button onClick={() => update.mutate()} disabled={update.isPending || (!email.trim() && !password.trim())}
          className="px-4 py-2 text-sm font-medium rounded-xl bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90 disabled:opacity-50">
          {update.isPending ? '保存中…' : '保存'}
        </button>
        <button onClick={logout}
          className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-xl border border-[var(--color-danger)] text-[var(--color-danger)] hover:bg-[color-mix(in_srgb,var(--color-danger)_8%,transparent)]">
          <LogOut size={14} /> 退出登录
        </button>
      </div>
    </div>
  )
}
