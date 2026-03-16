import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '@/shared/api/auth'
import toast from 'react-hot-toast'
import { Camera } from 'lucide-react'

export function ProfileTab() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: user, isLoading } = useQuery({ queryKey: ['me'], queryFn: authApi.me })

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (user?.email) setEmail(user.email)
  }, [user?.email])

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

  const applyChanges = () => {
    const trimmedEmail = email.trim()
    const currentEmail = (user?.email ?? '').trim()
    const hasEmailChange = trimmedEmail !== '' && trimmedEmail !== currentEmail
    const hasPassword = password.trim().length > 0
    if (!hasEmailChange && !hasPassword) return
    update.mutate()
  }

  if (isLoading) {
    return <div className="text-sm text-[var(--color-text-muted)]">加载中…</div>
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-full bg-[var(--color-accent-soft)] cursor-pointer group"
          aria-label="上传头像"
          onClick={() => fileRef.current?.click()}
        >
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <span className="text-xl">{user?.email?.[0]?.toUpperCase()}</span>
          )}
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            <Camera size={18} className="text-white" />
          </div>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (!file) return
            upload.mutate(file)
            event.currentTarget.value = ''
          }}
        />
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{user?.email}</div>
          <div className="text-[11px] text-[var(--color-text-muted)]">ID: {user?.id}</div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <label className="block space-y-1 text-xs">
          <span className="text-[var(--color-text-muted)]">邮箱</span>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onBlur={applyChanges}
            placeholder={user?.email}
            className="aelin-input"
          />
        </label>

        <label className="block space-y-1 text-xs">
          <span className="text-[var(--color-text-muted)]">修改密码</span>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onBlur={applyChanges}
            placeholder="输入新密码（至少 8 位）"
            className="aelin-input"
          />
        </label>
      </div>
    </div>
  )
}
