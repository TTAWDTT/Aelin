import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Camera } from 'lucide-react'
import { authApi } from '@/shared/api/auth'
import { useLocaleStore } from '@/shared/stores/localeStore'

export function ProfileTab() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const lastSubmittedRef = useRef<{ email: string; password: string } | null>(null)

  const { data: user, isLoading } = useQuery({ queryKey: ['me'], queryFn: authApi.me })

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    if (user?.email) setEmail(user.email)
  }, [user?.email])

  const update = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = {}
      const trimmedEmail = email.trim()
      const trimmedPassword = password.trim()
      if (trimmedEmail) body.email = trimmedEmail
      if (trimmedPassword) body.password = trimmedPassword
      return authApi.updateMe(body)
    },
    onSuccess: () => {
      toast.success(isZh ? '已更新' : 'Updated')
      setPassword('')
      qc.invalidateQueries({ queryKey: ['me'] })
    },
    onError: () => toast.error(isZh ? '更新失败' : 'Update failed'),
  })

  const upload = useMutation({
    mutationFn: (file: File) => authApi.uploadAvatar(file),
    onSuccess: () => {
      toast.success(isZh ? '头像已更新' : 'Avatar updated')
      qc.invalidateQueries({ queryKey: ['me'] })
    },
    onError: () => toast.error(isZh ? '上传失败' : 'Upload failed'),
  })

  const applyChanges = () => {
    const trimmedEmail = email.trim()
    const currentEmail = (user?.email ?? '').trim()
    const trimmedPassword = password.trim()

    // Avoid duplicate submissions for the same values (even if blur happens多次)
    const last = lastSubmittedRef.current
    if (last && last.email === trimmedEmail && last.password === trimmedPassword) return

    const hasEmailChange = trimmedEmail !== '' && trimmedEmail !== currentEmail
    const hasPassword = trimmedPassword.length > 0
    if (!hasEmailChange && !hasPassword) return

    lastSubmittedRef.current = { email: trimmedEmail, password: trimmedPassword }
    update.mutate()
  }

  if (isLoading) {
    return <div className="text-sm text-[var(--color-text-muted)]">{isZh ? '加载中…' : 'Loading…'}</div>
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="relative flex h-14 w-14 items-center justify-center overflow-hidden rounded-full bg-[var(--color-accent-soft)] cursor-pointer group"
          aria-label={isZh ? '上传头像' : 'Upload avatar'}
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
          <span className="text-[var(--color-text-muted)]">{isZh ? '邮箱' : 'Email'}</span>
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
          <span className="text-[var(--color-text-muted)]">{isZh ? '修改密码' : 'Change password'}</span>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onBlur={applyChanges}
            placeholder={isZh ? '输入新密码（至少 8 位）' : 'Enter new password (at least 8 characters)'}
            className="aelin-input"
          />
        </label>
      </div>
    </div>
  )
}
