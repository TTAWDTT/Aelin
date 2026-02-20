import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { App } from './app/App'
import { useLayoutStore, applyTheme } from './shared/stores/layoutStore'
import './styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000 } },
})

// Apply theme on load
const theme = useLayoutStore.getState().theme
applyTheme(theme)
useLayoutStore.subscribe((s) => applyTheme(s.theme))
// System preference listener
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (useLayoutStore.getState().theme === 'system') applyTheme('system')
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster
          position="bottom-center"
          toastOptions={{
            style: {
              background: 'var(--color-panel)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
              borderRadius: '10px',
              fontSize: '14px',
            },
          }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
