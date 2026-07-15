/** Google sign-in via Firebase Auth, loaded lazily.
 *
 * The firebase SDK (~40KB gz) must never enter the main bundle — CI's
 * budget gates `index-*.js` — so both modules are dynamic imports; Vite
 * splits them into a chunk fetched only when someone actually clicks
 * "Continue with Google". Popup (not redirect): the app is served on the
 * Firebase Hosting domain, so the popup is first-party, and Hosting's
 * reserved /__/auth/* helpers are handled before our Cloud Run rewrite.
 */

export async function signInWithGoogle(
  config: Record<string, string>,
): Promise<string> {
  const { initializeApp, getApps } = await import("firebase/app");
  const { getAuth, GoogleAuthProvider, signInWithPopup } = await import(
    "firebase/auth"
  );
  const app = getApps()[0] ?? initializeApp(config);
  const auth = getAuth(app);
  const provider = new GoogleAuthProvider();
  const credential = await signInWithPopup(auth, provider);
  return credential.user.getIdToken();
}
