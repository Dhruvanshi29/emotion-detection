import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { googleAuthConfigured } from '../lib/googleAuth'

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8, 'At least 8 characters'),
  mfa_code: z.string().regex(/^\d{6}$/, 'Use the 6-digit code').optional().or(z.literal('')),
})
type Form = z.infer<typeof schema>

export default function LoginPage() {
  const { login, loginWithGoogle } = useAuth()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: string } }
  const [err, setErr] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) })

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-semibold mb-2">Welcome back. Take your time.</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Your space is just as you left it. Sign in whenever you feel ready.
      </p>
      <form
        className="space-y-4"
        onSubmit={handleSubmit(async (data) => {
          setErr(null)
          try {
            await login(data.email, data.password, data.mfa_code || undefined)
            nav(loc.state?.from ?? '/chat', { replace: true })
          } catch (e: unknown) {
            const msg =
              (e as { response?: { data?: { detail?: string } } }).response
                ?.data?.detail ?? 'Login failed'
            setErr(msg)
          }
        })}
      >
        <div>
          <label className="block text-sm mb-1">Email</label>
          <input
            type="email"
            autoComplete="email"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
            {...register('email')}
          />
          {errors.email && (
            <p className="text-sm text-red-600 mt-1">{errors.email.message}</p>
          )}
        </div>
        <div>
          <label className="block text-sm mb-1">Authenticator code <span className="text-slate-400">(if enabled)</span></label>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="000000"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 tracking-[0.25em]"
            {...register('mfa_code')}
          />
          {errors.mfa_code && <p className="text-sm text-red-600 mt-1">{errors.mfa_code.message}</p>}
        </div>
        <div>
          <div className="flex items-center justify-between"><label className="block text-sm mb-1">Password</label><Link to="/forgot-password" className="text-xs text-indigo-600 hover:underline">Forgot password?</Link></div>
          <input
            type="password"
            autoComplete="current-password"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
            {...register('password')}
          />
          {errors.password && (
            <p className="text-sm text-red-600 mt-1">
              {errors.password.message}
            </p>
          )}
        </div>
        {err && <p className="text-sm text-red-600">{err}</p>}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md bg-indigo-600 text-white py-2 hover:bg-indigo-700 disabled:opacity-50"
        >
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      {googleAuthConfigured && (
        <>
          <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
            <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            or
            <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
          </div>
          <button
            type="button"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 py-2 hover:bg-slate-50 dark:hover:bg-slate-800"
            onClick={async () => {
              setErr(null)
              try {
                await loginWithGoogle()
                nav(loc.state?.from ?? '/chat', { replace: true })
              } catch (e: unknown) {
                const msg =
                  (e as { response?: { data?: { detail?: string } } }).response
                    ?.data?.detail ?? 'Google sign-in failed'
                setErr(msg)
              }
            }}
          >
            Continue with Google
          </button>
        </>
      )}
      <p className="text-sm text-slate-500 mt-6 text-center">
        No account?{' '}
        <Link to="/register" className="text-indigo-600 hover:underline">
          Create one
        </Link>
      </p>
    </div>
  )
}
