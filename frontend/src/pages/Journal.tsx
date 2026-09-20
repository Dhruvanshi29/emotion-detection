import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../lib/api'

type Analysis = {
  summary: string
  themes: string[] | null
  reflection_prompt: string
  key_feelings: string[] | null
  dominant_emotion: string | null
  sentiment: string | null
  confidence: number | null
  provider: string | null
  model: string | null
  created_at: string
}

type EntryList = {
  id: string
  title: string | null
  mood: number | null
  tags: string[] | null
  created_at: string
  updated_at: string
  has_analysis: boolean
  preview: string
}

type EntryDetail = {
  id: string
  title: string | null
  content: string
  mood: number | null
  tags: string[] | null
  created_at: string
  updated_at: string
  analysis: Analysis | null
}

const MOOD_LABELS: Record<number, string> = {
  1: 'Awful',
  2: 'Low',
  3: 'Okay',
  4: 'Good',
  5: 'Great',
}

function moodEmoji(mood: number | null): string {
  if (mood === null) return '·'
  return ({ 1: '😞', 2: '🙁', 3: '😐', 4: '🙂', 5: '😄' } as Record<number, string>)[mood] ?? '·'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export default function JournalPage() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mode, setMode] = useState<'view' | 'compose'>('compose')

  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [mood, setMood] = useState<number | null>(null)
  const [tagsText, setTagsText] = useState('')

  const list = useQuery({
    queryKey: ['journal', 'list'],
    queryFn: async () => {
      const r = await api.get<EntryList[]>('/journal')
      return r.data
    },
  })

  const detail = useQuery({
    queryKey: ['journal', 'entry', selectedId],
    enabled: !!selectedId && mode === 'view',
    queryFn: async () => {
      const r = await api.get<EntryDetail>(`/journal/${selectedId}`)
      return r.data
    },
    refetchInterval: (q) => {
      const data = q.state.data as EntryDetail | undefined
      // If we know analysis is still pending, keep polling briefly.
      return data && !data.analysis ? 1500 : false
    },
  })

  function resetComposer() {
    setTitle('')
    setContent('')
    setMood(null)
    setTagsText('')
  }

  function openCompose() {
    setSelectedId(null)
    setMode('compose')
    resetComposer()
  }

  function openEntry(id: string) {
    setSelectedId(id)
    setMode('view')
  }

  const create = useMutation({
    mutationFn: async () => {
      const payload = {
        title: title.trim() || undefined,
        content: content.trim(),
        mood: mood ?? undefined,
        tags: tagsText
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
          .slice(0, 20),
        analyze: true,
      }
      const r = await api.post<EntryDetail>('/journal', payload)
      return r.data
    },
    onSuccess: async (data) => {
      resetComposer()
      await qc.invalidateQueries({ queryKey: ['journal', 'list'] })
      setSelectedId(data.id)
      setMode('view')
    },
  })

  const analyze = useMutation({
    mutationFn: async () => {
      if (!selectedId) return null
      const r = await api.post<EntryDetail>(`/journal/${selectedId}/analyze`)
      return r.data
    },
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: ['journal', 'entry', selectedId],
      })
      await qc.invalidateQueries({ queryKey: ['journal', 'list'] })
    },
  })

  const del = useMutation({
    mutationFn: async () => {
      if (!selectedId) return
      await api.delete(`/journal/${selectedId}`)
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['journal', 'list'] })
      openCompose()
    },
  })

  return (
    <div className="mx-auto max-w-6xl h-[calc(100vh-57px)] flex px-2 gap-2">
      {/* Sidebar: entry list */}
      <aside className="w-64 shrink-0 py-4 hidden sm:flex flex-col border-r border-slate-200 dark:border-slate-800 pr-3">
        <button
          onClick={openCompose}
          className="w-full rounded-md bg-indigo-600 text-white py-2 mb-3 hover:bg-indigo-700"
        >
          + New entry
        </button>

        {list.isLoading && (
          <div className="text-sm text-slate-500 px-2">Loading…</div>
        )}
        {list.isError && (
          <div className="text-sm text-red-600 px-2">
            Couldn't load your journal.
          </div>
        )}
        {list.data && list.data.length === 0 && (
          <div className="text-sm text-slate-500 italic px-2">
            No entries yet. Start with a small check-in.
          </div>
        )}

        <div className="overflow-y-auto space-y-1 text-sm">
          {list.data?.map((e) => (
            <button
              key={e.id}
              onClick={() => openEntry(e.id)}
              className={
                'w-full text-left rounded-md px-2 py-2 ' +
                (selectedId === e.id && mode === 'view'
                  ? 'bg-slate-200 dark:bg-slate-800'
                  : 'hover:bg-slate-100 dark:hover:bg-slate-800')
              }
              title={e.title ?? 'Untitled'}
            >
              <div className="flex items-center gap-2">
                <span className="text-lg" aria-hidden>
                  {moodEmoji(e.mood)}
                </span>
                <span className="truncate font-medium">
                  {e.title ?? 'Untitled'}
                </span>
              </div>
              <div className="text-xs text-slate-500 truncate">
                {formatDate(e.created_at)} · {e.preview || '(no content)'}
              </div>
              {!e.has_analysis && (
                <div className="text-[11px] text-amber-600 mt-0.5">
                  reflection pending
                </div>
              )}
            </button>
          ))}
        </div>
      </aside>

      {/* Main */}
      <section className="flex-1 flex flex-col min-w-0 py-4 overflow-y-auto">
        {mode === 'compose' ? (
          <ComposePanel
            title={title}
            setTitle={setTitle}
            content={content}
            setContent={setContent}
            mood={mood}
            setMood={setMood}
            tagsText={tagsText}
            setTagsText={setTagsText}
            onSubmit={() => create.mutate()}
            submitting={create.isPending}
            error={create.isError ? 'Could not save your entry.' : null}
          />
        ) : (
          <ViewPanel
            entry={detail.data}
            loading={detail.isLoading}
            error={detail.isError}
            analyzing={analyze.isPending}
            onAnalyze={() => analyze.mutate()}
            onDelete={() => {
              if (confirm('Delete this journal entry?')) del.mutate()
            }}
          />
        )}
      </section>
    </div>
  )
}

function ComposePanel(props: {
  title: string
  setTitle: (v: string) => void
  content: string
  setContent: (v: string) => void
  mood: number | null
  setMood: (v: number | null) => void
  tagsText: string
  setTagsText: (v: string) => void
  onSubmit: () => void
  submitting: boolean
  error: string | null
}) {
  const {
    title,
    setTitle,
    content,
    setContent,
    mood,
    setMood,
    tagsText,
    setTagsText,
    onSubmit,
    submitting,
    error,
  } = props

  const canSubmit = content.trim().length > 0 && !submitting

  return (
    <div className="px-2 max-w-3xl w-full mx-auto">
      <h1 className="text-2xl font-semibold mb-4">New journal entry</h1>
      <p className="text-sm text-slate-500 mb-4">
        Write freely. Aria will read it after you save and offer a gentle
        reflection — not advice, not a diagnosis.
      </p>
      <div className="space-y-4">
        <div>
          <label className="block text-sm mb-1">Title (optional)</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            placeholder="A quiet evening"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
          />
        </div>

        <div>
          <label className="block text-sm mb-1">How you feel</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={20000}
            rows={10}
            placeholder="What's on your mind?"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 font-serif leading-relaxed"
          />
          <div className="text-xs text-slate-500 mt-1">
            {content.length} / 20000
          </div>
        </div>

        <div>
          <label className="block text-sm mb-2">Mood (optional)</label>
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setMood(mood === n ? null : n)}
                className={
                  'rounded-md border px-3 py-2 text-lg transition ' +
                  (mood === n
                    ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950'
                    : 'border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800')
                }
                title={MOOD_LABELS[n]}
                aria-pressed={mood === n}
              >
                {moodEmoji(n)}
              </button>
            ))}
            {mood !== null && (
              <span className="self-center text-sm text-slate-500">
                {MOOD_LABELS[mood]}
              </span>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm mb-1">
            Tags (optional, comma-separated)
          </label>
          <input
            value={tagsText}
            onChange={(e) => setTagsText(e.target.value)}
            placeholder="evening, work, family"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
          />
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="rounded-md bg-indigo-600 text-white px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting ? 'Saving…' : 'Save entry'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ViewPanel(props: {
  entry?: EntryDetail
  loading: boolean
  error: boolean
  analyzing: boolean
  onAnalyze: () => void
  onDelete: () => void
}) {
  const { entry, loading, error, analyzing, onAnalyze, onDelete } = props

  if (loading) {
    return <div className="p-6 text-slate-500">Loading…</div>
  }
  if (error) {
    return (
      <div className="p-6 text-red-600">
        We couldn't load that entry. Try again in a moment.
      </div>
    )
  }
  if (!entry) {
    return (
      <div className="p-6 text-slate-500 italic">
        Select an entry from the left, or start a new one.
      </div>
    )
  }

  return (
    <article className="px-2 max-w-3xl w-full mx-auto">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">
            {entry.title ?? 'Untitled'}
          </h1>
          <div className="text-xs text-slate-500 mt-1">
            {formatDate(entry.created_at)}
            {entry.mood !== null && (
              <>
                {' · '}
                <span aria-hidden>{moodEmoji(entry.mood)}</span>{' '}
                {MOOD_LABELS[entry.mood]}
              </>
            )}
          </div>
          {entry.tags && entry.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {entry.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-slate-200 dark:bg-slate-800 px-2 py-0.5 text-xs"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={onAnalyze}
            disabled={analyzing}
            className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
            title="Regenerate the AI reflection"
          >
            {analyzing ? 'Reflecting…' : 'Re-reflect'}
          </button>
          <button
            onClick={onDelete}
            className="rounded-md border border-red-300 text-red-700 dark:border-red-800 dark:text-red-400 px-3 py-1.5 text-sm hover:bg-red-50 dark:hover:bg-red-950"
          >
            Delete
          </button>
        </div>
      </header>

      <div className="whitespace-pre-wrap font-serif leading-relaxed rounded-md bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-4">
        {entry.content}
      </div>

      <ReflectionCard analysis={entry.analysis} analyzing={analyzing} />
    </article>
  )
}

function ReflectionCard({
  analysis,
  analyzing,
}: {
  analysis: Analysis | null
  analyzing: boolean
}) {
  if (!analysis) {
    return (
      <div className="mt-6 rounded-md border border-dashed border-slate-300 dark:border-slate-700 p-4 text-sm text-slate-500">
        {analyzing
          ? 'Aria is reading your entry…'
          : 'Reflection will appear here shortly.'}
      </div>
    )
  }

  return (
    <div className="mt-6 rounded-md border border-indigo-200 dark:border-indigo-900 bg-indigo-50/50 dark:bg-indigo-950/30 p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-indigo-700 dark:text-indigo-300 mb-2">
        Reflection from Aria
        {analysis.provider && (
          <span className="text-slate-500 normal-case">
            · {analysis.provider}
          </span>
        )}
      </div>
      <p className="text-sm mb-3">{analysis.summary}</p>

      {analysis.themes && analysis.themes.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-slate-500 mb-1">Themes</div>
          <div className="flex flex-wrap gap-1">
            {analysis.themes.map((t) => (
              <span
                key={t}
                className="rounded-full bg-white dark:bg-slate-900 border border-indigo-200 dark:border-indigo-800 px-2 py-0.5 text-xs"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {analysis.key_feelings && analysis.key_feelings.length > 0 && (
        <div className="mb-3 text-xs text-slate-500">
          Feelings noted:{' '}
          <span className="text-slate-700 dark:text-slate-300">
            {analysis.key_feelings.join(', ')}
          </span>
        </div>
      )}

      <div className="mt-3 border-t border-indigo-200 dark:border-indigo-900 pt-3">
        <div className="text-xs text-slate-500 mb-1">A gentle question</div>
        <p className="text-sm italic">{analysis.reflection_prompt}</p>
      </div>

      <p className="mt-4 text-[11px] text-slate-500">
        Signals only, not a diagnosis. If you are in immediate danger, contact
        local emergency services.
      </p>
    </div>
  )
}
