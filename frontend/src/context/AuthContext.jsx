// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { getMe } from '../api/client';

const AuthCtx = createContext(null);

const TIMEOUT_MS  = 30 * 60 * 1000;  // 30 minutes (NFR016)
const WARNING_MS  =  2 * 60 * 1000;  // warn 2 min before
const WARN_AT_MS  = TIMEOUT_MS - WARNING_MS;

export function AuthProvider({ children }) {
  const [user, setUser]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [showTimeout, setShowTimeout] = useState(false);
  const timerRef   = useRef(null);
  const warnRef    = useRef(null);
  const countRef   = useRef(null);
  const [countdown, setCountdown]   = useState(120);

  const clearTimers = () => {
    clearTimeout(timerRef.current);
    clearTimeout(warnRef.current);
    clearInterval(countRef.current);
  };

  const resetTimers = useCallback(() => {
    if (!localStorage.getItem('impt_token')) return;
    clearTimers();
    setShowTimeout(false);

    warnRef.current = setTimeout(() => {
      setShowTimeout(true);
      setCountdown(120);
      countRef.current = setInterval(() => {
        setCountdown(c => {
          if (c <= 1) { clearInterval(countRef.current); return 0; }
          return c - 1;
        });
      }, 1000);
    }, WARN_AT_MS);

    timerRef.current = setTimeout(() => {
      signOut();
    }, TIMEOUT_MS);
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('impt_token');
    if (!token) { setLoading(false); return; }
    getMe()
      .then(u => { setUser(u); resetTimers(); })
      .catch(() => localStorage.removeItem('impt_token'))
      .finally(() => setLoading(false));
  }, []);

  // Reset timer on user activity
  useEffect(() => {
    if (!user) return;
    const events = ['mousedown', 'keydown', 'scroll', 'touchstart'];
    const handler = () => resetTimers();
    events.forEach(e => window.addEventListener(e, handler, { passive: true }));
    return () => events.forEach(e => window.removeEventListener(e, handler));
  }, [user, resetTimers]);

  const signIn = (token, userData) => {
    localStorage.setItem('impt_token', token);
    setUser(userData);
    resetTimers();
  };

  const signOut = () => {
    localStorage.removeItem('impt_token');
    setUser(null);
    setShowTimeout(false);
    clearTimers();
  };

  const extendSession = () => {
    setShowTimeout(false);
    resetTimers();
  };

  return (
    <AuthCtx.Provider value={{ user, setUser, loading, signIn, signOut, showTimeout, extendSession, countdown }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
