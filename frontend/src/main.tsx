import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './lib/auth.tsx'
import * as Sentry from '@sentry/react'

const sentryDsn = import.meta.env.VITE_SENTRY_DSN as string | undefined
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_RELEASE || undefined,
    sendDefaultPii: false,
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || 0),
    beforeSend(event) {
      if (event.request) {
        delete event.request.cookies
        delete event.request.data
        event.request.query_string = '[REDACTED]'
      }
      if (event.user) delete event.user.email
      return event
    },
  })
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Sentry.ErrorBoundary fallback={<div className="mx-auto max-w-xl px-4 py-16 text-center"><h1 className="text-2xl font-semibold">Saaya needs a quiet restart.</h1><p className="mt-2 text-slate-500">Your saved information is safe. Refresh this page when you are ready.</p></div>}>
            <App />
          </Sentry.ErrorBoundary>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
