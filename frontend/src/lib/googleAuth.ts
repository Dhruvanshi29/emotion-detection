const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
}

export const googleAuthConfigured = Boolean(
  firebaseConfig.apiKey &&
    firebaseConfig.authDomain &&
    firebaseConfig.projectId &&
    firebaseConfig.appId,
)

export async function getGoogleIdentityToken(): Promise<string> {
  if (!googleAuthConfigured) {
    throw new Error('Google sign-in is not configured')
  }
  const [{ getApp, getApps, initializeApp }, authModule] = await Promise.all([
    import('firebase/app'),
    import('firebase/auth'),
  ])
  const app = getApps().length ? getApp() : initializeApp(firebaseConfig)
  const auth = authModule.getAuth(app)
  const provider = new authModule.GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  const credential = await authModule.signInWithPopup(auth, provider)
  try {
    return await credential.user.getIdToken()
  } finally {
    // The application owns its own short-lived session after the exchange;
    // do not leave a second long-lived Firebase browser session behind.
    await authModule.signOut(auth)
  }
}
