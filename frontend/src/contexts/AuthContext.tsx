/**
 * Authentication context using MSAL for Azure Entra ID.
 *
 * Shows a branded login page with "Entrar com Microsoft" button.
 * After authentication, fetches user profile and provides auth state.
 */
import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { loginRequest } from '@/lib/msal-config';
import { apiClient, setTokenProvider } from '@/lib/api';

interface UserProfile {
  email: string;
  name: string;
  role: 'admin' | 'consultor';
}

interface AuthContextValue {
  user: UserProfile | null;
  isAdmin: boolean;
  isLoading: boolean;
  getAccessToken: () => Promise<string | null>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isAdmin: false,
  isLoading: true,
  getAccessToken: async () => null,
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

// ---------------------------------------------------------------------------
// Login Page — Procurement Garage brand identity
// ---------------------------------------------------------------------------

function LoginPage() {
  const { instance, inProgress } = useMsal();
  const [loginError, setLoginError] = useState<string | null>(null);
  const isLoggingIn = inProgress !== InteractionStatus.None;

  const handleLogin = () => {
    setLoginError(null);
    instance.loginRedirect(loginRequest).catch((err) => {
      console.error('Login failed:', err);
      setLoginError(err?.message || 'Falha ao iniciar login');
    });
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'grid',
        placeItems: 'center',
        background: 'linear-gradient(135deg, #0e0330 0%, #1c0957 35%, #180847 65%, #0e0330 100%)',
        overflow: 'hidden',
      }}
    >
      {/* Decorative gradient orbs */}
      <div style={{
        position: 'absolute', top: '-20%', right: '-10%',
        width: 600, height: 600, borderRadius: '50%', opacity: 0.2,
        background: 'radial-gradient(circle, #0693e3 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '-15%', left: '-5%',
        width: 500, height: 500, borderRadius: '50%', opacity: 0.15,
        background: 'radial-gradient(circle, #9b51e0 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{ position: 'relative', zIndex: 10, width: 400, maxWidth: 'calc(100vw - 32px)' }}>
        {/* Main card */}
        <div style={{
          background: '#fff',
          borderRadius: 16,
          padding: '40px 36px 32px',
          boxShadow: '0 25px 60px rgba(0,0,0,0.35), 0 0 80px rgba(6,147,227,0.1)',
        }}>
          {/* Brand header */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{
              width: 56, height: 56, margin: '0 auto 20px',
              borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'linear-gradient(135deg, #0693e3 0%, #9b51e0 100%)',
              boxShadow: '0 8px 24px rgba(6,147,227,0.3)',
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h1 style={{ fontSize: 22, fontWeight: 600, color: '#32373c', letterSpacing: '-0.02em', margin: 0 }}>
              Spend.AI
            </h1>
            <p style={{ fontSize: 13, color: '#829ab1', marginTop: 6 }}>
              Classificação inteligente de gastos corporativos
            </p>
          </div>

          {/* Gradient divider */}
          <div style={{
            height: 1, marginBottom: 32, borderRadius: 1,
            background: 'linear-gradient(90deg, transparent 0%, #0693e3 30%, #9b51e0 70%, transparent 100%)',
            opacity: 0.25,
          }} />

          {/* Microsoft sign-in button */}
          <button
            onClick={handleLogin}
            disabled={isLoggingIn}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 12, padding: '14px 20px', borderRadius: 12,
              fontSize: 14, fontWeight: 500, border: 'none', cursor: isLoggingIn ? 'wait' : 'pointer',
              background: '#1c0957', color: 'white',
              boxShadow: '0 4px 14px rgba(28,9,87,0.25)',
              opacity: isLoggingIn ? 0.6 : 1,
              transition: 'box-shadow 0.2s, opacity 0.2s',
            }}
            onMouseEnter={(e) => { if (!isLoggingIn) (e.target as HTMLElement).style.boxShadow = '0 6px 20px rgba(28,9,87,0.4)'; }}
            onMouseLeave={(e) => { (e.target as HTMLElement).style.boxShadow = '0 4px 14px rgba(28,9,87,0.25)'; }}
          >
            {isLoggingIn ? (
              <>
                <div style={{
                  width: 18, height: 18, border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: 'white', borderRadius: '50%', animation: 'spin 0.8s linear infinite',
                }} />
                <span>Redirecionando...</span>
              </>
            ) : (
              <>
                <svg width="18" height="18" viewBox="0 0 21 21" fill="none">
                  <rect x="1" y="1" width="9" height="9" fill="#F25022" />
                  <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
                  <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
                  <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
                </svg>
                <span>Entrar com Microsoft</span>
              </>
            )}
          </button>

          {/* Error */}
          {loginError && (
            <div style={{
              marginTop: 16, fontSize: 12, color: '#e12d39',
              background: '#fef2f2', borderRadius: 8, padding: '10px 12px',
              border: '1px solid #fecaca',
            }}>
              {loginError}
            </div>
          )}

          {/* Access note */}
          <p style={{ textAlign: 'center', fontSize: 11, color: '#9fb3c8', marginTop: 28 }}>
            Acesso restrito a usuários autorizados pela organização
          </p>
        </div>

        {/* Footer */}
        <p style={{ textAlign: 'center', fontSize: 11, color: 'rgba(255,255,255,0.3)', marginTop: 24 }}>
          PG Consultoria &middot; AI Team
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AuthProvider
// ---------------------------------------------------------------------------

/**
 * DevAuthProvider — used when AZURE_AD_CLIENT_ID is not configured.
 * Mirrors backend SKIP_AUTH=true behavior: injects mock admin user.
 */
export function DevAuthProvider({ children }: { children: React.ReactNode }) {
  const mockUser: UserProfile = { email: 'dev@local', name: 'Dev User', role: 'admin' };
  return (
    <AuthContext.Provider
      value={{
        user: mockUser,
        isAdmin: true,
        isLoading: false,
        getAccessToken: async () => null,
        logout: () => window.location.reload(),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const profileFetchedRef = useRef(false);

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    if (!accounts[0]) return null;
    try {
      const response = await instance.acquireTokenSilent({
        ...loginRequest,
        account: accounts[0],
      });
      return response.accessToken;
    } catch {
      try {
        const response = await instance.acquireTokenPopup(loginRequest);
        return response.accessToken;
      } catch {
        return null;
      }
    }
  }, [instance, accounts]);

  // Register token provider with api.ts
  useEffect(() => {
    setTokenProvider(getAccessToken);
  }, [getAccessToken]);

  // Fetch user profile after authentication
  useEffect(() => {
    if (!isAuthenticated || profileFetchedRef.current) return;
    if (inProgress !== InteractionStatus.None) return;

    const fetchProfile = async () => {
      try {
        const token = await getAccessToken();
        if (!token) {
          // Token null = MSAL could not acquire (transient issue).
          // Do NOT logoutRedirect here — would cause infinite loop.
          console.warn('[Auth] No access token available — will retry on next interaction');
          setIsLoading(false);
          return;
        }
        const profile = await apiClient.getUserProfile(token);
        setUser({
          email: profile.email,
          name: profile.name,
          role: profile.role as 'admin' | 'consultor',
        });
        profileFetchedRef.current = true;
      } catch (err: any) {
        const status = err?.response?.status;
        if (status === 401) {
          // Backend CONFIRMED the token is invalid — safe to force re-login
          console.warn('[Auth] Token rejected by backend (401) — forcing re-login');
          instance.logoutRedirect();
          return;
        }
        // Other errors (network, 500, CORS) — don't force logout
        console.error('[Auth] Failed to fetch user profile:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, [isAuthenticated, inProgress, getAccessToken]);

  const logout = useCallback(() => {
    profileFetchedRef.current = false;
    setUser(null);
    instance.logoutRedirect();
  }, [instance]);

  const isAdmin = user?.role === 'admin';

  // Show spinner while MSAL processes a redirect response
  if (inProgress !== InteractionStatus.None) {
    return (
      <div className="flex items-center justify-center h-screen"
        style={{ background: 'linear-gradient(135deg, #0e0330 0%, #1c0957 50%, #0e0330 100%)' }}
      >
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-[3px] border-white/20 border-t-[#0693e3] rounded-full mx-auto mb-4" />
          <p className="text-white/60 text-sm">Autenticando...</p>
        </div>
      </div>
    );
  }

  // Show login page when not authenticated
  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <AuthContext.Provider value={{ user, isAdmin, isLoading, getAccessToken, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
