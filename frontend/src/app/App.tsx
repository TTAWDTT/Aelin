import { Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { RootLayout } from './layout/RootLayout'

const ChatPage = lazy(() => import('./routes/ChatPage'))
const TrackingPage = lazy(() => import('./routes/TrackingPage'))
const TrackingDetailPage = lazy(() => import('./routes/TrackingDetailPage'))
const ProcessesPage = lazy(() => import('./routes/ProcessesPage'))
const DiaryPage = lazy(() => import('./routes/DiaryPage'))
const FocusPage = lazy(() => import('./routes/FocusPage'))
const SettingsPage = lazy(() => import('./routes/SettingsPage'))

function Loading() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="w-5 h-5 rounded-full border-2 border-[var(--color-border-strong)] border-t-[var(--color-accent)] animate-spin" />
    </div>
  )
}

export function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<RootLayout />}>
          <Route index element={<ChatPage />} />
          <Route path="tracking" element={<TrackingPage />} />
          <Route path="tracking/:targetId" element={<TrackingDetailPage />} />
          <Route path="processes" element={<ProcessesPage />} />
          <Route path="diary" element={<DiaryPage />} />
          <Route path="focus" element={<FocusPage />} />
          <Route path="settings/*" element={<SettingsPage />} />
          {/* Compat redirects */}
          <Route path="chat" element={<Navigate to="/" replace />} />
          <Route path="desk" element={<Navigate to="/tracking?panel=desk" replace />} />
          <Route path="dashboard" element={<Navigate to="/tracking?panel=desk" replace />} />
          <Route path="signals" element={<Navigate to="/tracking" replace />} />
          <Route path="signals/:contactId" element={<Navigate to="/tracking" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
