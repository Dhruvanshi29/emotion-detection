import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../lib/api'

type Reminder = {
  id: string
  title: string
  message: string | null
  kind: string
  recurrence: string
  weekdays: number[] | null
  time_of_day: string
  timezone: string
  start_date: string | null
  end_date: string | null
  is_active: boolean
  next_fire_at: string | null
  last_fired_at: string | null
  fire_count: number
  created_at: string
  updated_at: string
}

type ReminderList = { items: Reminder[]; total: number }

type Notification = {
  id: string
  reminder_id: string | null
  kind: string
  channel: string
  title: string
  body: string | null
  status: string
  scheduled_for: string
  delivered_at: string | null
  read_at: string | null
  created_at: string
}

type NotificationList = {
  items: Notification[]
  total: number
  unread: number
}

const KINDS = [
  { value: 'chat_checkin', label: 'Chat check-in' },
  { value: 'journal', label: 'Journal prompt' },
  { value: 'exercise', label: 'Wellness exercise' },
  { value: 'hydration', label: 'Hydration' },
  { value: 'custom', label: 'Custom' },
]

const RECURRENCES = [
  { value: 'daily', label: 'Every day' },
  { value: 'weekly', label: 'Specific weekdays' },
  { value: 'once', label: 'One-time' },
]

const WEEKDAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
const WEEKDAY_FULL = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function browserTZ(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

function fmtWhen(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString()
}

export default function RemindersPage() {
  const dataQuery = useQuery({
    queryKey: ['reminders', 'overview'],
    queryFn: async () => {
      const [rl, nl] = await Promise.all([
        api.get<ReminderList>('/reminders'),
        api.get<NotificationList>('/notifications?limit=20'),
      ])
      return { reminders: rl.data.items, notifications: nl.data.items, unread: nl.data.unread }
    },
  })
  const reminders = dataQuery.data?.reminders ?? []
  const notifs = dataQuery.data?.notifications ?? []
  const unread = dataQuery.data?.unread ?? 0
  const loading = dataQuery.isPending
  const queryError = dataQuery.error as
    | { response?: { data?: { detail?: string } }; message?: string }
    | null
  const error = queryError
    ? queryError.response?.data?.detail || queryError.message || 'Failed to load'
    : null

  // Form state
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [kind, setKind] = useState('chat_checkin')
  const [recurrence, setRecurrence] = useState('daily')
  const [weekdays, setWeekdays] = useState<number[]>([0, 2, 4])
  const [timeOfDay, setTimeOfDay] = useState('09:00')
  const [tz, setTz] = useState(browserTZ())
  const [startDate, setStartDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  async function load() {
    await dataQuery.refetch()
  }

  const canSubmit = useMemo(() => {
    if (!title.trim() || !timeOfDay || !tz) return false
    if (recurrence === 'weekly' && weekdays.length === 0) return false
    if (recurrence === 'once' && !startDate) return false
    return true
  }, [title, timeOfDay, tz, recurrence, weekdays, startDate])

  async function submit() {
    setBusy(true)
    setFormError(null)
    try {
      const body: Record<string, unknown> = {
        title: title.trim(),
        message: message.trim() || null,
        kind,
        recurrence,
        time_of_day: timeOfDay,
        timezone: tz,
      }
      if (recurrence === 'weekly') body.weekdays = weekdays
      if (recurrence === 'once') body.start_date = startDate
      await api.post('/reminders', body)
      setTitle('')
      setMessage('')
      await load()
    } catch (e) {
      const err = e as { response?: { data?: { detail?: unknown } } }
      const d = err.response?.data?.detail
      setFormError(typeof d === 'string' ? d : 'Could not create reminder.')
    } finally {
      setBusy(false)
    }
  }

  async function toggleActive(r: Reminder) {
    await api.patch(`/reminders/${r.id}`, { is_active: !r.is_active })
    await load()
  }

  async function removeReminder(r: Reminder) {
    if (!window.confirm(`Delete "${r.title}"?`)) return
    await api.delete(`/reminders/${r.id}`)
    await load()
  }

  async function markRead(n: Notification) {
    await api.post(`/notifications/${n.id}/read`)
    await load()
  }

  function toggleWeekday(d: number) {
    setWeekdays((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort()
    )
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-1">Gentle reminders</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Gentle nudges for check-ins, journaling and wellness exercises.
        Timezone-aware; you can pause any reminder at any time.
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
              New reminder
            </h2>
            <div className="space-y-3">
              <input
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                placeholder="Title (e.g. Evening reflection)"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <textarea
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
                placeholder="Optional message"
                rows={2}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs uppercase text-slate-500">Kind</label>
                  <select
                    className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    {KINDS.map((k) => (
                      <option key={k.value} value={k.value}>
                        {k.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs uppercase text-slate-500">
                    Recurrence
                  </label>
                  <select
                    className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                    value={recurrence}
                    onChange={(e) => setRecurrence(e.target.value)}
                  >
                    {RECURRENCES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {recurrence === 'weekly' && (
                <div>
                  <label className="text-xs uppercase text-slate-500">
                    Weekdays
                  </label>
                  <div className="mt-1 flex gap-1">
                    {WEEKDAY_LABELS.map((lbl, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => toggleWeekday(i)}
                        className={
                          'w-9 h-9 rounded-full text-sm border ' +
                          (weekdays.includes(i)
                            ? 'bg-indigo-600 text-white border-indigo-600'
                            : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700')
                        }
                      >
                        {lbl}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {recurrence === 'once' && (
                <div>
                  <label className="text-xs uppercase text-slate-500">
                    Date
                  </label>
                  <input
                    type="date"
                    className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs uppercase text-slate-500">Time</label>
                  <input
                    type="time"
                    className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                    value={timeOfDay}
                    onChange={(e) => setTimeOfDay(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs uppercase text-slate-500">
                    Timezone
                  </label>
                  <input
                    className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
                    value={tz}
                    onChange={(e) => setTz(e.target.value)}
                  />
                </div>
              </div>

              {formError && (
                <div className="text-sm text-rose-600">{formError}</div>
              )}
              <button
                type="button"
                disabled={busy || !canSubmit}
                onClick={() => void submit()}
                className="rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm px-4 py-2"
              >
                {busy ? 'Saving…' : 'Add reminder'}
              </button>
            </div>
          </div>

          <h2 className="text-sm font-semibold uppercase text-slate-500 mb-3">
            Your reminders ({reminders.length})
          </h2>
          {loading ? (
            <div className="text-sm text-slate-500">Loading…</div>
          ) : reminders.length === 0 ? (
            <div className="text-sm text-slate-500 italic">
              No reminders yet. Create one above to start building a routine.
            </div>
          ) : (
            <ul className="space-y-2">
              {reminders.map((r) => (
                <li
                  key={r.id}
                  className={
                    'rounded-lg border p-3 flex items-start justify-between gap-3 ' +
                    (r.is_active
                      ? 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900'
                      : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 opacity-70')
                  }
                >
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{r.title}</div>
                    {r.message && (
                      <div className="text-xs text-slate-500 truncate">
                        {r.message}
                      </div>
                    )}
                    <div className="text-xs text-slate-500 mt-1">
                      {r.recurrence === 'weekly'
                        ? (r.weekdays ?? [])
                            .map((d) => WEEKDAY_FULL[d])
                            .join(', ')
                        : r.recurrence === 'once'
                          ? `Once on ${r.start_date ?? '—'}`
                          : 'Every day'}{' '}
                      · {r.time_of_day} {r.timezone}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                      Next: {fmtWhen(r.next_fire_at)} · fired {r.fire_count}×
                    </div>
                  </div>
                  <div className="flex flex-col gap-1 items-end">
                    <button
                      onClick={() => void toggleActive(r)}
                      className="text-[11px] uppercase rounded-full border border-slate-300 dark:border-slate-700 px-2 py-0.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      {r.is_active ? 'pause' : 'resume'}
                    </button>
                    <button
                      onClick={() => void removeReminder(r)}
                      className="text-[11px] uppercase rounded-full border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 px-2 py-0.5 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                    >
                      delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside>
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-sm font-semibold uppercase text-slate-500">
              Notifications
            </h2>
            {unread > 0 && (
              <span className="text-[10px] uppercase rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200 px-2 py-0.5">
                {unread} unread
              </span>
            )}
          </div>
          {notifs.length === 0 ? (
            <div className="text-sm text-slate-500 italic">Nothing yet.</div>
          ) : (
            <ul className="space-y-2">
              {notifs.map((n) => (
                <li
                  key={n.id}
                  className={
                    'rounded-lg border p-3 ' +
                    (n.read_at
                      ? 'border-slate-200 dark:border-slate-800 opacity-70'
                      : 'border-indigo-300 dark:border-indigo-700 bg-indigo-50/40 dark:bg-indigo-950/20')
                  }
                >
                  <div className="font-medium text-sm">{n.title}</div>
                  {n.body && (
                    <div className="text-xs text-slate-600 dark:text-slate-400 mt-0.5">
                      {n.body}
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[11px] text-slate-400">
                      {fmtWhen(n.scheduled_for)}
                    </span>
                    {!n.read_at && (
                      <button
                        onClick={() => void markRead(n)}
                        className="text-[11px] uppercase text-indigo-600 hover:underline"
                      >
                        mark read
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  )
}
