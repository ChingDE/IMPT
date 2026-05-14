// src/App.jsx
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './context/AuthContext';

// Auth pages
import Login from './pages/Login';
import Register from './pages/Register';
import { VerifyEmailSent, VerifyEmail } from './pages/VerifyEmail';
import { ForgotPassword, ResetPassword } from './pages/ForgotPassword';
import { AdminLogin, AdminFirstLogin } from './pages/AdminAuth';

// App pages (Phase 3+ — stubs for now)
import Dashboard from './pages/Dashboard';
import { NewSessionCreate } from './pages/NewSession';
import { NewSessionUpload } from './pages/NewSession';
import { NewSessionOperators } from './pages/NewSession';
import { NewSessionBudget } from './pages/NewSession';
import { NewSessionReview } from './pages/NewSession';
import Running from './pages/Running';
import Results from './pages/Results';
import CompareResults from './pages/CompareResults';
import History from './pages/History';
import Profile from './pages/Profile';
import Help from './pages/Help';
import { AdminDashboard, AdminUsers, AdminConfig, AdminLogs } from './pages/Admin';

// Loading screen
function Loading() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100vh', color: 'var(--gray-400)', fontFamily: 'var(--font)' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>⚗</div>
        <div>Loading IMPT…</div>
      </div>
    </div>
  );
}

// Protected route — requires login
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;

  // Force admin password change
  if (user.must_change_password && !location.pathname.includes('admin-first-login')) {
    return <Navigate to="/admin-first-login" replace />;
  }

  return children;
}

// Admin-only route
function AdminRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== 'admin') return <Navigate to="/dashboard" replace />;
  return children;
}

// Public route — redirect to dashboard if already logged in
function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (user && !user.must_change_password) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      {/* Public auth routes */}
      <Route path="/login"               element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register"            element={<PublicRoute><Register /></PublicRoute>} />
      <Route path="/verify-email-sent"   element={<VerifyEmailSent />} />
      <Route path="/verify-email"        element={<VerifyEmail />} />
      <Route path="/forgot-password"     element={<ForgotPassword />} />
      <Route path="/reset-password"      element={<ResetPassword />} />
      <Route path="/admin-login"         element={<PublicRoute><AdminLogin /></PublicRoute>} />
      <Route path="/admin-first-login"   element={<ProtectedRoute><AdminFirstLogin /></ProtectedRoute>} />

      {/* Protected user routes */}
      <Route path="/dashboard"           element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/new-session"         element={<ProtectedRoute><NewSessionCreate /></ProtectedRoute>} />
      <Route path="/sessions/:id/upload" element={<ProtectedRoute><NewSessionUpload /></ProtectedRoute>} />
      <Route path="/sessions/:id/operators" element={<ProtectedRoute><NewSessionOperators /></ProtectedRoute>} />
      <Route path="/sessions/:id/budget" element={<ProtectedRoute><NewSessionBudget /></ProtectedRoute>} />
      <Route path="/sessions/:id/review" element={<ProtectedRoute><NewSessionReview /></ProtectedRoute>} />
      <Route path="/running/:sessionId"  element={<ProtectedRoute><Running /></ProtectedRoute>} />
      <Route path="/results/:sessionId"  element={<ProtectedRoute><Results /></ProtectedRoute>} />
      <Route path="/compare/:sessionId"  element={<ProtectedRoute><CompareResults /></ProtectedRoute>} />
      <Route path="/history"             element={<ProtectedRoute><History /></ProtectedRoute>} />
      <Route path="/profile"             element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/help"                element={<ProtectedRoute><Help /></ProtectedRoute>} />

      {/* Admin routes */}
      <Route path="/admin"               element={<AdminRoute><AdminDashboard /></AdminRoute>} />
      <Route path="/admin/users"         element={<AdminRoute><AdminUsers /></AdminRoute>} />
      <Route path="/admin/config"        element={<AdminRoute><AdminConfig /></AdminRoute>} />
      <Route path="/admin/logs"          element={<AdminRoute><AdminLogs /></AdminRoute>} />

      {/* Redirects */}
      <Route path="/"    element={<Navigate to="/dashboard" replace />} />
      <Route path="*"    element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
