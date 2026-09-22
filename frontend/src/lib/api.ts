import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 300_000,
  withCredentials: true,
})

const ACCESS_KEY = 'ew_access_token'
const REFRESH_KEY = 'ew_refresh_token'
const CSRF_KEY = 'saaya_csrf_token'
let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}
export function setTokens(access: string, refresh: string) {
  setAccessToken(access)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  else localStorage.removeItem(REFRESH_KEY)
}
export function setAccessToken(access: string) {
  accessToken = access
  // Browser sessions keep access in memory and refresh in an HttpOnly cookie.
  // Remove any credentials left by an older Saaya build.
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}
export function setCsrfToken(token?: string | null) {
  if (token) localStorage.setItem(CSRF_KEY, token)
}
export function getCsrfToken(): string | null {
  return localStorage.getItem(CSRF_KEY)
}
export function clearTokens() {
  accessToken = null
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(CSRF_KEY)
}

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const csrfCookie = document.cookie
    .split('; ')
    .find((row) => row.startsWith('saaya_csrf='))
    ?.split('=')[1]
  const csrf = csrfCookie ? decodeURIComponent(csrfCookie) : getCsrfToken()
  if (csrf && ['post', 'put', 'patch', 'delete'].includes((config.method || '').toLowerCase())) {
    config.headers['X-CSRF-Token'] = csrf
  }
  return config
})

// Refresh-on-401 with single-flight
let refreshPromise: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  try {
    const csrfCookie = document.cookie
      .split('; ')
      .find((row) => row.startsWith('saaya_csrf='))
      ?.split('=')[1]
    const csrf = csrfCookie ? decodeURIComponent(csrfCookie) : getCsrfToken()
    const r = await axios.post(`${API_BASE}/auth/browser/refresh`, {}, {
      timeout: 15_000,
      withCredentials: true,
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    })
    const access = r.data.access_token as string
    setAccessToken(access)
    setCsrfToken(r.data.csrf_token)
    return access
  } catch {
    clearTokens()
    return null
  }
}

api.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const original = error.config
    if (
      error.response?.status === 401 &&
      original &&
      !original.__isRetry &&
      !original.url?.includes('/auth/')
    ) {
      original.__isRetry = true
      if (!refreshPromise) refreshPromise = tryRefresh()
      const newAccess = await refreshPromise
      refreshPromise = null
      if (newAccess) {
        original.headers.Authorization = `Bearer ${newAccess}`
        return api.request(original)
      }
    }
    return Promise.reject(error)
  },
)
