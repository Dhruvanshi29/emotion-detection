import { lazy, Suspense, useState, type ReactElement } from 'react'
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import { useAuth } from './lib/auth'
import { useQuery } from '@tanstack/react-query'
import { api } from './lib/api'

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
const OnboardingPage = lazy(() => import('./pages/Onboarding'))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPassword'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPassword'))
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmail'))

type NavItem = { to: string; label: string; glyph: string; end?: boolean }

const primaryNav: NavItem[] = [
  { to: '/dashboard', label: 'Today', glyph: '⌂', end: true },
  { to: '/chat', label: 'Companion', glyph: '◌' },
  { to: '/journal', label: 'Journal', glyph: '✎' },
  { to: '/wellness', label: 'Wellness', glyph: '◇' },
]
const checkInNav: NavItem[] = [
  { to: '/voice', label: 'Voice check-in', glyph: '∿' },
  { to: '/video', label: 'Face check-in', glyph: '◎' },
]
const supportNav: NavItem[] = [
  { to: '/therapists', label: 'Find a therapist', glyph: '♡' },
  { to: '/reminders', label: 'Reminders', glyph: '◫' },
  { to: '/memory', label: 'Memory', glyph: '◈' },
]
const settingsNav: NavItem[] = [
  { to: '/privacy', label: 'Privacy & safety', glyph: '⌾' },
  { to: '/profile', label: 'Profile', glyph: '○' },
]

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className={`brand ${compact ? 'brand--compact' : ''}`} aria-label="Saaya home">
      <span className="brand-mark" aria-hidden="true"><i /></span>
      {!compact && <span className="brand-name">Saaya</span>}
    </Link>
  )
}

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingScreen />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return children
}

function LoadingScreen() {
  return (
    <div className="loading-screen" role="status" aria-live="polite">
      <span className="brand-mark brand-mark--pulse" aria-hidden="true"><i /></span>
      <p>Making space for you…</p>
    </div>
  )
}

function PublicLayout() {
  const { user } = useAuth()
  return (
    <div className="public-layout">
      <header className="public-header">
        <div className="public-header__inner">
          <Brand />
          <nav className="public-nav" aria-label="Public navigation">
            <a href="/#how-it-helps">How it helps</a>
            <a href="/#privacy">Privacy</a>
            {user ? (
              <Link className="button button--primary button--small" to="/dashboard">Open your space</Link>
            ) : (
              <><Link to="/login">Sign in</Link><Link className="button button--primary button--small" to="/register">Get started</Link></>
            )}
          </nav>
        </div>
      </header>
      <main><Outlet /></main>
      <footer className="public-footer">
        <Brand />
        <p>Emotional support for everyday life. Not a replacement for professional care.</p>
        <div><Link to="/privacy">Privacy</Link><span>·</span><Link to="/therapists">Professional support</Link></div>
      </footer>
    </div>
  )
}

function NavGroup({ title, items, collapsed }: { title: string; items: NavItem[]; collapsed: boolean }) {
  return (
    <div className="nav-group">
      {!collapsed && <p className="nav-group__label">{title}</p>}
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end} title={collapsed ? item.label : undefined} className={({ isActive }) => `app-nav__link ${isActive ? 'is-active' : ''}`}>
          <span className="app-nav__glyph" aria-hidden="true">{item.glyph}</span>
          {!collapsed && <span>{item.label}</span>}
        </NavLink>
      ))}
    </div>
  )
}

function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const name = user?.profile?.display_name?.trim() || user?.email?.split('@')[0] || 'friend'
  const initial = name.slice(0, 1).toUpperCase()
  const notifications = useQuery({
    queryKey: ['notifications', 'badge', user?.id],
    enabled: !!user,
    queryFn: async () => (await api.get<{ unread: number }>('/notifications?unread_only=true&limit=1')).data,
    refetchInterval: 30_000,
  })
  const unread = notifications.data?.unread ?? 0

  return (
    <div className={`app-shell ${collapsed ? 'app-shell--collapsed' : ''}`}>
      <aside className="app-sidebar">
        <div className="app-sidebar__top">
          <Brand compact={collapsed} />
          <button type="button" className="sidebar-toggle" onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>{collapsed ? '›' : '‹'}</button>
        </div>
        <nav className="app-nav" aria-label="Main navigation">
          <NavGroup title="Your space" items={primaryNav} collapsed={collapsed} />
          <NavGroup title="Check in" items={checkInNav} collapsed={collapsed} />
          <NavGroup title="Support" items={supportNav} collapsed={collapsed} />
          <NavGroup title="Settings" items={settingsNav} collapsed={collapsed} />
        </nav>
        <div className="sidebar-care-note">
          {!collapsed && <><span>Need urgent help?</span><p>Contact local emergency services or a crisis line in your area.</p></>}
          <span className="sidebar-care-note__icon" aria-hidden="true">+</span>
        </div>
        <div className="sidebar-user">
          <Link to="/profile" className="user-avatar" aria-label="Open profile">{initial}</Link>
          {!collapsed && <div className="sidebar-user__copy"><strong>{name}</strong><span>Your private space</span></div>}
          {!collapsed && <button type="button" className="icon-button" aria-label="Sign out" onClick={() => void logout().finally(() => navigate('/login'))}>↗</button>}
        </div>
      </aside>
      <div className="app-workspace">
        <header className="app-header">
          <div><p className="app-header__eyebrow">Your private wellbeing space</p><p className="app-header__welcome">Take what you need today, {name}.</p></div>
          <div className="app-header__actions">
            <span className="privacy-chip"><span aria-hidden="true">●</span> Private by design</span>
            <Link to="/reminders" className="icon-button notification-button" aria-label={unread ? `Open reminders, ${unread} unread` : 'Open reminders'}>◫{unread > 0 && <i />}</Link>
            <Link to="/chat" className="button button--primary button--small">Start a check-in</Link>
          </div>
        </header>
        <main className="app-content"><Suspense fallback={<PageSkeleton />}><Outlet /></Suspense></main>
      </div>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {[primaryNav[0], primaryNav[1], primaryNav[2], primaryNav[3], settingsNav[1]].map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => isActive ? 'is-active' : ''}><span aria-hidden="true">{item.glyph}</span><small>{item.label === 'Companion' ? 'Chat' : item.label}</small></NavLink>
        ))}
      </nav>
    </div>
  )
}

function PageSkeleton() {
  return <div className="page-skeleton" aria-label="Loading page"><div className="skeleton skeleton--title" /><div className="skeleton skeleton--copy" /><div className="skeleton-grid"><div className="skeleton skeleton--card" /><div className="skeleton skeleton--card" /></div></div>
}

function Home() {
  const { user } = useAuth()
  return (
    <>
      <section className="hero">
        <div className="hero__glow hero__glow--one" /><div className="hero__glow hero__glow--two" />
        <div className="hero__content">
          <span className="eyebrow"><i /> A gentler way to check in</span>
          <h1>Your feelings deserve<br /><em>room to breathe.</em></h1>
          <p>Saaya brings reflection, emotional insights, and grounded support into one calm, private space—available whenever you need it.</p>
          <div className="hero__actions">
            <Link className="button button--primary button--large" to={user ? '/dashboard' : '/register'}>{user ? 'Return to your space' : 'Begin your first check-in'} <span>→</span></Link>
            <Link className="button button--ghost button--large" to={user ? '/journal' : '/login'}>{user ? 'Open your journal' : 'I already have an account'}</Link>
          </div>
          <div className="hero__trust"><span>⌾ Your data stays under your control</span><span>◇ Designed with emotional safety in mind</span></div>
        </div>
        <div className="hero-visual" aria-label="An example emotional check-in">
          <div className="hero-visual__orbit hero-visual__orbit--outer" /><div className="hero-visual__orbit hero-visual__orbit--inner" />
          <div className="mood-card">
            <span className="mood-card__label">A moment for you</span><h2>How are you arriving?</h2><p>No right answer. Just notice what is here.</p>
            <div className="mood-scale">{['Heavy', 'Tender', 'Steady', 'Light'].map((mood, index) => <button key={mood} className={index === 2 ? 'is-selected' : ''}><i />{mood}</button>)}</div>
            <div className="mood-card__footer"><span>Today, 8:42 AM</span><strong>Continue gently →</strong></div>
          </div>
          <div className="floating-note floating-note--top"><span>7 day rhythm</span><strong>Showing up counts.</strong></div>
          <div className="floating-note floating-note--bottom"><i>∿</i><span><small>A calmer pattern</small><strong>Your evenings feel steadier</strong></span></div>
        </div>
      </section>
      <section className="approach" id="how-it-helps">
        <div className="section-heading"><span className="eyebrow"><i /> Support that meets you here</span><h2>One space. Many ways<br />to understand yourself.</h2></div>
        <div className="approach-grid">
          <article className="feature-card feature-card--sage"><span className="feature-card__number">01</span><i className="feature-card__icon">◌</i><h3>Talk it through</h3><p>A thoughtful AI companion for reflection—not diagnosis. Share at your own pace, without judgment.</p><Link to="/chat">Meet your companion <span>→</span></Link></article>
          <article className="feature-card feature-card--sand"><span className="feature-card__number">02</span><i className="feature-card__icon">✎</i><h3>Notice your patterns</h3><p>Journal freely and see gentle themes emerge across your moods, words, and daily rhythms.</p><Link to="/journal">Explore journaling <span>→</span></Link></article>
          <article className="feature-card feature-card--coral"><span className="feature-card__number">03</span><i className="feature-card__icon">◇</i><h3>Find what helps</h3><p>Small, evidence-informed practices matched to the way you are feeling in this moment.</p><Link to="/wellness">View wellness tools <span>→</span></Link></article>
        </div>
      </section>
      <section className="privacy-story" id="privacy">
        <div className="privacy-story__mark"><span className="brand-mark brand-mark--large"><i /></span></div>
        <div><span className="eyebrow eyebrow--light"><i /> Privacy is part of care</span><h2>What you share is yours.</h2><p>Emotional wellbeing is deeply personal. Saaya gives you clear consent controls, transparent activity history, and the ability to export or delete your data.</p></div>
        <div className="privacy-list"><span><i>✓</i>Granular camera, microphone, and memory controls</span><span><i>✓</i>No hidden use of your private reflections</span><span><i>✓</i>Export or delete your information at any time</span></div>
      </section>
      <section className="final-cta"><span className="eyebrow"><i /> Start where you are</span><h2>You do not have to have<br />the words yet.</h2><p>A quiet place to begin is enough.</p><Link className="button button--primary button--large" to={user ? '/dashboard' : '/register'}>Create your private space <span>→</span></Link></section>
    </>
  )
}

function NotFound() {
  return <div className="not-found"><span className="brand-mark brand-mark--large"><i /></span><p className="eyebrow">A small pause</p><h1>This path wandered off.</h1><p>The space you were looking for is not here, but your Saaya home is close by.</p><Link className="button button--primary" to="/dashboard">Return to today</Link></div>
}

export default function App() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route element={<PublicLayout />}><Route path="/" element={<Home />} /><Route path="/login" element={<LoginPage />} /><Route path="/register" element={<RegisterPage />} /><Route path="/forgot-password" element={<ForgotPasswordPage />} /><Route path="/reset-password" element={<ResetPasswordPage />} /><Route path="/verify-email" element={<VerifyEmailPage />} /></Route>
        <Route element={<RequireAuth><AppShell /></RequireAuth>}>
          <Route path="/onboarding" element={<OnboardingPage />} /><Route path="/dashboard" element={<DashboardPage />} /><Route path="/chat" element={<ChatPage />} /><Route path="/journal" element={<JournalPage />} /><Route path="/voice" element={<VoicePage />} /><Route path="/video" element={<VideoPage />} /><Route path="/wellness" element={<WellnessPage />} /><Route path="/therapists" element={<TherapistsPage />} /><Route path="/therapists/:slug" element={<TherapistProfilePage />} /><Route path="/reminders" element={<RemindersPage />} /><Route path="/memory" element={<MemoryPage />} /><Route path="/privacy" element={<PrivacyPage />} /><Route path="/profile" element={<ProfilePage />} /><Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
