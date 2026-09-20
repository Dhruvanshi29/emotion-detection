import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../lib/api'

type Summary = {
  window_days: number
  total_chat_messages: number
  total_conversations: number
  total_journal_entries: number
  total_wellness_sessions: number
  total_emotion_events: number
  total_voice_analyses: number
  total_facial_analyses: number
  active_reminders: number
  active_goals: number
  unread_notifications: number
  dominant_emotion: string | null
  dominant_emotion_percent: number
  sentiment_positive_pct: number
  sentiment_neutral_pct: number
  sentiment_negative_pct: number
  average_journal_mood: number | null
  average_exercise_rating: number | null
  current_streak_days: number
  longest_streak_days: number
  latest_risk_level: string | null
  generated_at: string
}

type EmotionsBreakdown = {
  window_days: number
  by_emotion: Record<string, number>
  by_source: Record<string, number>
  by_sentiment: Record<string, number>
  daily: { date: string; counts: Record<string, number> }[]
  total: number
}

type TrendPoint = {
  date: string
  mood_score: number | null
  events: number
  journal_entries: number
  exercise_sessions: number
  journal_mood_avg: number | null
  exercise_rating_avg: number | null
}

type Trends = {
  window_days: number
  granularity: string
  points: TrendPoint[]
  rolling_mood_7d: number | null
  momentum: 'up' | 'down' | 'steady' | 'insufficient_data'
}

type Insights = {
  window_days: number
  highlights: string[]
  top_emotion: string | null
  top_exercise_category: string | null
}

const EMOTION_COLORS: Record<string, string> = {
  joy: 'bg-amber-400',
  sadness: 'bg-blue-400',
  anger: 'bg-rose-500',
  fear: 'bg-violet-500',
  surprise: 'bg-teal-400',
  disgust: 'bg-lime-500',
  neutral: 'bg-slate-400',
}

const EMOTION_EMOJI: Record<string, string> = {
  joy: '😊',
  sadness: '😔',
  anger: '😠',
  fear: '😨',
  surprise: '😮',
  disgust: '🤢',
  neutral: '😐',
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string
  value: string | number
  hint?: string
}) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {hint && <div className="text-[11px] text-slate-500 mt-1">{hint}</div>}
    </div>
  )
}

function MoodSparkline({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) return null
  const w = 480
  const h = 80
  const pad = 4
  const vals = points.map((p) => p.mood_score)
  // Map [-1, 1] → [h - pad, pad], nulls skipped.
  const path: string[] = []
  const zeroY = h / 2
  vals.forEach((v, i) => {
    if (v == null) return
    const x = pad + (i / Math.max(points.length - 1, 1)) * (w - pad * 2)
    const y = pad + (1 - (v + 1) / 2) * (h - pad * 2)
    path.push(`${path.length === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
  })
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="text-indigo-500">
      <line
        x1={0}
        x2={w}
        y1={zeroY}
        y2={zeroY}
        stroke="currentColor"
        strokeOpacity={0.2}
        strokeDasharray="4 4"
      />
      {path.length > 0 && (
        <path
          d={path.join(' ')}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        />
      )}
    </svg>
  )
}

function EmotionDistribution({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  if (total === 0) {
    return <div className="text-sm text-slate-500 italic">No signals yet.</div>
  }
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  return (
    <div className="space-y-2">
      {entries.map(([e, n]) => {
        const pct = Math.round((100 * n) / total)
        return (
          <div key={e}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span>
                <span className="mr-1">{EMOTION_EMOJI[e] ?? '•'}</span>
                {e}
              </span>
              <span className="text-slate-500">
                {n} · {pct}%
              </span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
              <div
                className={`h-full ${EMOTION_COLORS[e] ?? 'bg-slate-400'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SentimentBar({ summary }: { summary: Summary }) {
  const total =
    summary.sentiment_positive_pct +
    summary.sentiment_neutral_pct +
    summary.sentiment_negative_pct
  if (total === 0) {
    return <div className="text-sm text-slate-500 italic">No signals yet.</div>
  }
  return (
    <div>
      <div className="h-3 w-full flex rounded-full overflow-hidden">
        <div
          className="bg-emerald-500"
          style={{ width: `${summary.sentiment_positive_pct}%` }}
        />
        <div
          className="bg-slate-400"
          style={{ width: `${summary.sentiment_neutral_pct}%` }}
        />
        <div
          className="bg-rose-500"
          style={{ width: `${summary.sentiment_negative_pct}%` }}
        />
      </div>
      <div className="flex justify-between text-[11px] mt-1 text-slate-500">
        <span>positive {summary.sentiment_positive_pct}%</span>
        <span>neutral {summary.sentiment_neutral_pct}%</span>
        <span>negative {summary.sentiment_negative_pct}%</span>
      </div>
    </div>
  )
}

function RiskBadge({ level }: { level: string | null }) {
  if (!level) return null
  const color =
    level === 'high'
      ? 'bg-rose-600 text-white'
      : level === 'medium'
        ? 'bg-amber-500 text-white'
        : level === 'low'
          ? 'bg-yellow-200 text-yellow-900'
          : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-100'
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] uppercase rounded-full px-2 py-0.5 ${color}`}
      title="Most recent safety signal from your conversations"
    >
      Latest risk · {level}
    </span>
  )
}

export default function DashboardPage() {
  const [windowDays, setWindowDays] = useState(7)
  const dashboardQuery = useQuery({
    queryKey: ['dashboard', windowDays],
    queryFn: async () => {
      const trendWindow = Math.max(windowDays, 14)
      const [s, e, t, i] = await Promise.all([
        api.get<Summary>(`/dashboard/summary?window_days=${windowDays}`),
        api.get<EmotionsBreakdown>(
          `/dashboard/emotions?window_days=${windowDays}`,
        ),
        api.get<Trends>(`/dashboard/trends?window_days=${trendWindow}`),
        api.get<Insights>(`/dashboard/insights?window_days=${windowDays}`),
      ])
      return { summary: s.data, emotions: e.data, trends: t.data, insights: i.data }
    },
  })
  const summary = dashboardQuery.data?.summary ?? null
  const emotions = dashboardQuery.data?.emotions ?? null
  const trends = dashboardQuery.data?.trends ?? null
  const insights = dashboardQuery.data?.insights ?? null
  const loading = dashboardQuery.isPending
  const queryError = dashboardQuery.error as
    | { response?: { data?: { detail?: string } }; message?: string }
    | null
  const error = queryError
    ? queryError.response?.data?.detail || queryError.message || 'Failed to load'
    : null

  const momentumLabel = useMemo(() => {
    if (!trends) return null
    return {
      up: '↑ trending up',
      down: '↓ trending down',
      steady: '→ steady',
      insufficient_data: 'not enough data',
    }[trends.momentum]
  }, [trends])

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h1 className="text-2xl font-semibold">Your dashboard</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Signals, patterns and progress — not a clinical assessment.
          </p>
        </div>
        <div>
          <label className="text-xs uppercase text-slate-500 mr-2">
            Window
          </label>
          <select
            className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1 text-sm"
            value={windowDays}
            onChange={(e) => setWindowDays(parseInt(e.target.value, 10))}
          >
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}
      {loading && !summary && (
        <div className="text-sm text-slate-500">Loading…</div>
      )}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard
              label="Chat messages"
              value={summary.total_chat_messages}
              hint={`${summary.total_conversations} conversation(s)`}
            />
            <StatCard
              label="Journal entries"
              value={summary.total_journal_entries}
              hint={
                summary.average_journal_mood != null
                  ? `avg self-mood ${summary.average_journal_mood.toFixed(1)}/5`
                  : undefined
              }
            />
            <StatCard
              label="Wellness sessions"
              value={summary.total_wellness_sessions}
              hint={
                summary.average_exercise_rating != null
                  ? `avg rating ${summary.average_exercise_rating.toFixed(1)}/5`
                  : undefined
              }
            />
            <StatCard
              label="Current streak"
              value={`${summary.current_streak_days}d`}
              hint={`longest ${summary.longest_streak_days}d`}
            />
            <StatCard
              label="Voice analyses"
              value={summary.total_voice_analyses}
            />
            <StatCard
              label="Facial analyses"
              value={summary.total_facial_analyses}
            />
            <StatCard
              label="Active reminders"
              value={summary.active_reminders}
              hint={
                summary.unread_notifications > 0
                  ? `${summary.unread_notifications} unread`
                  : undefined
              }
            />
            <StatCard label="Active goals" value={summary.active_goals} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold uppercase text-slate-500">
                  Dominant signal
                </h2>
                <RiskBadge level={summary.latest_risk_level} />
              </div>
              {summary.dominant_emotion ? (
                <div>
                  <div className="text-4xl">
                    {EMOTION_EMOJI[summary.dominant_emotion] ?? '•'}
                  </div>
                  <div className="mt-2 text-lg font-medium">
                    {summary.dominant_emotion}
                  </div>
                  <div className="text-xs text-slate-500">
                    {summary.dominant_emotion_percent}% of {summary.total_emotion_events}{' '}
                    events
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-500 italic">
                  No signals yet. Try a chat check-in or short journal entry.
                </div>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
                Sentiment mix
              </h2>
              <SentimentBar summary={summary} />
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
                Mood trend
              </h2>
              {trends && trends.points.length > 0 ? (
                <>
                  <MoodSparkline points={trends.points} />
                  <div className="text-xs text-slate-500 mt-2 flex justify-between">
                    <span>
                      rolling 7d:{' '}
                      {trends.rolling_mood_7d != null
                        ? trends.rolling_mood_7d.toFixed(2)
                        : '—'}
                    </span>
                    <span>{momentumLabel}</span>
                  </div>
                </>
              ) : (
                <div className="text-sm text-slate-500 italic">
                  No trend data yet.
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
                Signal distribution
              </h2>
              {emotions && <EmotionDistribution counts={emotions.by_emotion} />}
            </div>
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
                Where signals came from
              </h2>
              {emotions && (
                <ul className="text-sm space-y-1">
                  {Object.entries(emotions.by_source)
                    .sort((a, b) => b[1] - a[1])
                    .map(([src, n]) => (
                      <li
                        key={src}
                        className="flex items-center justify-between"
                      >
                        <span className="capitalize">{src}</span>
                        <span className="text-slate-500">{n}</span>
                      </li>
                    ))}
                  {Object.keys(emotions.by_source).length === 0 && (
                    <li className="text-slate-500 italic">No sources yet.</li>
                  )}
                </ul>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
            <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
              Insights
            </h2>
            {insights && insights.highlights.length > 0 ? (
              <ul className="text-sm space-y-2 list-disc pl-5">
                {insights.highlights.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            ) : (
              <div className="text-sm text-slate-500 italic">
                Try a check-in, journal entry or wellness exercise to see
                patterns here.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
