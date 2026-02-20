import { Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense, useState, useCallback } from 'react'
import { RootLayout } from './layout/RootLayout'
import { AuthGate } from '@/features/auth/AuthGate'

const ChatPage = lazy(() => import('./routes/ChatPage'))
const SignalsPage = lazy(() => import('./routes/SignalsPage'))
const SignalThreadPage = lazy(() => import('./routes/SignalThreadPage'))
const TrackingPage = lazy(() => import('./routes/TrackingPage'))
const TrackingDetailPage = lazy(() => import('./routes/TrackingDetailPage'))
const SettingsPage = lazy(() => import('./routes/SettingsPage'))

function Loading() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="w-5 h-5 rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-accent)] animate-spin" />
    </div>
  )
}

export function App() {
  const [authed, setAuthed] = useState(() => !!localStorage.getItem('token'))

  const handleAuth = useCallback(() => setAuthed(true), [])

  if (!authed) return <AuthGate onAuth={handleAuth} />

  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<RootLayout />}>
          <Route index element={<ChatPage />} />
          <Route path="signals" element={<SignalsPage />} />
          <Route path="signals/:contactId" element={<SignalThreadPage />} />
          <Route path="tracking" element={<TrackingPage />} />
          <Route path="tracking/:targetId" element={<TrackingDetailPage />} />
          <Route path="settings/*" element={<SettingsPage />} />
          {/* Compat redirects */}
          <Route path="chat" element={<Navigate to="/" replace />} />
          <Route path="desk" element={<Navigate to="/signals" replace />} />
          <Route path="dashboard" element={<Navigate to="/signals" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
