import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 300_000,
})

const ACCESS_KEY = 'ew_access_token'
const REFRESH_KEY = 'ew_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Refresh-on-401 with single-flight
let refreshPromise: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null
  try {
    const r = await axios.post(
      `${API_BASE}/auth/refresh`,
      { refresh_token: refresh },
      { timeout: 15_000 },
    )
    const access = r.data.access_token as string
    const newRefresh = (r.data.refresh_token as string) || refresh
    setTokens(access, newRefresh)
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
