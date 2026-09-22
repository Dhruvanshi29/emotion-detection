import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

type Summary = {
  id: string
  slug: string
  full_name: string
  title: string
  country_code: string
  city: string | null
  session_price_min: number | null
  session_price_max: number | null
  currency: string
  offers_online: boolean
  offers_in_person: boolean
  accepts_new_clients: boolean
  specializations: string[]
  languages: string[]
  verified: boolean
  verification_status: string
}

type ListResp = {
  items: Summary[]
  total: number
  skip: number
  limit: number
}

const SPECIALIZATIONS = [
  'anxiety',
  'burnout',
  'trauma',
  'grief',
  'anger',
  'addiction',
  'couples',
  'family_systems',
  'identity',
  'young_adults',
  'self_esteem',
  'depression',
  'cbt',
  'life_transitions',
  'acculturation',
  'men',
]

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'es', label: 'Español' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'gu', label: 'ગુજરાતી' },
  { code: 'mr', label: 'मराठी' },
  { code: 'zh', label: '中文' },
  { code: 'pt', label: 'Português' },
]

const COUNTRIES = [
  { code: '', label: 'Any' },
  { code: 'US', label: 'United States' },
  { code: 'IN', label: 'India' },
  { code: 'GB', label: 'United Kingdom' },
  { code: 'PT', label: 'Portugal' },
]

function price(t: Summary): string {
  if (t.session_price_min == null && t.session_price_max == null) return '—'
  const min = t.session_price_min ?? t.session_price_max
  const max = t.session_price_max ?? t.session_price_min
  if (min === max) return `${min} ${t.currency}`
  return `${min}–${max} ${t.currency}`
}

export default function TherapistsPage() {
  const [items, setItems] = useState<Summary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [q, setQ] = useState('')
  const [specialization, setSpecialization] = useState('')
  const [language, setLanguage] = useState('')
  const [country, setCountry] = useState('')
  const [modality, setModality] = useState('')
  const [acceptsNew, setAcceptsNew] = useState(false)
  const [verifiedOnly, setVerifiedOnly] = useState(true)
  const [order, setOrder] = useState('default')

  const params = useMemo(() => {
    const p = new URLSearchParams()
    if (q.trim()) p.set('q', q.trim())
    if (specialization) p.set('specialization', specialization)
    if (language) p.set('language', language)
    if (country) p.set('country', country)
    if (modality) p.set('modality', modality)
    if (acceptsNew) p.set('accepts_new_clients', 'true')
    if (!verifiedOnly) p.set('verified_only', 'false')
    if (order !== 'default') p.set('order', order)
    p.set('limit', '50')
    return p
  }, [q, specialization, language, country, modality, acceptsNew, verifiedOnly, order])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await api.get<ListResp>(`/therapists?${params.toString()}`)
      setItems(r.data.items)
      setTotal(r.data.total)
      setError(null)
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(err.response?.data?.detail || err.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [params])

  useEffect(() => {
    const h = window.setTimeout(() => void load(), 200)
    return () => window.clearTimeout(h)
  }, [load])

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-1">Find someone to talk to</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-2">
        Browse at your own pace. Results use only the preferences you choose —
        never AI ranking or a clinical referral.
      </p>
      <p className="text-xs italic text-slate-500 mb-6">
        The platform does not endorse, employ, or supervise listed
        professionals. Please independently verify credentials before contacting.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-6">
        <aside className="space-y-4">
          <input
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm"
            placeholder="Search name or title"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />

          <div>
            <label className="text-xs uppercase text-slate-500">Specialization</label>
            <select
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value)}
            >
              <option value="">Any</option>
              {SPECIALIZATIONS.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs uppercase text-slate-500">Language</label>
            <select
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="">Any</option>
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs uppercase text-slate-500">Country</label>
            <select
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            >
              {COUNTRIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs uppercase text-slate-500">Modality</label>
            <select
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              value={modality}
              onChange={(e) => setModality(e.target.value)}
            >
              <option value="">Any</option>
              <option value="online">Online</option>
              <option value="in_person">In person</option>
            </select>
          </div>

          <div>
            <label className="text-xs uppercase text-slate-500">Sort</label>
            <select
              className="mt-1 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-2 text-sm"
              value={order}
              onChange={(e) => setOrder(e.target.value)}
            >
              <option value="default">Suggested (accepts new first)</option>
              <option value="name">Name (A–Z)</option>
              <option value="price_asc">Price (low to high)</option>
              <option value="price_desc">Price (high to low)</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={acceptsNew}
              onChange={(e) => setAcceptsNew(e.target.checked)}
            />
            Accepts new clients
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={verifiedOnly}
              onChange={(e) => setVerifiedOnly(e.target.checked)}
            />
            Verified only
          </label>
        </aside>

        <section>
          {error && (
            <div className="mb-3 rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
              {error}
            </div>
          )}
          <div className="text-xs text-slate-500 mb-2">
            {loading ? 'Loading…' : `${total} result${total === 1 ? '' : 's'}`}
          </div>
          <ul className="space-y-3">
            {items.map((t) => (
              <li
                key={t.id}
                className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Link
                      to={`/therapists/${t.slug}`}
                      className="text-lg font-semibold hover:underline"
                    >
                      {t.full_name}
                    </Link>
                    <div className="text-sm text-slate-600 dark:text-slate-400">
                      {t.title}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {[t.city, t.country_code].filter(Boolean).join(', ')} · {price(t)}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    {t.verified ? (
                      <span className="text-[10px] uppercase rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200 px-2 py-0.5">
                        verified
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 px-2 py-0.5">
                        {t.verification_status}
                      </span>
                    )}
                    {t.accepts_new_clients ? (
                      <span className="text-[10px] uppercase rounded-full bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200 px-2 py-0.5">
                        accepting
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase rounded-full bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200 px-2 py-0.5">
                        waitlist
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {t.specializations.slice(0, 5).map((s) => (
                    <span
                      key={s}
                      className="text-[11px] rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5"
                    >
                      {s.replace(/_/g, ' ')}
                    </span>
                  ))}
                  <span className="text-[11px] text-slate-500 pl-1">
                    {t.languages.join(' · ')}
                  </span>
                  <span className="text-[11px] text-slate-500 pl-1">
                    {t.offers_online ? 'online' : ''}
                    {t.offers_online && t.offers_in_person ? ' · ' : ''}
                    {t.offers_in_person ? 'in person' : ''}
                  </span>
                </div>
              </li>
            ))}
            {!loading && items.length === 0 && (
              <li className="text-sm text-slate-500 italic">
                No therapists match these filters.
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  )
}
