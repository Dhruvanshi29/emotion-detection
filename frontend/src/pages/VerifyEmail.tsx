import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'

export default function VerifyEmailPage() {
  const [params] = useSearchParams()
  const [state, setState] = useState<'working' | 'done' | 'error'>('working')
  useEffect(() => { void api.post('/auth/email/verify/confirm', { token: params.get('token') || '' }).then(() => setState('done')).catch(() => setState('error')) }, [params])
  return <div className="mx-auto max-w-md px-4 py-12 text-center"><h1 className="text-2xl font-semibold mb-3">{state === 'working' ? 'Verifying your email…' : state === 'done' ? 'Email verified' : 'This link has expired'}</h1><p className="text-sm text-slate-600 mb-5">{state === 'done' ? 'Thank you. Your Saaya account is ready.' : state === 'error' ? 'Request a fresh link from your profile after signing in.' : 'This will only take a moment.'}</p>{state !== 'working' && <Link className="button button--primary" to="/login">Continue to Saaya</Link>}</div>
}
