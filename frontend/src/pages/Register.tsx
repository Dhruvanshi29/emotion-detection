import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8, 'At least 8 characters'),
  display_name: z.string().max(80).optional(),
  dob_year: z.number().int().min(1900).max(new Date().getFullYear() - 18),
  age_confirmed: z.literal(true, { error: 'You must confirm you are 18 or older' }),
})
type Form = z.infer<typeof schema>

export default function RegisterPage() {
  const { register: doRegister } = useAuth()
  const nav = useNavigate()
  const [err, setErr] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema) })

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="text-2xl font-semibold mb-2">A calm space of your own.</h1>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Begin gently. You can shape your preferences and privacy choices later.
      </p>
      <form
        className="space-y-4"
        onSubmit={handleSubmit(async (data) => {
          setErr(null)
          try {
            await doRegister(data.email, data.password, data.display_name, data.dob_year)
            nav('/onboarding', { replace: true })
          } catch (e: unknown) {
            const msg =
              (e as { response?: { data?: { detail?: string } } }).response
                ?.data?.detail ?? 'Registration failed'
            setErr(msg)
          }
        })}
      >
        <div>
          <label htmlFor="register-name" className="block text-sm mb-1">Display name (optional)</label>
          <input
            id="register-name"
            type="text"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
            {...register('display_name')}
          />
        </div>
        <div>
          <label htmlFor="register-birth-year" className="block text-sm mb-1">Birth year</label>
          <input
            id="register-birth-year"
            type="number"
            inputMode="numeric"
            autoComplete="bday-year"
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
            {...register('dob_year', { valueAsNumber: true })}
          />
          {errors.dob_year && <p className="text-sm text-red-600 mt-1">You must be at least 18 to use Saaya.</p>}
        </div>
        <label className="flex items-start gap-2 rounded-lg bg-slate-50 dark:bg-slate-800 p-3">
          <input type="checkbox" className="mt-1" {...register('age_confirmed')} />
          <span className="text-sm">I confirm that I am 18 or older and understand Saaya is not emergency or medical care.</span>
        </label>
        {errors.age_confirmed && <p className="text-sm text-red-600">{errors.age_confirmed.message}</p>}
        <div>
          <label htmlFor="register-email" className="block text-sm mb-1">Email</label>
          <input
            id="register-email"
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
          <label htmlFor="register-password" className="block text-sm mb-1">Password</label>
          <input
            id="register-password"
            type="password"
            autoComplete="new-password"
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
          {isSubmitting ? 'Preparing your space…' : 'Create my private space'}
        </button>
      </form>
      <p className="text-sm text-slate-500 mt-6 text-center">
        Already a member?{' '}
        <Link to="/login" className="text-indigo-600 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  )
}
