// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { getMe } from '../api/client';

const AuthCtx = createContext(null);

const TIMEOUT_MS = 30 * 60 * 1000;  // 30 minutes (NFR016)
const WARNING_MS =  2 * 60 * 1000;
const WARN_AT_MS = TIMEOUT_MS - WARNING_MS;
const TOKEN_KEY  = 'impt_token';

// ── Token helpers — sessionStorage by default, localStorage if "keep signed in" ──
function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || null;
}
function setToken(token, persist) {
  if (persist) {
    localStorage.setItem(TOKEN_KEY, token);
    sessionStorage.removeItem(TOKEN_KEY);
  } else {
    sessionStorage.setItem(TOKEN_KEY, token);
    localStorage.removeItem(TOKEN_KEY);
  }
}
function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
}
function isPersisted() {
  return !!localStorage.getItem(TOKEN_KEY);
}

export function AuthProvider({ children }) {
  const [user, setUser]               = useState(null);
  const [loading, setLoading]         = useState(true);
  const [showTimeout, setShowTimeout] = useState(false);
  const timerRef  = useRef(null);
  const warnRef   = useRef(null);
  const countRef  = useRef(null);
  const [countdown, setCountdown]     = useState(120);

  const clearTimers = () => {
    clearTimeout(timerRef.current);
    clearTimeout(warnRef.current);
    clearInterval(countRef.current);
  };

  const resetTimers = useCallback(() => {
    if (!getToken()) return;
    clearTimers();
    setShowTimeout(false);

    warnRef.current = setTimeout(() => {
      setShowTimeout(true);
      setCountdown(120);
      countRef.current = setInterval(() => {
        setCountdown(c => { if (c <= 1) { clearInterval(countRef.current); return 0; } return c - 1; });
      }, 1000);
    }, WARN_AT_MS);

    timerRef.current = setTimeout(() => { signOut(); }, TIMEOUT_MS);
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) { setLoading(false); return; }
    getMe()
      .then(u => { setUser(u); resetTimers(); })
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    const events = ['mousedown', 'keydown', 'scroll', 'touchstart'];
    const handler = () => resetTimers();
    events.forEach(e => window.addEventListener(e, handler, { passive: true }));
    return () => events.forEach(e => window.removeEventListener(e, handler));
  }, [user, resetTimers]);

  // NFR016: sign out when browser/tab closes if not persisted.
  // Skip during an in-app OAuth redirect (e.g. GitHub) — navigating away to the
  // provider and back must not wipe the session token.
  useEffect(() => {
    const handleUnload = () => {
      if (sessionStorage.getItem('impt_oauth_in_progress')) return;
      if (!isPersisted()) clearToken();
    };
    window.addEventListener('beforeunload', handleUnload);
    return () => window.removeEventListener('beforeunload', handleUnload);
  }, []);

  const signIn = (token, userData, keepSignedIn = false) => {
    setToken(token, keepSignedIn);
    setUser(userData);
    resetTimers();
  };

  const signOut = () => {
    clearToken();
    setUser(null);
    setShowTimeout(false);
    clearTimers();
  };

  const extendSession = () => { setShowTimeout(false); resetTimers(); };

  return (
    <AuthCtx.Provider value={{ user, setUser, loading, signIn, signOut, showTimeout, extendSession, countdown }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
