import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'

type AvailabilitySlot = {
  weekday: number
  start_minute: number
  end_minute: number
}

type VerificationRead = {
  status: string
  license_number: string | null
  license_authority: string | null
  verified_at: string | null
  expires_at: string | null
  notes: string | null
}

type Detail = {
  id: string
  slug: string
  full_name: string
  title: string
  bio: string
  photo_url: string | null
  country_code: string
  city: string | null
  timezone: string | null
  session_price_min: number | null
  session_price_max: number | null
  currency: string
  offers_online: boolean
  offers_in_person: boolean
  accepts_new_clients: boolean
  specializations: string[]
  languages: string[]
  availability: AvailabilitySlot[]
  verification: VerificationRead | null
  verified: boolean
  verification_status: string
  contact_email: string | null
  website_url: string | null
  disclaimer: string
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const REPORT_KINDS = [
  { value: 'outdated_info', label: 'Outdated information' },
  { value: 'incorrect_contact', label: 'Incorrect contact details' },
  { value: 'not_practicing', label: 'No longer practicing' },
  { value: 'impersonation', label: 'Impersonation' },
  { value: 'other', label: 'Other' },
]

function fmtMinute(m: number): string {
  const h = Math.floor(m / 60)
  const mm = String(m % 60).padStart(2, '0')
  return `${String(h).padStart(2, '0')}:${mm}`
}

function fmtPrice(t: Detail): string {
  if (t.session_price_min == null && t.session_price_max == null) return '—'
  const min = t.session_price_min ?? t.session_price_max
  const max = t.session_price_max ?? t.session_price_min
  if (min === max) return `${min} ${t.currency}`
  return `${min}–${max} ${t.currency}`
}

export default function TherapistProfilePage() {
  const { slug } = useParams<{ slug: string }>()
  const profileQuery = useQuery({
    queryKey: ['therapist', slug],
    enabled: !!slug,
    queryFn: async () => {
      const r = await api.get<Detail>(`/therapists/${slug}`)
      return r.data
    },
  })
  const data = profileQuery.data ?? null
  const loading = profileQuery.isPending
  const queryError = profileQuery.error as
    | { response?: { status?: number; data?: { detail?: string } } }
    | null
  const error = queryError
    ? queryError.response?.status === 404
      ? 'Profile not found.'
      : queryError.response?.data?.detail || 'Failed to load'
    : null

  const [reporting, setReporting] = useState(false)
  const [reportKind, setReportKind] = useState('outdated_info')
  const [reportNotes, setReportNotes] = useState('')
  const [reportBusy, setReportBusy] = useState(false)
  const [reportMsg, setReportMsg] = useState<string | null>(null)

  async function submitReport() {
    if (!slug) return
    setReportBusy(true)
    setReportMsg(null)
    try {
      await api.post(`/therapists/${slug}/report`, {
        kind: reportKind,
        notes: reportNotes || null,
      })
      setReportMsg('Report submitted. Thank you — our team will review it.')
      setReportNotes('')
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } } }
      setReportMsg(err.response?.data?.detail || 'Could not submit report.')
    } finally {
      setReportBusy(false)
    }
  }

  if (loading) {
    return <div className="mx-auto max-w-4xl px-4 py-8 text-sm text-slate-500">Loading…</div>
  }
  if (error || !data) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-4 text-sm text-rose-800 dark:text-rose-200">
          {error || 'Unknown error'}
        </div>
        <Link to="/therapists" className="text-sm text-indigo-600 hover:underline mt-3 inline-block">
          ← Back to directory
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <Link to="/therapists" className="text-sm text-indigo-600 hover:underline">
        ← Back to directory
      </Link>

      <header className="mt-4 flex items-start gap-4">
        <div className="w-20 h-20 rounded-full bg-slate-200 dark:bg-slate-800 flex items-center justify-center text-2xl font-semibold text-slate-500">
          {data.full_name.slice(0, 1)}
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold">{data.full_name}</h1>
          <div className="text-slate-600 dark:text-slate-400">{data.title}</div>
          <div className="text-xs text-slate-500 mt-1">
            {[data.city, data.country_code].filter(Boolean).join(', ')}
            {data.timezone ? ` · ${data.timezone}` : ''}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="text-[10px] uppercase rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 px-2 py-0.5">
              verified · {data.verification?.license_authority ?? 'authority'}
            </span>
            {data.accepts_new_clients ? (
              <span className="text-[10px] uppercase rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200 px-2 py-0.5">
                accepting new clients
              </span>
            ) : (
              <span className="text-[10px] uppercase rounded-full bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200 px-2 py-0.5">
                waitlist
              </span>
            )}
            <span className="text-[10px] uppercase rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5">
              {fmtPrice(data)} / session
            </span>
          </div>
        </div>
      </header>

      <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 p-3 text-xs text-amber-900 dark:text-amber-200">
        {data.disclaimer}
      </div>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase text-slate-500">About</h2>
        <p className="mt-2 text-sm whitespace-pre-wrap leading-relaxed">{data.bio}</p>
      </section>

      <section className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="text-sm font-semibold uppercase text-slate-500">Specializations</h2>
          <div className="mt-2 flex flex-wrap gap-1">
            {data.specializations.map((s) => (
              <span key={s} className="text-xs rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-1">
                {s.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-sm font-semibold uppercase text-slate-500">Languages</h2>
          <div className="mt-2 flex flex-wrap gap-1">
            {data.languages.map((l) => (
              <span key={l} className="text-xs rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-1">
                {l}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase text-slate-500">Modality</h2>
        <div className="mt-2 text-sm">
          {data.offers_online ? '✓ Online' : '— Online'}
          <span className="mx-3 text-slate-400">|</span>
          {data.offers_in_person ? '✓ In person' : '— In person'}
        </div>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase text-slate-500">Availability (local to therapist)</h2>
        {data.availability.length === 0 ? (
          <div className="text-sm text-slate-500 mt-2 italic">Not published.</div>
        ) : (
          <ul className="mt-2 text-sm space-y-1">
            {data.availability.map((s, i) => (
              <li key={i}>
                <span className="inline-block w-12 font-medium">{WEEKDAYS[s.weekday]}</span>
                {fmtMinute(s.start_minute)} – {fmtMinute(s.end_minute)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold uppercase text-slate-500">Contact</h2>
        <ul className="mt-2 text-sm space-y-1">
          {data.website_url && (
            <li>
              <a
                href={data.website_url}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-600 hover:underline"
              >
                {data.website_url}
              </a>
            </li>
          )}
          {data.contact_email && (
            <li>
              <a href={`mailto:${data.contact_email}`} className="text-indigo-600 hover:underline">
                {data.contact_email}
              </a>
            </li>
          )}
          {!data.website_url && !data.contact_email && (
            <li className="text-slate-500 italic">No public contact details.</li>
          )}
        </ul>
      </section>

      <section className="mt-8 rounded-lg border border-slate-200 dark:border-slate-800 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">See something wrong?</h2>
          <button
            className="text-xs rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800"
            onClick={() => setReporting((v) => !v)}
          >
            {reporting ? 'Cancel' : 'Report profile'}
          </button>
        </div>
        {reporting && (
          <div className="mt-3 space-y-2">
            <select
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              value={reportKind}
              onChange={(e) => setReportKind(e.target.value)}
            >
              {REPORT_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
            <textarea
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              rows={3}
              placeholder="Optional details (max 2000 characters)"
              value={reportNotes}
              maxLength={2000}
              onChange={(e) => setReportNotes(e.target.value)}
            />
            <button
              className="rounded-md bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-sm px-3 py-1.5"
              disabled={reportBusy}
              onClick={() => void submitReport()}
            >
              {reportBusy ? 'Submitting…' : 'Submit report'}
            </button>
            {reportMsg && (
              <div className="text-xs text-slate-600 dark:text-slate-400">{reportMsg}</div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
