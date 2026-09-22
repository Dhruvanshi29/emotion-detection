import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../lib/api'

type Memory = {
  id: string
  kind: string
  title: string
  content: string
  source: string
  source_ref_id: string | null
  tags: string[] | null
  importance: number
  pinned: boolean
  is_active: boolean
  embedding_model: string | null
  created_at: string
  updated_at: string
}

type MemoryList = { items: Memory[]; total: number }

type Hit = { memory: Memory; score: number; reasons: string[] }

type Candidate = {
  kind: string
  title: string
  content: string
  confidence: number
}

const KINDS = [
  { value: 'preference', label: 'Preference' },
  { value: 'fact', label: 'Fact' },
  { value: 'goal', label: 'Goal' },
  { value: 'theme', label: 'Theme' },
  { value: 'custom', label: 'Custom' },
]

const KIND_COLORS: Record<string, string> = {
  preference: 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200',
  fact: 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200',
  goal: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-200',
  theme: 'bg-indigo-100 text-indigo-900 dark:bg-indigo-900/40 dark:text-indigo-200',
  custom: 'bg-violet-100 text-violet-900 dark:bg-violet-900/40 dark:text-violet-200',
}

export default function MemoryPage() {
  const memoryQuery = useQuery({
    queryKey: ['memory', 'list'],
    queryFn: async () => {
      const r = await api.get<MemoryList>('/memory')
      return r.data.items
    },
  })
  const memories = memoryQuery.data ?? []
  const loading = memoryQuery.isPending
  const queryError = memoryQuery.error as
    | { response?: { data?: { detail?: string } }; message?: string }
    | null
  const error = queryError
    ? queryError.response?.data?.detail || queryError.message || 'Failed to load'
    : null

  // Create form
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [kind, setKind] = useState('custom')
  const [pinned, setPinned] = useState(false)
  const [busy, setBusy] = useState(false)

  // Search
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<Hit[] | null>(null)
  const [searching, setSearching] = useState(false)

  // Extract
  const [extractText, setExtractText] = useState('')
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [extracting, setExtracting] = useState(false)

  async function load() {
    await memoryQuery.refetch()
  }

  async function submitCreate() {
    if (!title.trim() || !content.trim()) return
    setBusy(true)
    try {
      await api.post('/memory', {
        kind,
        title: title.trim(),
        content: content.trim(),
        pinned,
      })
      setTitle('')
      setContent('')
      setPinned(false)
      await load()
    } finally {
      setBusy(false)
    }
  }

  async function togglePin(m: Memory) {
    await api.patch(`/memory/${m.id}`, { pinned: !m.pinned })
    await load()
  }

  async function removeMemory(m: Memory) {
    if (!window.confirm(`Delete "${m.title}"?`)) return
    await api.delete(`/memory/${m.id}`)
    await load()
  }

  async function deleteAll() {
    if (
      !window.confirm(
        'Permanently delete ALL your saved memories? This cannot be undone.',
      )
    )
      return
    await api.delete('/memory')
    await load()
  }

  async function runSearch() {
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await api.post<{ hits: Hit[] }>('/memory/search', {
        query: query.trim(),
        k: 5,
      })
      setHits(r.data.hits)
    } finally {
      setSearching(false)
    }
  }

  async function runExtract() {
    if (!extractText.trim()) return
    setExtracting(true)
    try {
      const r = await api.post<{ candidates: Candidate[] }>('/memory/extract', {
        text: extractText.trim(),
        source: 'chat',
      })
      setCandidates(r.data.candidates)
    } finally {
      setExtracting(false)
    }
  }

  async function saveCandidate(c: Candidate) {
    await api.post('/memory', {
      kind: c.kind,
      title: c.title,
      content: c.content,
      source: 'auto',
      importance: c.confidence,
    })
    setCandidates((prev) => (prev ? prev.filter((x) => x !== c) : prev))
    await load()
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex items-baseline justify-between mb-1">
        <h1 className="text-2xl font-semibold">What Saaya remembers</h1>
        <button
          onClick={() => void deleteAll()}
          className="text-xs uppercase rounded-md border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 px-3 py-1 hover:bg-rose-50 dark:hover:bg-rose-950/30"
        >
          Delete all
        </button>
      </div>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Notes the companion remembers about you. You are always in control —
        pin what matters, edit anything, or wipe it all.
      </p>

      {error && (
        <div className="mb-4 rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-[1fr_360px] gap-6">
        <section>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 mb-6">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Add memory
            </h2>
            <div className="space-y-3">
              <input
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                placeholder="Short title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <textarea
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                rows={3}
                placeholder="Content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="flex items-center gap-3">
                <select
                  className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  {KINDS.map((k) => (
                    <option key={k.value} value={k.value}>
                      {k.label}
                    </option>
                  ))}
                </select>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={pinned}
                    onChange={(e) => setPinned(e.target.checked)}
                  />
                  Pinned
                </label>
                <button
                  onClick={() => void submitCreate()}
                  disabled={busy || !title.trim() || !content.trim()}
                  className="ml-auto rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm px-4 py-2"
                >
                  {busy ? 'Saving…' : 'Add'}
                </button>
              </div>
            </div>
          </div>

          <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
            Saved memories ({memories.length})
          </h2>
          {loading ? (
            <div className="text-sm text-slate-500">Loading…</div>
          ) : memories.length === 0 ? (
            <div className="text-sm text-slate-500 italic">
              Nothing here yet. Add a memory or extract from a message below.
            </div>
          ) : (
            <ul className="space-y-2">
              {memories.map((m) => (
                <li
                  key={m.id}
                  className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-[10px] uppercase rounded-full px-2 py-0.5 ${KIND_COLORS[m.kind] ?? ''}`}
                        >
                          {m.kind}
                        </span>
                        {m.pinned && (
                          <span className="text-[10px] uppercase rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200 px-2 py-0.5">
                            pinned
                          </span>
                        )}
                        <span className="text-[11px] text-slate-500">
                          importance {Math.round(m.importance * 100)}%
                        </span>
                      </div>
                      <div className="font-medium mt-1">{m.title}</div>
                      <div className="text-sm text-slate-600 dark:text-slate-400 mt-0.5">
                        {m.content}
                      </div>
                      {m.tags && m.tags.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {m.tags.map((t) => (
                            <span
                              key={t}
                              className="text-[10px] rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5"
                            >
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col gap-1 items-end">
                      <button
                        onClick={() => void togglePin(m)}
                        className="text-[11px] uppercase rounded-full border border-slate-300 dark:border-slate-700 px-2 py-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                      >
                        {m.pinned ? 'unpin' : 'pin'}
                      </button>
                      <button
                        onClick={() => void removeMemory(m)}
                        className="text-[11px] uppercase rounded-full border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 px-2 py-0.5 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                      >
                        delete
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="space-y-6">
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Search
            </h2>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                placeholder="What are you looking for?"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void runSearch()}
              />
              <button
                onClick={() => void runSearch()}
                disabled={searching || !query.trim()}
                className="rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm px-3 py-2"
              >
                {searching ? '…' : 'Go'}
              </button>
            </div>
            {hits && (
              <div className="mt-3">
                {hits.length === 0 ? (
                  <div className="text-xs text-slate-500 italic">
                    No matches.
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {hits.map((h) => (
                      <li
                        key={h.memory.id}
                        className="rounded-md border border-slate-200 dark:border-slate-800 p-2"
                      >
                        <div className="text-sm font-medium">{h.memory.title}</div>
                        <div className="text-xs text-slate-500 line-clamp-2">
                          {h.memory.content}
                        </div>
                        <div className="flex items-center justify-between mt-1">
                          <span className="text-[11px] text-slate-500">
                            score {h.score.toFixed(2)}
                          </span>
                          <span className="text-[11px] text-slate-500">
                            {h.reasons.join(' · ')}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Extract from text
            </h2>
            <textarea
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              rows={4}
              placeholder="Paste a chat snippet or journal excerpt…"
              value={extractText}
              onChange={(e) => setExtractText(e.target.value)}
            />
            <button
              onClick={() => void runExtract()}
              disabled={extracting || !extractText.trim()}
              className="mt-2 rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm px-3 py-1.5"
            >
              {extracting ? 'Analyzing…' : 'Suggest memories'}
            </button>
            {candidates && (
              <div className="mt-3">
                {candidates.length === 0 ? (
                  <div className="text-xs text-slate-500 italic">
                    No candidates found in that text.
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {candidates.map((c, i) => (
                      <li
                        key={i}
                        className="rounded-md border border-slate-200 dark:border-slate-800 p-2"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-[10px] uppercase rounded-full px-2 py-0.5 ${KIND_COLORS[c.kind] ?? ''}`}
                          >
                            {c.kind}
                          </span>
                          <span className="text-[11px] text-slate-500">
                            {Math.round(c.confidence * 100)}%
                          </span>
                        </div>
                        <div className="text-sm font-medium mt-1">{c.title}</div>
                        <div className="text-xs text-slate-500">{c.content}</div>
                        <button
                          onClick={() => void saveCandidate(c)}
                          className="mt-1 text-[11px] uppercase text-indigo-600 hover:underline"
                        >
                          save
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
