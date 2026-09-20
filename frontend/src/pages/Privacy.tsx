import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

type ConsentEvent = {
  id: string
  kind: string
  granted: boolean
  source: string
  notes: string | null
  created_at: string
}

type ConsentState = {
  mic: boolean
  camera: boolean
  memory: boolean
  data_processing: boolean
  terms: boolean
  history: ConsentEvent[]
}

type AuditItem = {
  id: string
  category: string
  action: string
  details: unknown
  created_at: string
}

const CONSENT_TOGGLES: { kind: keyof Omit<ConsentState, 'history'>; label: string; help: string }[] = [
  { kind: 'mic', label: 'Microphone', help: 'Voice check-ins and transcription.' },
  { kind: 'camera', label: 'Camera', help: 'Opt-in facial expression analysis.' },
  { kind: 'memory', label: 'Memory', help: 'Let the companion remember details you share.' },
  { kind: 'data_processing', label: 'Data processing', help: 'Store activity for insights and dashboard.' },
  { kind: 'terms', label: 'Terms accepted', help: 'You have read the terms of use.' },
]

const CATEGORIES = [
  { id: 'chat', label: 'Chat history' },
  { id: 'journal', label: 'Journal entries' },
  { id: 'emotion', label: 'Emotion signals' },
  { id: 'voice', label: 'Voice check-ins' },
  { id: 'facial', label: 'Facial signals' },
  { id: 'wellness', label: 'Wellness sessions' },
  { id: 'reminders', label: 'Reminders + notifications' },
  { id: 'memory', label: 'Memories' },
  { id: 'audit', label: 'Audit + consent history' },
] as const

export default function PrivacyPage() {
  const nav = useNavigate()
  const { logout } = useAuth()
  const privacyQuery = useQuery({
    queryKey: ['privacy', 'overview'],
    queryFn: async () => {
      const [c, a] = await Promise.all([
        api.get<ConsentState>('/consent'),
        api.get<{ items: AuditItem[] }>('/audit'),
      ])
      return { consent: c.data, audit: a.data.items }
    },
  })
  const consent = privacyQuery.data?.consent ?? null
  const audit = privacyQuery.data?.audit ?? []
  const loading = privacyQuery.isPending
  const queryError = privacyQuery.error as
    | { response?: { data?: { detail?: string } }; message?: string }
    | null
  const error = queryError
    ? queryError.response?.data?.detail || queryError.message || 'Failed to load'
    : null
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState('')

  async function load() {
    await privacyQuery.refetch()
  }

  async function toggle(kind: string, granted: boolean) {
    setBusy(`consent:${kind}`)
    try {
      await api.post('/consent', { kind, granted, source: 'settings' })
      await load()
    } finally {
      setBusy(null)
    }
  }

  async function exportData() {
    setBusy('export')
    try {
      const r = await api.get('/privacy/export')
      const blob = new Blob([JSON.stringify(r.data, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `wellness-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setBusy(null)
    }
  }

  async function deleteCategory(id: string) {
    if (
      !window.confirm(
        `Delete all data in "${id}"? This cannot be undone.`,
      )
    )
      return
    setBusy(`cat:${id}`)
    try {
      await api.delete(`/privacy/data/${id}`)
      await load()
    } finally {
      setBusy(null)
    }
  }

  async function deleteAccount() {
    if (confirmDelete.trim().toUpperCase() !== 'DELETE') return
    setBusy('account')
    try {
      await api.request({
        method: 'DELETE',
        url: '/privacy/account',
        data: { confirm: 'DELETE' },
      })
      await logout()
      nav('/register')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-1">Privacy &amp; safety</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        You control what the platform remembers, records, and shares. AI
        signals here are not a clinical diagnosis.
      </p>

      {error && (
        <div className="mb-4 rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}

      {loading || !consent ? (
        <div className="text-sm text-slate-500">Loading…</div>
      ) : (
        <div className="space-y-8">
          {/* Consent */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Consent
            </h2>
            <ul className="divide-y divide-slate-200 dark:divide-slate-800">
              {CONSENT_TOGGLES.map(({ kind, label, help }) => {
                const on = consent[kind]
                const key = `consent:${kind}`
                return (
                  <li
                    key={kind}
                    className="py-3 flex items-center justify-between gap-4"
                  >
                    <div>
                      <div className="font-medium">{label}</div>
                      <div className="text-xs text-slate-500">{help}</div>
                    </div>
                    <button
                      onClick={() => void toggle(kind, !on)}
                      disabled={busy === key}
                      className={`text-xs uppercase rounded-full px-3 py-1 border ${
                        on
                          ? 'bg-emerald-600 border-emerald-600 text-white'
                          : 'border-slate-300 dark:border-slate-700'
                      }`}
                    >
                      {on ? 'granted' : 'off'}
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>

          {/* Export */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-2">
              Export your data
            </h2>
            <p className="text-xs text-slate-500 mb-3">
              Download a JSON copy of everything associated with your account.
            </p>
            <button
              onClick={() => void exportData()}
              disabled={busy === 'export'}
              className="rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-2 disabled:opacity-50"
            >
              {busy === 'export' ? 'Preparing…' : 'Download JSON'}
            </button>
          </section>

          {/* Category deletion */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Clear data by category
            </h2>
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {CATEGORIES.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between rounded-md border border-slate-200 dark:border-slate-800 px-3 py-2"
                >
                  <span className="text-sm">{c.label}</span>
                  <button
                    onClick={() => void deleteCategory(c.id)}
                    disabled={busy === `cat:${c.id}`}
                    className="text-xs uppercase rounded-full border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 px-2 py-1 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                  >
                    clear
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {/* Audit trail */}
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Recent activity
            </h2>
            {audit.length === 0 ? (
              <div className="text-xs text-slate-500 italic">
                Nothing recorded yet.
              </div>
            ) : (
              <ul className="space-y-1 max-h-72 overflow-auto text-sm">
                {audit.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center justify-between gap-3 py-1"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5">
                        {a.category}
                      </span>
                      <span>{a.action}</span>
                    </div>
                    <span className="text-[11px] text-slate-500">
                      {new Date(a.created_at).toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Danger zone */}
          <section className="rounded-xl border border-rose-300 dark:border-rose-800 p-4 bg-rose-50 dark:bg-rose-950/20">
            <h2 className="text-sm font-semibold uppercase text-rose-700 dark:text-rose-300 mb-2">
              Danger zone
            </h2>
            <p className="text-xs text-rose-700 dark:text-rose-300 mb-3">
              Permanently delete your account and all associated data. Type{' '}
              <code className="font-mono">DELETE</code> to confirm.
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={confirmDelete}
                onChange={(e) => setConfirmDelete(e.target.value)}
                placeholder="Type DELETE"
                className="flex-1 rounded-md border border-rose-300 dark:border-rose-800 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
              />
              <button
                onClick={() => void deleteAccount()}
                disabled={
                  busy === 'account' ||
                  confirmDelete.trim().toUpperCase() !== 'DELETE'
                }
                className="rounded-md bg-rose-600 hover:bg-rose-700 text-white text-sm px-4 py-2 disabled:opacity-50"
              >
                {busy === 'account' ? 'Deleting…' : 'Delete account'}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
