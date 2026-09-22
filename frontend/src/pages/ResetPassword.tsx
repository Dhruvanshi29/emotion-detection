import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'

export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return <div className="mx-auto max-w-md px-4 py-12"><h1 className="text-2xl font-semibold mb-2">Choose a new password</h1><p className="text-sm text-slate-600 mb-6">Use at least eight characters you do not use elsewhere.</p>{done ? <div className="rounded-lg bg-indigo-50 p-4 text-sm">Your password is updated. <Link className="text-indigo-700 underline" to="/login">Sign in to Saaya</Link>.</div> : <form className="space-y-4" onSubmit={async (e) => { e.preventDefault(); setError(null); try { await api.post('/auth/password/reset', { token: params.get('token') || '', new_password: password }); setDone(true) } catch { setError('This reset link is invalid or has expired.') } }}><label className="block text-sm">New password<input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2" /></label>{error && <p className="text-sm text-red-600">{error}</p>}<button className="w-full rounded-md bg-indigo-600 text-white py-2">Update password</button></form>}</div>
}
