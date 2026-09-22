import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

const EMOTIONS = [
  'joy',
  'sadness',
  'anger',
  'fear',
  'surprise',
  'disgust',
  'neutral',
] as const
type Emotion = (typeof EMOTIONS)[number]

type FacialAnalyzeResponse = {
  facial_analysis_id: string
  emotion_event_id: string | null
  sample_count: number
  duration_seconds: number | null
  faces_detected_ratio: number | null
  dominant_emotion: string
  sentiment: string
  confidence: number
  scores: Record<string, number>
  signals: string[]
  model_provider: string | null
  model_name: string | null
}

type FacialHistory = FacialAnalyzeResponse & { id: string; created_at: string }

const EMOJI: Record<string, string> = {
  joy: '😊',
  sadness: '😢',
  anger: '😠',
  fear: '😨',
  surprise: '😮',
  disgust: '🤢',
  neutral: '😐',
}

type FrameSignal = {
  faceLikely: boolean
  brightness: number
  motion: number
  skinRatio: number
}

type NativeFaceDetector = { detect: (source: HTMLVideoElement) => Promise<unknown[]> }

// Runs entirely in the browser — no pixels ever leave the device.
function analyzeFrame(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  prev: Uint8ClampedArray | null,
): { signal: FrameSignal; data: Uint8ClampedArray } {
  const img = ctx.getImageData(0, 0, w, h)
  const d = img.data
  let sumY = 0
  let sumSkin = 0
  let sumMotion = 0
  let pixels = 0
  const stride = 4 * 4 // sample every 4th pixel horizontally
  for (let i = 0; i < d.length; i += stride) {
    const r = d[i]
    const g = d[i + 1]
    const b = d[i + 2]
    const y = 0.299 * r + 0.587 * g + 0.114 * b
    sumY += y
    // Rough skin-tone heuristic (RGB thresholds); tuned to reject pure grayscale.
    if (
      r > 60 &&
      g > 40 &&
      b > 20 &&
      r > g &&
      r > b &&
      Math.abs(r - g) > 15 &&
      r - b > 15
    ) {
      sumSkin += 1
    }
    if (prev) {
      sumMotion += Math.abs(y - (prev[i] * 0.299 + prev[i + 1] * 0.587 + prev[i + 2] * 0.114))
    }
    pixels += 1
  }
  const brightness = sumY / pixels / 255
  const skinRatio = sumSkin / pixels
  const motion = prev ? sumMotion / pixels / 255 : 0
  const faceLikely = brightness > 0.15 && skinRatio > 0.03
  return { signal: { faceLikely, brightness, motion, skinRatio }, data: d }
}

function aggregate(samples: FrameSignal[]): {
  scores: Record<Emotion, number>
  signals: string[]
  facesDetectedRatio: number
} {
  const facesDetectedRatio =
    samples.length === 0
      ? 0
      : samples.filter((s) => s.faceLikely).length / samples.length
  const avgMotion =
    samples.reduce((a, s) => a + s.motion, 0) / Math.max(1, samples.length)
  const avgBrightness =
    samples.reduce((a, s) => a + s.brightness, 0) / Math.max(1, samples.length)
  const avgSkin =
    samples.reduce((a, s) => a + s.skinRatio, 0) / Math.max(1, samples.length)

  // Coarse heuristic — this is intentionally NOT a diagnostic model.
  // Higher engagement (motion + presence) → joy/surprise weighting.
  // Low presence → neutral-heavy.
  const presence = Math.min(1, facesDetectedRatio + avgSkin)
  const engagement = Math.min(1, avgMotion * 6)

  const raw: Record<Emotion, number> = {
    joy: 0.15 + 0.35 * presence * (1 - engagement * 0.4),
    sadness: 0.05 + 0.15 * (1 - avgBrightness),
    anger: 0.03 + 0.12 * engagement,
    fear: 0.03 + 0.08 * (1 - presence),
    surprise: 0.03 + 0.35 * engagement,
    disgust: 0.02,
    neutral: 0.4 - 0.3 * presence,
  }

  // Nudge toward neutral when we barely saw a face.
  if (facesDetectedRatio < 0.2) {
    raw.neutral += 0.4
    for (const k of EMOTIONS) if (k !== 'neutral') raw[k] *= 0.6
  }

  const total = EMOTIONS.reduce((a, k) => a + raw[k], 0)
  const scores = Object.fromEntries(
    EMOTIONS.map((k) => [k, +(raw[k] / total).toFixed(4)]),
  ) as Record<Emotion, number>

  const signals: string[] = []
  if (facesDetectedRatio > 0.6) signals.push('face-visible-most-of-session')
  else if (facesDetectedRatio > 0.2) signals.push('face-visible-intermittently')
  else signals.push('face-rarely-detected')
  if (engagement > 0.5) signals.push('elevated-motion')
  else if (engagement < 0.1) signals.push('very-still')
  if (avgBrightness < 0.2) signals.push('low-light-conditions')

  return { scores, signals, facesDetectedRatio }
}

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toFixed(digits)
}

const SAMPLE_MS = 500
const DEFAULT_SECONDS = 15

export default function VideoPage() {
  const { user } = useAuth()
  const [status, setStatus] = useState<'idle' | 'running' | 'analyzing'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<FacialAnalyzeResponse | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [previewMeter, setPreviewMeter] = useState({ face: 0, motion: 0 })
  const [history, setHistory] = useState<FacialHistory[]>([])

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const samplerRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const startedAtRef = useRef<number>(0)
  const samplesRef = useRef<FrameSignal[]>([])
  const prevPixelsRef = useRef<Uint8ClampedArray | null>(null)
  const detectorRef = useRef<NativeFaceDetector | null>(null)

  const consent = user?.preferences.camera_consent === true

  const stopEverything = useCallback(() => {
    if (samplerRef.current !== null) {
      window.clearInterval(samplerRef.current)
      samplerRef.current = null
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    prevPixelsRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  useEffect(() => {
    return () => stopEverything()
  }, [stopEverything])

  useEffect(() => {
    if (consent) void api.get<FacialHistory[]>('/emotion/face?limit=8').then((r) => setHistory(r.data)).catch(() => {})
  }, [consent, result])

  async function start() {
    setError(null)
    setResult(null)
    samplesRef.current = []
    prevPixelsRef.current = null
    try {
      const Detector = (window as unknown as { FaceDetector?: new (options?: { fastMode?: boolean; maxDetectedFaces?: number }) => NativeFaceDetector }).FaceDetector
      detectorRef.current = Detector ? new Detector({ fastMode: true, maxDetectedFaces: 1 }) : null
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 320 }, height: { ideal: 240 } },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }

      startedAtRef.current = Date.now()
      setElapsed(0)
      setStatus('running')

      timerRef.current = window.setInterval(() => {
        const secs = Math.floor((Date.now() - startedAtRef.current) / 1000)
        setElapsed(secs)
      }, 250)

      samplerRef.current = window.setInterval(async () => {
        const video = videoRef.current
        const canvas = canvasRef.current
        if (!video || !canvas) return
        const w = 160
        const h = 120
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) return
        try {
          ctx.drawImage(video, 0, 0, w, h)
        } catch {
          return
        }
        const { signal, data } = analyzeFrame(ctx, w, h, prevPixelsRef.current)
        if (detectorRef.current) {
          try {
            signal.faceLikely = (await detectorRef.current.detect(video)).length > 0
          } catch {
            detectorRef.current = null
          }
        }
        prevPixelsRef.current = data
        samplesRef.current.push(signal)
        setPreviewMeter({
          face: signal.faceLikely ? 1 : signal.skinRatio * 4,
          motion: Math.min(1, signal.motion * 6),
        })
      }, SAMPLE_MS)
    } catch (e) {
      setError(
        e instanceof Error
          ? `Camera unavailable: ${e.message}`
          : 'Camera unavailable',
      )
      setStatus('idle')
    }
  }

  async function stopAndSubmit() {
    if (status !== 'running') return
    const durationSec = (Date.now() - startedAtRef.current) / 1000
    const samples = samplesRef.current.slice()
    setStatus('analyzing')
    stopEverything()

    if (samples.length === 0) {
      setError('No samples captured.')
      setStatus('idle')
      return
    }

    const agg = aggregate(samples)
    const body = {
      source: 'adhoc',
      sample_count: samples.length,
      duration_seconds: +durationSec.toFixed(2),
      faces_detected_ratio: +agg.facesDetectedRatio.toFixed(3),
      scores: agg.scores,
      signals: agg.signals,
      model_provider: detectorRef.current ? 'browser-face-detector' : 'browser-heuristic',
      model_name: detectorRef.current ? 'native-presence-plus-signals-v1' : 'browser-v1',
    }
    try {
      const r = await api.post<FacialAnalyzeResponse>('/emotion/video', body)
      setResult(r.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(
        err.response?.data?.detail || err.message || 'Failed to submit signals.',
      )
    } finally {
      setStatus('idle')
    }
  }

  if (!consent) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12">
        <h1 className="text-2xl font-semibold mb-3">A check-in on your terms</h1>
        <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/40 dark:border-amber-800 p-5 text-sm">
          <p className="mb-3">
            Facial analysis is opt-in. Enable <strong>camera consent</strong>{' '}
            in your profile to use this check-in. All inference happens
            on-device — <strong>no video or images are ever uploaded.</strong>{' '}
            Only aggregated signals (like face presence, motion, and a coarse
            expression distribution) are sent to the server.
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

  const emoji = result?.dominant_emotion
    ? EMOJI[result.dominant_emotion] ?? '💬'
    : null

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold mb-2">A quiet face check-in</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Look at the camera for ~{DEFAULT_SECONDS}s. We derive tentative signals
        on-device — <strong>your video never leaves this browser</strong>.
        These are gentle signals, not a diagnosis.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-black aspect-video flex items-center justify-center">
          <video
            ref={videoRef}
            playsInline
            muted
            className={`w-full h-full object-cover ${status === 'running' ? '' : 'opacity-40'}`}
          />
          <canvas ref={canvasRef} className="hidden" />
        </div>
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-col gap-4">
          <div>
            <div className="text-xs uppercase text-slate-500 mb-1">
              Face presence
            </div>
            <div className="h-3 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-[width] duration-150"
                style={{ width: `${Math.min(100, Math.round(previewMeter.face * 100))}%` }}
              />
            </div>
          </div>
          <div>
            <div className="text-xs uppercase text-slate-500 mb-1">
              Motion
            </div>
            <div className="h-3 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-rose-500 transition-[width] duration-150"
                style={{ width: `${Math.min(100, Math.round(previewMeter.motion * 100))}%` }}
              />
            </div>
          </div>
          <div className="text-sm text-slate-500">
            {status === 'running'
              ? `Recording… ${elapsed}s`
              : status === 'analyzing'
                ? 'Submitting signals…'
                : 'Ready'}
          </div>
          <div className="mt-auto flex gap-2">
            {status === 'idle' && (
              <button
                onClick={start}
                className="rounded-md bg-indigo-600 text-white px-4 py-2 hover:bg-indigo-700"
              >
                Start
              </button>
            )}
            {status === 'running' && (
              <button
                onClick={stopAndSubmit}
                className="rounded-md bg-slate-700 text-white px-4 py-2 hover:bg-slate-800"
              >
                Stop & analyze
              </button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-rose-300 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 p-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-6 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="text-4xl">{emoji}</div>
            <div>
              <div className="font-semibold capitalize">
                {result.dominant_emotion}{' '}
                <span className="text-sm text-slate-500 font-normal">
                  · {result.sentiment}
                </span>
              </div>
              <div className="text-xs text-slate-500">
                confidence {fmt(result.confidence, 2)} · {result.sample_count}{' '}
                samples · face seen{' '}
                {fmt((result.faces_detected_ratio ?? 0) * 100, 0)}% of the time
              </div>
            </div>
          </div>

          <div>
            <div className="text-xs uppercase text-slate-500 mb-2">
              Distribution
            </div>
            <div className="space-y-1">
              {EMOTIONS.map((k) => {
                const v = result.scores[k] ?? 0
                return (
                  <div key={k} className="flex items-center gap-2 text-sm">
                    <div className="w-20 capitalize text-slate-500">{k}</div>
                    <div className="flex-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                      <div
                        className="h-full bg-indigo-500"
                        style={{ width: `${Math.round(v * 100)}%` }}
                      />
                    </div>
                    <div className="w-12 text-right text-xs text-slate-500">
                      {(v * 100).toFixed(0)}%
                    </div>
                  </div>
                )
              })}
            </div>
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
            Model:{' '}
            <span className="font-mono">
              {result.model_provider}
              {result.model_name ? `/${result.model_name}` : ''}
            </span>{' '}
            · duration {fmt(result.duration_seconds, 1)}s
          </div>
          <div className="text-xs italic text-slate-500">
            These are approximate, tentative signals — not a diagnosis.
          </div>
        </div>
      )}
      <section className="mt-8">
        <h2 className="font-semibold">Recent face check-ins</h2>
        <p className="mt-1 text-sm text-slate-500">Only aggregated signals are kept—never photos or video.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {history.length === 0 && <p className="text-sm italic text-slate-500">No earlier face check-ins.</p>}
          {history.map((item) => <article key={item.id} className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"><div className="flex items-center gap-2"><span className="text-2xl" aria-hidden>{EMOJI[item.dominant_emotion] ?? '😐'}</span><strong className="capitalize">{item.dominant_emotion}</strong></div><small className="mt-1 block text-slate-500">{new Date(item.created_at).toLocaleString()} · face present {fmt((item.faces_detected_ratio ?? 0) * 100, 0)}%</small></article>)}
        </div>
      </section>
    </div>
  )
}
