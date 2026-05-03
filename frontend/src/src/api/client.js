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
    return Promise.reject(err);
  }
);

// ── Auth ─────────────────────────────────────────────────────────
export const login = (email, password) => {
  const fd = new URLSearchParams({ username: email, password });
  return client.post('/api/auth/token', fd, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  }).then(r => r.data);
};
export const register = (payload) => client.post('/api/auth/register', payload).then(r => r.data);
export const getMe    = ()         => client.get('/api/auth/me').then(r => r.data);

// ── Projects ─────────────────────────────────────────────────────
export const listProjects   = ()       => client.get('/api/projects').then(r => r.data);
export const createProject  = (p)      => client.post('/api/projects', p).then(r => r.data);
export const getProject     = (id)     => client.get(`/api/projects/${id}`).then(r => r.data);
export const deleteProject  = (id)     => client.delete(`/api/projects/${id}`);
export const uploadProject  = (id, fd) => client.post(`/api/projects/${id}/upload`, fd, {
  headers: { 'Content-Type': 'multipart/form-data' }
}).then(r => r.data);

// ── Jobs ─────────────────────────────────────────────────────────
export const listJobs      = ()    => client.get('/api/jobs').then(r => r.data);
export const submitJob     = (p)   => client.post('/api/jobs', p).then(r => r.data);
export const getJobStatus  = (id)  => client.get(`/api/jobs/${id}`).then(r => r.data);
export const getJobResult  = (id)  => client.get(`/api/jobs/${id}/result`).then(r => r.data);
export const getJobMutants = (id)  => client.get(`/api/jobs/${id}/mutants`).then(r => r.data);

// ── Analytics ────────────────────────────────────────────────────
export const getTrend   = ()           => client.get('/api/analytics/trend').then(r => r.data);
export const getSummary = ()           => client.get('/api/analytics/summary').then(r => r.data);
export const compareJobs = (a, b)      => client.get(`/api/analytics/compare?job_a=${a}&job_b=${b}`).then(r => r.data);
export const getAdminStats = ()        => client.get('/api/analytics/admin').then(r => r.data);
export const exportCSV = (jobId)       => client.get(`/api/jobs/${jobId}/export/csv`, { responseType: 'blob' }).then(r => r.data);

// ── Profiles ─────────────────────────────────────────────────────
export const listProfiles   = ()    => client.get('/api/profiles').then(r => r.data);
export const createProfile  = (p)   => client.post('/api/profiles', p).then(r => r.data);
export const updateProfile  = (id,p)=> client.put(`/api/profiles/${id}`, p).then(r => r.data);
export const deleteProfile  = (id)  => client.delete(`/api/profiles/${id}`);
export const useProfile     = (id)  => client.post(`/api/profiles/${id}/use`).then(r => r.data);

// ── Users ────────────────────────────────────────────────────────
export const getMyStats      = ()  => client.get('/api/users/me/stats').then(r => r.data);
export const updateMe        = (p) => client.patch('/api/users/me', p).then(r => r.data);
export const changePassword  = (p) => client.post('/api/users/me/password', p).then(r => r.data);

// ── Health ───────────────────────────────────────────────────────
export const health = () => client.get('/api/health').then(r => r.data);

export default client;
