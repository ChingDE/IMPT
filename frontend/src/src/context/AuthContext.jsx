// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect } from 'react';
import { getMe } from '../api/client';

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('impt_token');
    if (!token) { setLoading(false); return; }
    getMe()
      .then(u => setUser(u))
      .catch(() => localStorage.removeItem('impt_token'))
      .finally(() => setLoading(false));
  }, []);

  const signIn = (token, userData) => {
    localStorage.setItem('impt_token', token);
    setUser(userData);
  };

  const signOut = () => {
    localStorage.removeItem('impt_token');
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, setUser, loading, signIn, signOut }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
