import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

type VoiceAnalyzeResponse = {
  voice_analysis_id: string
  emotion_event_id: string | null
  transcript: string
  language: string | null
  duration_seconds: number | null
  word_count: number | null
  speech_rate_wpm: number | null
  features_available: boolean
  energy_rms: number | null
  pause_ratio: number | null
  stt_provider: string | null
  stt_model: string | null
  dominant_emotion: string | null
  sentiment: string | null
  confidence: number | null
  scores: Record<string, number>
  signals: string[]
  emotion_provider: string | null
  emotion_model: string | null
}

type VoiceHistory = {
  id: string
  transcript: string
  duration_seconds: number | null
  speech_rate_wpm: number | null
  created_at: string
}

const EMOJI: Record<string, string> = {
  joy: '😊',
  sadness: '😢',
  anger: '😠',
  fear: '😨',
  surprise: '😮',
  disgust: '🤢',
  neutral: '😐',
}

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

export default function VoicePage() {
  const { user } = useAuth()
  const [recording, setRecording] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<VoiceAnalyzeResponse | null>(null)
  const [level, setLevel] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [history, setHistory] = useState<VoiceHistory[]>([])

  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef<number | null>(null)
  const startedAtRef = useRef<number>(0)
  const timerRef = useRef<number | null>(null)

  const consent = user?.preferences.mic_consent === true

  useEffect(() => {
    return () => stopEverything()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (consent) void api.get<VoiceHistory[]>('/emotion/voice?limit=8').then((r) => setHistory(r.data)).catch(() => {})
  }, [consent, result])

  function stopEverything() {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    try {
      recRef.current?.stop()
    } catch {
      /* ignore */
    }
    recRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    analyserRef.current = null
  }

  async function startRecording() {
    setError(null)
    setResult(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const mime =
        MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : MediaRecorder.isTypeSupported('audio/webm')
            ? 'audio/webm'
            : ''

      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.onstop = () => {
        void handleStopped(rec.mimeType || 'audio/webm')
      }
      rec.start()
      recRef.current = rec

      // Level meter via AudioContext.
      const AC: typeof AudioContext =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext
      const ctx = new AC()
      audioCtxRef.current = ctx
      const src = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      src.connect(analyser)
      analyserRef.current = analyser

      const buf = new Uint8Array(analyser.frequencyBinCount)
      const loop = () => {
        if (!analyserRef.current) return
        analyserRef.current.getByteTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128
          sum += v * v
        }
        const rms = Math.sqrt(sum / buf.length)
        setLevel(Math.min(1, rms * 3))
        rafRef.current = requestAnimationFrame(loop)
      }
      rafRef.current = requestAnimationFrame(loop)

      startedAtRef.current = Date.now()
      setElapsed(0)
      timerRef.current = window.setInterval(() => {
        setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000))
      }, 250)
      setRecording(true)
    } catch (e) {
      setError(
        e instanceof Error
          ? `Microphone unavailable: ${e.message}`
          : 'Microphone unavailable',
      )
    }
  }

  function stopRecording() {
    if (!recRef.current) return
    setRecording(false)
    try {
      recRef.current.stop()
    } catch {
      /* ignore */
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    setLevel(0)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }

  async function handleStopped(mimeType: string) {
    const blob = new Blob(chunksRef.current, { type: mimeType })
    chunksRef.current = []
    if (blob.size === 0) {
      setError('No audio captured.')
      return
    }
    const ext =
      mimeType.includes('wav')
        ? 'wav'
        : mimeType.includes('ogg')
          ? 'ogg'
          : mimeType.includes('mp4') || mimeType.includes('m4a')
            ? 'm4a'
            : 'webm'
    const form = new FormData()
    form.append('file', blob, `recording.${ext}`)
    form.append('source', 'adhoc')

    setAnalyzing(true)
    setError(null)
    try {
      const r = await api.post<VoiceAnalyzeResponse>('/emotion/audio', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(
        err.response?.data?.detail || err.message || 'Failed to analyze audio.',
      )
    } finally {
      setAnalyzing(false)
    }
  }

  if (!consent) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12">
        <h1 className="text-2xl font-semibold mb-3">Speak only if it feels comfortable</h1>
        <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/40 dark:border-amber-800 p-5 text-sm">
          <p className="mb-3">
            Voice analysis is opt-in. Enable <strong>microphone consent</strong>{' '}
            in your profile to record a short voice note. We derive tentative
            signals (like tone, energy, pauses) from what you say — we never
            store the raw audio.
          </p>
          <Link
            to="/profile"
            className="inline-block rounded-md bg-indigo-600 text-white px-4 py-2 hover:bg-indigo-700"
          >
            Manage consent in Profile
          </Link>
        </div>
      </div>
    )
  }

  const emoji = result?.dominant_emotion ? EMOJI[result.dominant_emotion] ?? '💬' : null

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-2">A quiet voice check-in</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        A few words are enough. Pause whenever you need. These are gentle
        signals, not a diagnosis, and raw audio is never stored.
      </p>

      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 mb-6">
        <div className="flex items-center gap-4">
          {!recording ? (
            <button
              onClick={startRecording}
              disabled={analyzing}
              className="rounded-full bg-rose-600 text-white w-14 h-14 flex items-center justify-center text-2xl hover:bg-rose-700 disabled:opacity-50"
              aria-label="Start recording"
            >
              ●
            </button>
          ) : (
            <button
              onClick={stopRecording}
              className="rounded-full bg-slate-700 text-white w-14 h-14 flex items-center justify-center text-2xl hover:bg-slate-800"
              aria-label="Stop recording"
            >
              ■
            </button>
          )}
          <div className="flex-1">
            <div className="h-3 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-rose-500 transition-[width] duration-100"
                style={{ width: `${Math.round(level * 100)}%` }}
              />
            </div>
            <div className="mt-1 text-xs text-slate-500 flex justify-between">
              <span>
                {recording
                  ? 'Recording…'
                  : analyzing
                    ? 'Analyzing…'
                    : 'Ready'}
              </span>
              <span>
                {recording || elapsed > 0
                  ? `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(
                      elapsed % 60,
                    ).padStart(2, '0')}`
                  : ''}
              </span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}

      {result && (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="text-4xl">{emoji}</div>
            <div>
              <div className="font-semibold capitalize">
                {result.dominant_emotion || 'unknown'}{' '}
                <span className="text-sm text-slate-500 font-normal">
                  · {result.sentiment || '—'}
                </span>
              </div>
              <div className="text-xs text-slate-500">
                confidence {fmt(result.confidence, 2)}
              </div>
            </div>
          </div>

          <div>
            <div className="text-xs uppercase text-slate-500 mb-1">
              Transcript
            </div>
            <blockquote className="italic border-l-4 border-slate-300 dark:border-slate-700 pl-3 text-sm">
              {result.transcript || <span className="text-slate-500">—</span>}
            </blockquote>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <Stat label="Duration" value={result.duration_seconds ? `${fmt(result.duration_seconds, 1)}s` : '—'} />
            <Stat label="Words" value={result.word_count ?? '—'} />
            <Stat label="Rate (wpm)" value={fmt(result.speech_rate_wpm, 0)} />
            <Stat
              label="Energy (RMS)"
              value={result.features_available ? fmt(result.energy_rms, 3) : 'n/a'}
            />
            <Stat
              label="Pause ratio"
              value={
                result.features_available && result.pause_ratio !== null
                  ? fmt(result.pause_ratio, 2)
                  : 'n/a'
              }
            />
            <Stat label="Language" value={result.language || '—'} />
          </div>

          {result.signals.length > 0 && (
            <div>
              <div className="text-xs uppercase text-slate-500 mb-1">
                Signals
              </div>
              <ul className="list-disc pl-5 text-sm space-y-1">
                {result.signals.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="text-xs text-slate-500">
            STT via{' '}
            <span className="font-mono">
              {result.stt_provider}
              {result.stt_model ? `/${result.stt_model}` : ''}
            </span>
            {' · '}
            emotion via{' '}
            <span className="font-mono">
              {result.emotion_provider}
              {result.emotion_model ? `/${result.emotion_model}` : ''}
            </span>
          </div>
        </div>
      )}
      <section className="mt-8">
        <h2 className="font-semibold">Recent voice moments</h2>
        <p className="mt-1 text-sm text-slate-500">Raw recordings are never saved. You can revisit only the private transcript and derived details.</p>
        <div className="mt-3 space-y-2">
          {history.length === 0 && <p className="text-sm italic text-slate-500">No earlier voice check-ins.</p>}
          {history.map((item) => <article key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900"><p className="line-clamp-2">{item.transcript}</p><small className="mt-1 block text-slate-500">{new Date(item.created_at).toLocaleString()} · {item.duration_seconds ? `${item.duration_seconds.toFixed(0)}s` : 'duration unavailable'} · {item.speech_rate_wpm ? `${item.speech_rate_wpm.toFixed(0)} wpm` : 'rate unavailable'}</small></article>)}
        </div>
      </section>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-slate-200 dark:border-slate-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  )
}
