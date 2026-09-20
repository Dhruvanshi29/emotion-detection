import { lazy, Suspense, type ReactElement } from 'react'
import { Navigate, Route, Routes, Link, useNavigate } from 'react-router-dom'
import { useAuth } from './lib/auth'

const LoginPage = lazy(() => import('./pages/Login'))
const RegisterPage = lazy(() => import('./pages/Register'))
const ChatPage = lazy(() => import('./pages/Chat'))
const DashboardPage = lazy(() => import('./pages/Dashboard'))
const JournalPage = lazy(() => import('./pages/Journal'))
const VoicePage = lazy(() => import('./pages/Voice'))
const VideoPage = lazy(() => import('./pages/Video'))
const WellnessPage = lazy(() => import('./pages/Wellness'))
const TherapistsPage = lazy(() => import('./pages/Therapists'))
const TherapistProfilePage = lazy(() => import('./pages/TherapistProfile'))
const RemindersPage = lazy(() => import('./pages/Reminders'))
const MemoryPage = lazy(() => import('./pages/Memory'))
const PrivacyPage = lazy(() => import('./pages/Privacy'))
const ProfilePage = lazy(() => import('./pages/Profile'))

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8 text-center">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

function NavBar() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  return (
    <header className="border-b border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/70 backdrop-blur">
      <div className="mx-auto max-w-4xl flex items-center justify-between px-4 py-3">
        <Link to="/" className="font-semibold text-lg">
          Emotional Wellness
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          {user ? (
            <>
              <Link to="/dashboard" className="hover:underline">
                Dashboard
              </Link>
              <Link to="/chat" className="hover:underline">
                Chat
              </Link>
              <Link to="/journal" className="hover:underline">
                Journal
              </Link>
              <Link to="/voice" className="hover:underline">
                Voice
              </Link>
              <Link to="/video" className="hover:underline">
                Video
              </Link>
              <Link to="/wellness" className="hover:underline">
                Wellness
              </Link>
              <Link to="/therapists" className="hover:underline">
                Therapists
              </Link>
              <Link to="/reminders" className="hover:underline">
                Reminders
              </Link>
              <Link to="/memory" className="hover:underline">
                Memory
              </Link>
              <Link to="/privacy" className="hover:underline">
                Privacy
              </Link>
              <Link to="/profile" className="hover:underline">
                Profile
              </Link>
              <span className="text-slate-500">{user.email}</span>
              <button
                onClick={() => {
                  void logout().finally(() => nav('/login'))
                }}
                className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="hover:underline">
                Log in
              </Link>
              <Link
                to="/register"
                className="rounded-md bg-indigo-600 text-white px-3 py-1 hover:bg-indigo-700"
              >
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}

function Home() {
  const { user } = useAuth()
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <h1 className="text-4xl font-semibold tracking-tight mb-4">
        A calm space, whenever you need one.
      </h1>
      <p className="text-slate-600 dark:text-slate-400 mb-8">
        Text-first AI companion for check-ins, coping strategies, and gentle
        guidance. Not a replacement for professional care.
      </p>
      {user ? (
        <Link
          to="/chat"
          className="inline-block rounded-md bg-indigo-600 text-white px-5 py-2 hover:bg-indigo-700"
        >
          Open chat
        </Link>
      ) : (
        <div className="flex justify-center gap-3">
          <Link
            to="/register"
            className="rounded-md bg-indigo-600 text-white px-5 py-2 hover:bg-indigo-700"
          >
            Get started
          </Link>
          <Link
            to="/login"
            className="rounded-md border border-slate-300 dark:border-slate-700 px-5 py-2 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            I have an account
          </Link>
        </div>
      )}
    </div>
  )
}

function App() {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main>
        <Suspense fallback={<div className="p-8 text-center">Loading…</div>}>
          <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/chat"
            element={
              <RequireAuth>
                <ChatPage />
              </RequireAuth>
            }
          />
          <Route
            path="/journal"
            element={
              <RequireAuth>
                <JournalPage />
              </RequireAuth>
            }
          />
          <Route
            path="/voice"
            element={
              <RequireAuth>
                <VoicePage />
              </RequireAuth>
            }
          />
          <Route
            path="/video"
            element={
              <RequireAuth>
                <VideoPage />
              </RequireAuth>
            }
          />
          <Route
            path="/wellness"
            element={
              <RequireAuth>
                <WellnessPage />
              </RequireAuth>
            }
          />
          <Route
            path="/therapists"
            element={
              <RequireAuth>
                <TherapistsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/therapists/:slug"
            element={
              <RequireAuth>
                <TherapistProfilePage />
              </RequireAuth>
            }
          />
          <Route
            path="/reminders"
            element={
              <RequireAuth>
                <RemindersPage />
              </RequireAuth>
            }
          />
          <Route
            path="/memory"
            element={
              <RequireAuth>
                <MemoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/privacy"
            element={
              <RequireAuth>
                <PrivacyPage />
              </RequireAuth>
            }
          />
          <Route
            path="/profile"
            element={
              <RequireAuth>
                <ProfilePage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}

export default App
