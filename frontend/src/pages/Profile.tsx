import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { getGoogleIdentityToken, googleAuthConfigured } from '../lib/googleAuth'
import { disablePush, enablePush, pushAvailability } from '../lib/push'

const schema = z.object({
  display_name: z.string().max(80).optional().or(z.literal('')),
  timezone: z.string().max(64).optional(),
  theme: z.enum(['system', 'light', 'dark']).optional(),
  memory_enabled: z.boolean().optional(),
  mic_consent: z.boolean().optional(),
  camera_consent: z.boolean().optional(),
  notification_email: z.boolean().optional(),
  age_confirmed: z.boolean().optional(),
  dob_year: z
    .union([z.string(), z.number()])
    .transform((v) => (v === '' || v === undefined ? undefined : Number(v)))
    .optional(),
})
type Form = z.infer<typeof schema>

const passwordSchema = z
  .object({
    current: z.string().min(1, 'Current password required'),
    next: z.string().min(8, 'At least 8 characters'),
    confirm: z.string().min(1, 'Confirm new password'),
  })
  .refine((v) => v.next === v.confirm, {
    message: 'Passwords do not match',
    path: ['confirm'],
  })
  .refine((v) => v.current !== v.next, {
    message: 'New password must be different',
    path: ['next'],
  })
type PasswordForm = z.infer<typeof passwordSchema>

type DeviceSession = {
  family_id: string
  created_at: string
  last_seen_at: string
  expires_at: string
  user_agent: string | null
  ip: string | null
}

type MFASetup = { secret: string; otpauth_uri: string }

export default function ProfilePage() {
  const { user, refreshMe, logoutAll, changePassword } = useAuth()
  const [status, setStatus] = useState<string | null>(null)
  const [pwStatus, setPwStatus] = useState<string | null>(null)
  const [pwError, setPwError] = useState<string | null>(null)
  const [logoutBusy, setLogoutBusy] = useState(false)
  const [sessions, setSessions] = useState<DeviceSession[]>([])
  const [verifyStatus, setVerifyStatus] = useState<string | null>(null)
  const [mfaSetup, setMfaSetup] = useState<MFASetup | null>(null)
  const [mfaCode, setMfaCode] = useState('')
  const [mfaPassword, setMfaPassword] = useState('')
  const [securityStatus, setSecurityStatus] = useState<string | null>(null)
  const [pushAvailable, setPushAvailable] = useState(false)
  const [pushStatus, setPushStatus] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<Form>()
  const {
    register: registerPw,
    handleSubmit: handlePwSubmit,
    reset: resetPw,
    formState: {
      errors: pwErrors,
      isSubmitting: pwSubmitting,
    },
  } = useForm<PasswordForm>()

  useEffect(() => {
    if (user) {
      reset({
        display_name: user.profile.display_name ?? '',
        timezone: user.profile.timezone,
        theme: (user.preferences.theme as 'system' | 'light' | 'dark') ?? 'system',
        memory_enabled: user.preferences.memory_enabled,
        mic_consent: user.preferences.mic_consent,
        camera_consent: user.preferences.camera_consent,
        notification_email: user.preferences.notification_email,
        age_confirmed: user.profile.age_confirmed,
        dob_year: user.profile.dob_year ?? undefined,
      })
    }
  }, [user, reset])

  useEffect(() => {
    if (user) void api.get<DeviceSession[]>('/auth/sessions').then((r) => setSessions(r.data)).catch(() => setSessions([]))
  }, [user])

  useEffect(() => {
    if (user) void pushAvailability().then(setPushAvailable).catch(() => setPushAvailable(false))
  }, [user])

  if (!user) return null

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold mb-2">Your space, your way</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Adjust only what matters to you. Everything here can be changed later.
      </p>
      <form
        className="space-y-5"
        onSubmit={handleSubmit(async (data) => {
          setStatus(null)
          const payload = schema.parse(data)
          const body: Record<string, unknown> = { ...payload }
          if (body.display_name === '') body.display_name = null
          await api.patch('/users/me', body)
          await refreshMe()
          setStatus('Saved.')
        })}
      >
        <section className="space-y-3">
          <h2 className="font-medium">Profile</h2>
          <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 dark:bg-slate-800 p-3">
            <div><span className="block text-sm font-medium">Email {user.is_verified ? 'verified' : 'not yet verified'}</span><small className="text-slate-500">{user.email}</small></div>
            {!user.is_verified && <button type="button" className="rounded-md border border-slate-300 px-3 py-1.5 text-xs" onClick={async () => { await api.post('/auth/email/verify/request'); setVerifyStatus('Verification email requested.') }}>Send verification</button>}
          </div>
          {verifyStatus && <p className="text-xs text-green-700">{verifyStatus}</p>}
          <div>
            <label className="block text-sm mb-1">Display name</label>
            <input
              type="text"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
              {...register('display_name')}
            />
          </div>
          <div>
            <label className="block text-sm mb-1">Timezone</label>
            <input
              type="text"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
              {...register('timezone')}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex items-center gap-2">
              <input type="checkbox" {...register('age_confirmed')} />
              <span className="text-sm">I am 18 or older</span>
            </label>
            <div>
              <label className="block text-sm mb-1">Birth year</label>
              <input
                type="number"
                min={1900}
                max={2100}
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
                {...register('dob_year')}
              />
            </div>
          </div>
        </section>

        <section className="space-y-3">
          <h2 className="font-medium">Preferences</h2>
          <div>
            <label className="block text-sm mb-1">Theme</label>
            <select
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
              {...register('theme')}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" {...register('memory_enabled')} />
            <span className="text-sm">Remember our conversations</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" {...register('mic_consent')} />
            <span className="text-sm">Allow microphone (future voice)</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" {...register('camera_consent')} />
            <span className="text-sm">Allow camera (future facial cues)</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" {...register('notification_email')} />
            <span className="text-sm">Email me gentle reminders</span>
          </label>
          {pushAvailable && <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p className="text-sm font-medium">Browser reminders</p><p className="mt-1 text-xs text-slate-500">Optional notifications on this device. The reminder text is sent only through your browser's push service.</p><div className="mt-2 flex gap-3"><button type="button" className="text-sm text-indigo-600" onClick={async () => { try { await enablePush(); setPushStatus('Browser reminders enabled on this device.') } catch (error) { setPushStatus(error instanceof Error ? error.message : 'Could not enable browser reminders.') } }}>Enable on this device</button><button type="button" className="text-sm text-slate-500" onClick={async () => { await disablePush(); setPushStatus('Browser reminders disabled on this device.') }}>Disable</button></div>{pushStatus && <p className="mt-2 text-xs text-slate-600">{pushStatus}</p>}</div>}
        </section>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={isSubmitting}
            className="rounded-md bg-indigo-600 text-white px-5 py-2 hover:bg-indigo-700 disabled:opacity-50"
          >
            {isSubmitting ? 'Saving…' : 'Save'}
          </button>
          {status && <span className="text-sm text-green-600">{status}</span>}
        </div>
      </form>

      <section className="mt-10 border-t border-slate-200 dark:border-slate-800 pt-8 space-y-4">
        <h2 className="text-lg font-semibold">Security</h2>

        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <div className="flex items-start justify-between gap-4">
            <div><h3 className="font-medium">Authenticator verification</h3><p className="mt-1 text-sm text-slate-500">Add a six-digit code from your authenticator app when signing in.</p></div>
            <span className={`rounded-full px-2 py-1 text-xs ${user.mfa_enabled ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`}>{user.mfa_enabled ? 'On' : 'Off'}</span>
          </div>
          {!user.mfa_enabled && !mfaSetup && <div className="mt-3 flex gap-2"><input type="password" value={mfaPassword} onChange={(e) => setMfaPassword(e.target.value)} placeholder="Current password" autoComplete="current-password" className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /><button type="button" disabled={!mfaPassword} className="rounded-md border border-slate-300 px-3 py-2 text-sm disabled:opacity-50" onClick={async () => { setSecurityStatus(null); const r = await api.post<MFASetup>('/auth/mfa/setup', { password: mfaPassword }); setMfaPassword(''); setMfaSetup(r.data) }}>Set up authenticator</button></div>}
          {mfaSetup && !user.mfa_enabled && <div className="mt-4 space-y-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><p className="text-sm">Add this setup key to your authenticator app:</p><code className="block break-all rounded bg-white p-2 text-sm dark:bg-slate-900">{mfaSetup.secret}</code><a className="text-sm text-indigo-600 underline" href={mfaSetup.otpauth_uri}>Open in an authenticator app</a><div className="flex gap-2"><input value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code" className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /><button type="button" disabled={mfaCode.length !== 6} className="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-50" onClick={async () => { await api.post('/auth/mfa/confirm', { code: mfaCode }); setMfaSetup(null); setMfaCode(''); await refreshMe(); setSecurityStatus('Authenticator verification is now on.') }}>Confirm</button></div></div>}
          {user.mfa_enabled && <div className="mt-3 space-y-2"><div className="flex gap-2"><input type="password" value={mfaPassword} onChange={(e) => setMfaPassword(e.target.value)} placeholder="Current password" className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /><input value={mfaCode} onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" placeholder="6-digit code" className="w-36 rounded-md border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900" /></div><button type="button" className="text-sm text-red-600" onClick={async () => { await api.delete('/auth/mfa', { data: { password: mfaPassword, code: mfaCode } }); setMfaPassword(''); setMfaCode(''); await refreshMe(); setSecurityStatus('Authenticator verification is now off.') }}>Turn off authenticator verification</button></div>}
          {googleAuthConfigured && <button type="button" className="mt-4 block text-sm text-indigo-600" onClick={async () => { const idToken = await getGoogleIdentityToken(); await api.post('/auth/google/link', { id_token: idToken }); await refreshMe(); setSecurityStatus('Google account linked securely.') }}>Link this account with Google</button>}
          {securityStatus && <p className="mt-3 text-sm text-emerald-700">{securityStatus}</p>}
        </div>

        <form
          className="space-y-3"
          onSubmit={handlePwSubmit(async (data) => {
            setPwError(null)
            setPwStatus(null)
            try {
              await changePassword(data.current, data.next)
              resetPw({ current: '', next: '', confirm: '' })
              setPwStatus('Password updated. Other sessions have been signed out.')
            } catch (e: unknown) {
              const err = e as { response?: { data?: { detail?: string } } }
              setPwError(
                err.response?.data?.detail ?? 'Unable to update password.',
              )
            }
          })}
        >
          <h3 className="font-medium">Change password</h3>
          <div>
            <label className="block text-sm mb-1">Current password</label>
            <input
              type="password"
              autoComplete="current-password"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
              {...registerPw('current')}
            />
            {pwErrors.current && (
              <p className="text-xs text-red-600 mt-1">{pwErrors.current.message}</p>
            )}
          </div>
          <div>
            <label className="block text-sm mb-1">New password</label>
            <input
              type="password"
              autoComplete="new-password"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
              {...registerPw('next')}
            />
            {pwErrors.next && (
              <p className="text-xs text-red-600 mt-1">{pwErrors.next.message}</p>
            )}
          </div>
          <div>
            <label className="block text-sm mb-1">Confirm new password</label>
            <input
              type="password"
              autoComplete="new-password"
              className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
              {...registerPw('confirm')}
            />
            {pwErrors.confirm && (
              <p className="text-xs text-red-600 mt-1">{pwErrors.confirm.message}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={pwSubmitting}
              className="rounded-md bg-slate-800 text-white px-5 py-2 hover:bg-slate-700 disabled:opacity-50"
            >
              {pwSubmitting ? 'Updating…' : 'Update password'}
            </button>
            {pwStatus && <span className="text-sm text-green-600">{pwStatus}</span>}
            {pwError && <span className="text-sm text-red-600">{pwError}</span>}
          </div>
        </form>

        <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
          <h3 className="font-medium">Active sessions</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 mb-3">Review devices that can refresh access to your account.</p>
          <div className="space-y-2 mb-5">
            {sessions.length === 0 && <p className="text-sm text-slate-500">No active refresh sessions found.</p>}
            {sessions.map((session) => <div key={session.family_id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 dark:bg-slate-800 p-3"><div className="min-w-0"><strong className="block truncate text-sm">{session.user_agent || 'Unknown browser'}</strong><small className="text-slate-500">Last active {new Date(session.last_seen_at).toLocaleString()} · {session.ip || 'IP unavailable'}</small></div><button type="button" className="text-xs text-red-600" onClick={async () => { await api.delete(`/auth/sessions/${session.family_id}`); setSessions((items) => items.filter((item) => item.family_id !== session.family_id)) }}>Revoke</button></div>)}
          </div>

          <h3 className="font-medium">Sign out everywhere</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 mb-3">
            Revoke sessions on all your devices. You'll need to sign in again.
          </p>
          <button
            type="button"
            disabled={logoutBusy}
            onClick={async () => {
              if (!confirm('Sign out from all devices?')) return
              setLogoutBusy(true)
              try {
                await logoutAll()
                window.location.href = '/login'
              } finally {
                setLogoutBusy(false)
              }
            }}
            className="rounded-md border border-red-500 text-red-600 px-5 py-2 hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-50"
          >
            {logoutBusy ? 'Signing out…' : 'Log out of all sessions'}
          </button>
        </div>
      </section>
    </div>
  )
}
