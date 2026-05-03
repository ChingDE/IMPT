// src/App.jsx
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';

import Login    from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import NewSession from './pages/NewSession';
import Running from './pages/Running';
import Results from './pages/Results';
import { Reports, History, Compare, Config, Profiles, UserProfile, Help, Admin } from './pages/OtherPages';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100vh', color: 'var(--gray-400)', fontFamily: 'var(--font)' }}>
      <div>
        <div style={{ fontSize: 40, textAlign: 'center', marginBottom: 12 }}>⚗</div>
        <div>Loading IMPT…</div>
      </div>
    </div>
  );
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login"        element={<Login />} />
      <Route path="/register"     element={<Register />} />
      <Route path="/forgot"       element={<Login />} />

      {/* Protected */}
      <Route path="/dashboard"    element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/new-session"  element={<ProtectedRoute><NewSession /></ProtectedRoute>} />
      <Route path="/running/:id"  element={<ProtectedRoute><Running /></ProtectedRoute>} />
      <Route path="/results/:id"  element={<ProtectedRoute><Results /></ProtectedRoute>} />
      <Route path="/reports"      element={<ProtectedRoute><Reports /></ProtectedRoute>} />
      <Route path="/history"      element={<ProtectedRoute><History /></ProtectedRoute>} />
      <Route path="/compare"      element={<ProtectedRoute><Compare /></ProtectedRoute>} />
      <Route path="/config"       element={<ProtectedRoute><Config /></ProtectedRoute>} />
      <Route path="/profiles"     element={<ProtectedRoute><Profiles /></ProtectedRoute>} />
      <Route path="/profile"      element={<ProtectedRoute><UserProfile /></ProtectedRoute>} />
      <Route path="/help"         element={<ProtectedRoute><Help /></ProtectedRoute>} />
      <Route path="/admin"        element={<ProtectedRoute><Admin /></ProtectedRoute>} />

      {/* Redirects */}
      <Route path="/"             element={<Navigate to="/dashboard" replace />} />
      <Route path="*"             element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
