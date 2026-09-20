import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from './api'
import { getGoogleIdentityToken } from './googleAuth'

export type UserProfile = {
  display_name: string | null
  timezone: string
  age_confirmed: boolean
  dob_year: number | null
}

export type UserPreferences = {
  notification_email: boolean
  theme: string
  memory_enabled: boolean
  mic_consent: boolean
  camera_consent: boolean
}

export type UserRead = {
  id: string
  email: string
  is_active: boolean
  is_verified: boolean
  created_at: string
  profile: UserProfile
  preferences: UserPreferences
}

type AuthState = {
  user: UserRead | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithGoogle: () => Promise<void>
  register: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
  logoutAll: () => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
  refreshMe: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshMe = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null)
      return
    }
    try {
      const r = await api.get<UserRead>('/users/me')
      setUser(r.data)
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    ;(async () => {
      await refreshMe()
      setLoading(false)
    })()
  }, [refreshMe])

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await api.post('/auth/login', { email, password })
      setTokens(r.data.access_token, r.data.refresh_token)
      await refreshMe()
    },
    [refreshMe],
  )

  const register = useCallback(
    async (email: string, password: string, displayName?: string) => {
      await api.post('/auth/register', {
        email,
        password,
        display_name: displayName,
      })
      await login(email, password)
    },
    [login],
  )

  const loginWithGoogle = useCallback(async () => {
    const idToken = await getGoogleIdentityToken()
    const r = await api.post('/auth/google', { id_token: idToken })
    setTokens(r.data.access_token, r.data.refresh_token)
    await refreshMe()
  }, [refreshMe])

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken()
    try {
      if (refreshToken) {
        await api.post('/auth/logout', { refresh_token: refreshToken })
      }
    } finally {
      clearTokens()
      setUser(null)
    }
  }, [])

  const logoutAll = useCallback(async () => {
    try {
      await api.post('/auth/logout-all')
    } catch {
      // Even if the call fails (already invalidated, etc.), still clear locally.
    }
    clearTokens()
    setUser(null)
  }, [])

  const changePassword = useCallback(
    async (current: string, next: string) => {
      const r = await api.post('/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      setTokens(r.data.access_token, r.data.refresh_token)
      await refreshMe()
    },
    [refreshMe],
  )

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      loginWithGoogle,
      register,
      logout,
      logoutAll,
      changePassword,
      refreshMe,
    }),
    [
      user,
      loading,
      login,
      loginWithGoogle,
      register,
      logout,
      logoutAll,
      changePassword,
      refreshMe,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
