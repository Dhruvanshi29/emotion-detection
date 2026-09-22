import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  return <div className="mx-auto max-w-md px-4 py-12"><h1 className="text-2xl font-semibold mb-2">Let’s help you back in</h1><p className="text-sm text-slate-600 mb-6">Enter your email and we’ll send a private reset link if an account exists.</p>{sent ? <div className="rounded-lg bg-indigo-50 p-4 text-sm">Check your inbox when you are ready. <Link className="text-indigo-700 underline" to="/login">Return to sign in</Link></div> : <form className="space-y-4" onSubmit={async (e) => { e.preventDefault(); await api.post('/auth/password/forgot', { email }); setSent(true) }}><label className="block text-sm">Email<input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2" /></label><button className="w-full rounded-md bg-indigo-600 text-white py-2">Send reset link</button></form>}</div>
}
