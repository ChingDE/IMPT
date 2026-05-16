// src/api/client.js
import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({ baseURL: BASE });

client.interceptors.request.use(cfg => {
  const token = localStorage.getItem('impt_token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

client.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('impt_token');
      window.location.href = '/login';
    }
    if (err.response?.status === 403) {
      // Unverified account or suspended — clear token and redirect
      localStorage.removeItem('impt_token');
      window.location.href = '/login?reason=unverified';
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────
export const register = (p) => client.post('/api/auth/register', p).then(r => r.data);
export const login = (email, password) => {
  const fd = new URLSearchParams({ username: email, password });
  return client.post('/api/auth/token', fd, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).then(r => r.data);
};
export const adminLogin         = (p)     => client.post('/api/auth/admin-token', p).then(r => r.data);
export const changeAdminCreds   = (p)     => client.post('/api/auth/change-admin-credentials', p).then(r => r.data);
export const getMe              = ()      => client.get('/api/auth/me').then(r => r.data);
export const verifyEmail        = (token) => client.get(`/api/auth/verify-email?token=${token}`).then(r => r.data);
export const resendVerification = ()      => client.post('/api/auth/resend-verification').then(r => r.data);
export const forgotPassword     = (email) => client.post('/api/auth/forgot-password', { email }).then(r => r.data);
export const resetPassword      = (p)     => client.post('/api/auth/reset-password', p).then(r => r.data);

// ── Sessions ──────────────────────────────────────────────────────
export const listSessions       = ()          => client.get('/api/sessions').then(r => r.data);
export const createSession      = (p)         => client.post('/api/sessions', p).then(r => r.data);
export const getSession         = (id)        => client.get(`/api/sessions/${id}`).then(r => r.data);
export const updateSession      = (id,p)      => client.patch(`/api/sessions/${id}`, p).then(r => r.data);
export const deleteSession      = (id)        => client.delete(`/api/sessions/${id}`);
export const uploadProject      = (id,fd)     => client.post(`/api/sessions/${id}/upload`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
export const configureOperators = (id,ops)    => client.post(`/api/sessions/${id}/operators`, { selected_operators: ops }).then(r => r.data);
export const setBudget          = (id,p)      => client.post(`/api/sessions/${id}/budget`, p).then(r => r.data);
export const startTesting       = (id)        => client.post(`/api/sessions/${id}/start`).then(r => r.data);
export const createShareLink    = (id)        => client.post(`/api/sessions/${id}/share`).then(r => r.data);
export const getSharedSession   = (token)     => client.get(`/api/sessions/share/${token}`).then(r => r.data);
export const getSessionJobs     = (id)       => client.get(`/api/sessions/${id}/jobs`).then(r => r.data);

// ── Jobs ──────────────────────────────────────────────────────────
export const getJobStatus    = (id) => client.get(`/api/jobs/${id}`).then(r => r.data);
export const getJobResult    = (id) => client.get(`/api/jobs/${id}/result`).then(r => r.data);
export const getJobMutants   = (id) => client.get(`/api/jobs/${id}/mutants`).then(r => r.data);
export const exportJobCSV    = (id) => client.get(`/api/jobs/${id}/export/csv`, { responseType: 'blob' }).then(r => r.data);

// ── Analytics ─────────────────────────────────────────────────────
export const getDashboardStats  = ()    => client.get('/api/analytics/dashboard').then(r => r.data);
export const getReportsStats    = ()    => client.get('/api/analytics/reports').then(r => r.data);
export const getTrend           = ()    => client.get('/api/analytics/trend').then(r => r.data);
export const compareStrategies  = (id)  => client.get(`/api/analytics/compare/${id}`).then(r => r.data);

// ── Users ─────────────────────────────────────────────────────────
export const getMyStats     = ()  => client.get('/api/users/me/stats').then(r => r.data);
export const updateMe       = (p) => client.patch('/api/users/me', p).then(r => r.data);
export const changePassword = (p) => client.post('/api/users/me/password', p).then(r => r.data);
export const deleteAccount  = ()  => client.delete('/api/users/me').then(r => r.data);

// ── Admin ─────────────────────────────────────────────────────────
export const getAdminStats    = ()         => client.get('/api/admin/stats').then(r => r.data);
export const getHealthMetrics = ()         => client.get('/api/admin/health-metrics').then(r => r.data);
export const listAdminUsers   = (p)        => client.get('/api/admin/users', { params: p }).then(r => r.data);
export const getAdminUser     = (id)       => client.get(`/api/admin/users/${id}`).then(r => r.data);
export const adminVerifyEmail = (id)       => client.post(`/api/admin/users/${id}/verify-email`).then(r => r.data);
export const suspendUser      = (id)       => client.post(`/api/admin/users/${id}/suspend`).then(r => r.data);
export const unsuspendUser    = (id)       => client.post(`/api/admin/users/${id}/unsuspend`).then(r => r.data);
export const deleteUser       = (id)       => client.delete(`/api/admin/users/${id}`).then(r => r.data);
export const getSystemConfig  = ()         => client.get('/api/admin/config').then(r => r.data);
export const updateConfig     = (key,val)  => client.put(`/api/admin/config/${key}`, { value: val }).then(r => r.data);
export const getAuditLogs     = (p)        => client.get('/api/admin/logs', { params: p }).then(r => r.data);

// ── FOSS Projects ─────────────────────────────────────────────────
export const listFossProjects  = (params)  => client.get('/api/foss', { params }).then(r => r.data);
export const getFossProject    = (slug)    => client.get(`/api/foss/${slug}`).then(r => r.data);
export const getFossBaseline   = (slug)    => client.get(`/api/foss/${slug}/baseline`).then(r => r.data);

export default client;
