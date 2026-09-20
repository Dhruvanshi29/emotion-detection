import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

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

export default function ProfilePage() {
  const { user, refreshMe, logoutAll, changePassword } = useAuth()
  const [status, setStatus] = useState<string | null>(null)
  const [pwStatus, setPwStatus] = useState<string | null>(null)
  const [pwError, setPwError] = useState<string | null>(null)
  const [logoutBusy, setLogoutBusy] = useState(false)
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

  if (!user) return null

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold mb-6">Your profile</h1>
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
