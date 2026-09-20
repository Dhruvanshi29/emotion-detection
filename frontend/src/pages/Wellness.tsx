import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

type Exercise = {
  id: string
  slug: string
  title: string
  summary: string
  category: string
  duration_seconds: number
  body: string
  target_emotions: string[] | null
  target_goals: string[] | null
  tags: string[] | null
}

type ExerciseSummary = {
  id: string
  slug: string
  title: string
  summary: string
  category: string
  duration_seconds: number
}

type Recommendation = {
  exercise: ExerciseSummary
  score: number
  reasons: string[]
}

type RecommendationList = {
  items: Recommendation[]
  recent_dominant_emotion: string | null
  active_goals: string[]
}

type Goal = {
  id: string
  kind: string
  is_active: boolean
  priority: number | null
  created_at: string
}

type SessionRow = {
  id: string
  exercise_id: string
  exercise_slug: string
  exercise_title: string
  started_at: string
  completed_at: string | null
  rating: number | null
  notes: string | null
}

const GOAL_KINDS: { kind: string; label: string }[] = [
  { kind: 'reduce_stress', label: 'Reduce stress' },
  { kind: 'manage_anxiety', label: 'Manage anxiety' },
  { kind: 'manage_anger', label: 'Manage anger' },
  { kind: 'lift_mood', label: 'Lift my mood' },
  { kind: 'sleep_better', label: 'Sleep better' },
  { kind: 'general_wellbeing', label: 'General wellbeing' },
]

const CATEGORY_STYLES: Record<string, string> = {
  breathing: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200',
  grounding: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  reflection: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  movement: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200',
}

function categoryChip(category: string) {
  const cls =
    CATEGORY_STYLES[category] ||
    'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200'
  return (
    <span className={`text-[10px] uppercase tracking-wide rounded-full px-2 py-0.5 ${cls}`}>
      {category}
    </span>
  )
}

function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60)
  const r = s % 60
  return m ? `${m}m${r ? ` ${r}s` : ''}` : `${r}s`
}

export default function WellnessPage() {
  const wellnessQuery = useQuery({
    queryKey: ['wellness', 'overview'],
    queryFn: async () => {
      const [ex, rec, gl, ss] = await Promise.all([
        api.get<Exercise[]>('/wellness/exercises'),
        api.get<RecommendationList>('/wellness/recommendations?limit=5'),
        api.get<Goal[]>('/wellness/goals'),
        api.get<SessionRow[]>('/wellness/sessions?limit=20'),
      ])
      return {
        exercises: ex.data,
        recommendations: rec.data,
        goals: gl.data,
        sessions: ss.data,
      }
    },
  })
  const exercises = wellnessQuery.data?.exercises ?? []
  const recs = wellnessQuery.data?.recommendations ?? null
  const goals = wellnessQuery.data?.goals ?? []
  const sessions = wellnessQuery.data?.sessions ?? []
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [activeSession, setActiveSession] = useState<SessionRow | null>(null)
  const [remaining, setRemaining] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const loading = wellnessQuery.isPending
  const loadError = wellnessQuery.error as
    | { response?: { data?: { detail?: string } }; message?: string }
    | null
  const displayError =
    error ||
    (loadError
      ? loadError.response?.data?.detail || loadError.message || 'Failed to load'
      : null)

  async function load() {
    await wellnessQuery.refetch()
  }

  useEffect(() => {
    if (!activeSession) return
    const id = window.setInterval(() => {
      setRemaining((r) => Math.max(0, r - 1))
    }, 1000)
    return () => window.clearInterval(id)
  }, [activeSession])

  const activeGoalKinds = new Set(
    goals.filter((g) => g.is_active).map((g) => g.kind),
  )
  const selected =
    exercises.find((e) => e.slug === selectedSlug) ||
    exercises.find((e) => e.slug === recs?.items[0]?.exercise.slug) ||
    exercises[0]

  async function toggleGoal(kind: string, on: boolean) {
    setError(null)
    try {
      if (on) {
        await api.post<Goal>('/wellness/goals', { kind })
      } else {
        const g = goals.find((x) => x.kind === kind)
        if (g) await api.delete(`/wellness/goals/${g.id}`)
      }
      await load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(err.response?.data?.detail || err.message || 'Failed to update goals')
    }
  }

  async function startExercise(slug: string) {
    setError(null)
    try {
      const r = await api.post<SessionRow>('/wellness/sessions', {
        exercise_slug: slug,
      })
      const exercise = exercises.find((item) => item.slug === slug)
      setRemaining(exercise?.duration_seconds ?? 0)
      setActiveSession(r.data)
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(err.response?.data?.detail || err.message || 'Failed to start')
    }
  }

  async function completeActive(rating: number | null) {
    if (!activeSession) return
    try {
      await api.patch(`/wellness/sessions/${activeSession.id}`, {
        completed: true,
        rating,
      })
      setActiveSession(null)
      await load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(err.response?.data?.detail || err.message || 'Failed to complete')
    }
  }

  if (loading) return <div className="p-8 text-center">Loading…</div>

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Wellness</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Curated exercises with deterministic recommendations based on your
          recent signals and goals. These are gentle suggestions, not medical advice.
        </p>
      </div>

      {displayError && (
        <div className="rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
          {displayError}
        </div>
      )}

      {/* Goals row */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
        <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
          Your goals
        </div>
        <div className="flex flex-wrap gap-2">
          {GOAL_KINDS.map(({ kind, label }) => {
            const on = activeGoalKinds.has(kind)
            return (
              <button
                key={kind}
                onClick={() => toggleGoal(kind, !on)}
                className={`text-sm rounded-full px-3 py-1 border transition ${
                  on
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Recommendations */}
      {recs && recs.items.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-500">
                Recommended for you
              </div>
              <div className="text-xs text-slate-500">
                {recs.recent_dominant_emotion
                  ? `Based on recent signal: ${recs.recent_dominant_emotion}`
                  : 'Based on your goals'}
                {recs.active_goals.length > 0
                  ? ` · goals: ${recs.active_goals.join(', ')}`
                  : ''}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {recs.items.map((r) => (
              <button
                key={r.exercise.slug}
                onClick={() => setSelectedSlug(r.exercise.slug)}
                className="text-left rounded-lg border border-slate-200 dark:border-slate-800 hover:border-indigo-400 p-3 bg-slate-50 dark:bg-slate-950/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{r.exercise.title}</div>
                  {categoryChip(r.exercise.category)}
                </div>
                <div className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                  {r.exercise.summary}
                </div>
                <div className="text-xs text-slate-500 mt-2 flex items-center gap-2">
                  <span>{fmtSeconds(r.exercise.duration_seconds)}</span>
                  <span>·</span>
                  <span>score {r.score.toFixed(2)}</span>
                </div>
                {r.reasons.length > 0 && (
                  <div className="text-[11px] text-slate-500 mt-1 italic">
                    {r.reasons.join(' · ')}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Library + detail */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-4">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 max-h-[520px] overflow-y-auto">
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-2 px-1">
            Library
          </div>
          <ul className="space-y-1">
            {exercises.map((ex) => (
              <li key={ex.slug}>
                <button
                  onClick={() => setSelectedSlug(ex.slug)}
                  className={`w-full text-left rounded-md px-2 py-2 hover:bg-slate-100 dark:hover:bg-slate-800 ${
                    (selected?.slug === ex.slug) ? 'bg-slate-100 dark:bg-slate-800' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-sm">{ex.title}</div>
                    {categoryChip(ex.category)}
                  </div>
                  <div className="text-xs text-slate-500">
                    {fmtSeconds(ex.duration_seconds)}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          {selected ? (
            <>
              <div className="flex items-center justify-between gap-2 mb-2">
                <h2 className="text-lg font-semibold">{selected.title}</h2>
                {categoryChip(selected.category)}
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-400 mb-2">
                {selected.summary}
              </div>
              <div className="text-xs text-slate-500 mb-4">
                {fmtSeconds(selected.duration_seconds)}
              </div>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed bg-slate-50 dark:bg-slate-950/40 rounded-md p-3">
                {selected.body}
              </pre>
              <div className="mt-4">
                <button
                  onClick={() => startExercise(selected.slug)}
                  disabled={activeSession !== null}
                  className="rounded-md bg-indigo-600 text-white px-4 py-2 hover:bg-indigo-700 disabled:opacity-50"
                >
                  Start
                </button>
              </div>
            </>
          ) : (
            <div className="text-sm text-slate-500">Pick an exercise to view.</div>
          )}
        </div>
      </div>

      {/* Active session panel */}
      {activeSession && (
        <div className="rounded-xl border border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-950/30 p-5 space-y-3">
          <div className="text-sm uppercase tracking-wide text-indigo-700 dark:text-indigo-300">
            In progress
          </div>
          <div className="text-lg font-semibold">
            {activeSession.exercise_title}
          </div>
          <div className="text-3xl font-mono">
            {Math.floor(remaining / 60)
              .toString()
              .padStart(2, '0')}
            :{(remaining % 60).toString().padStart(2, '0')}
          </div>
          <div className="text-xs text-slate-600 dark:text-slate-400">
            When you're done, rate how helpful it was:
          </div>
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                onClick={() => completeActive(n)}
                className="rounded-md bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                {n}★
              </button>
            ))}
            <button
              onClick={() => completeActive(null)}
              className="rounded-md bg-slate-700 text-white px-3 py-1 hover:bg-slate-800"
            >
              Done
            </button>
          </div>
        </div>
      )}

      {/* Recent sessions */}
      {sessions.length > 0 && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">
            Recent sessions
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
            {sessions.slice(0, 10).map((s) => (
              <li key={s.id} className="py-2 flex items-center justify-between gap-2">
                <div>
                  <div className="font-medium">{s.exercise_title}</div>
                  <div className="text-xs text-slate-500">
                    {new Date(s.started_at).toLocaleString()}
                    {s.completed_at ? ' · completed' : ' · in progress'}
                  </div>
                </div>
                {s.rating != null && (
                  <div className="text-sm text-amber-500">
                    {'★'.repeat(s.rating)}
                    <span className="text-slate-300 dark:text-slate-700">
                      {'★'.repeat(5 - s.rating)}
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
