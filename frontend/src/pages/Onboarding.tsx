import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

const GOALS = [
  ['reduce_stress', 'Feel less overwhelmed'],
  ['manage_anxiety', 'Manage anxious moments'],
  ['lift_mood', 'Support my mood'],
  ['sleep_better', 'Sleep more peacefully'],
  ['general_wellbeing', 'Understand myself better'],
] as const

export default function OnboardingPage() {
  const { refreshMe } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [goals, setGoals] = useState<string[]>([])
  const [mic, setMic] = useState(false)
  const [camera, setCamera] = useState(false)
  const [memory, setMemory] = useState(true)
  const [busy, setBusy] = useState(false)

  async function finish() {
    setBusy(true)
    try {
      await api.patch('/users/me', {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        age_confirmed: true,
        memory_enabled: memory,
        mic_consent: mic,
        camera_consent: camera,
      })
      await Promise.all(goals.map((kind) => api.post('/wellness/goals', { kind }).catch(() => undefined)))
      await refreshMe()
      navigate('/dashboard', { replace: true })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-widest text-indigo-600">A gentle beginning · {step + 1} of 2</p>
        <h1 className="text-3xl font-semibold mt-2">Shape Saaya around you</h1>
        <p className="text-slate-600 dark:text-slate-400 mt-2">Nothing here is permanent. You can change every choice later.</p>
      </div>
      {step === 0 ? (
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <h2 className="text-xl font-semibold">What would feel supportive?</h2>
          <p className="text-sm text-slate-500 mt-1 mb-5">Choose any that resonate—or choose none.</p>
          <div className="grid sm:grid-cols-2 gap-3">
            {GOALS.map(([value, label]) => (
              <button key={value} type="button" onClick={() => setGoals((items) => items.includes(value) ? items.filter((item) => item !== value) : [...items, value])} className={`text-left rounded-lg border p-4 ${goals.includes(value) ? 'border-indigo-600 bg-indigo-50 dark:bg-indigo-950/30' : 'border-slate-200 dark:border-slate-700'}`}>
                <span className="text-sm font-medium">{label}</span>
              </button>
            ))}
          </div>
          <button type="button" className="mt-6 rounded-md bg-indigo-600 text-white px-5 py-2" onClick={() => setStep(1)}>Continue gently</button>
        </section>
      ) : (
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
          <h2 className="text-xl font-semibold">You stay in control</h2>
          <p className="text-sm text-slate-500">These optional permissions are off unless you choose them.</p>
          <label className="flex items-start gap-3 rounded-lg bg-slate-50 dark:bg-slate-800 p-4"><input type="checkbox" checked={memory} onChange={(e) => setMemory(e.target.checked)} /><span><strong className="block text-sm">Helpful memory</strong><small className="text-slate-500">Remember details you intentionally share so conversations feel connected.</small></span></label>
          <label className="flex items-start gap-3 rounded-lg bg-slate-50 dark:bg-slate-800 p-4"><input type="checkbox" checked={mic} onChange={(e) => setMic(e.target.checked)} /><span><strong className="block text-sm">Voice check-ins</strong><small className="text-slate-500">Allow microphone access only when you start a voice check-in.</small></span></label>
          <label className="flex items-start gap-3 rounded-lg bg-slate-50 dark:bg-slate-800 p-4"><input type="checkbox" checked={camera} onChange={(e) => setCamera(e.target.checked)} /><span><strong className="block text-sm">Face check-ins</strong><small className="text-slate-500">Process coarse signals in your browser; raw video is not uploaded.</small></span></label>
          <div className="flex gap-3 pt-2"><button type="button" className="rounded-md border border-slate-300 px-4 py-2" onClick={() => setStep(0)}>Back</button><button type="button" disabled={busy} className="rounded-md bg-indigo-600 text-white px-5 py-2 disabled:opacity-50" onClick={() => void finish()}>{busy ? 'Preparing your space…' : 'Enter my space'}</button></div>
        </section>
      )}
    </div>
  )
}
