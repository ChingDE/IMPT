// src/pages/Profile.jsx  FR129-FR134
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getMyStats, updateMe, changePassword, deleteAccount } from '../api/client';
import { AppShell, PageHeader, Alert, ConfirmModal } from '../components/UI';

const NOTIF_ITEMS = [
  { key: 'notif_session_complete', label: 'Email notification when a testing session completes',      defaultOn: true  },
  { key: 'notif_security_alerts',  label: 'Security alerts (login from new location, failed attempts)', defaultOn: true  },
  { key: 'notif_product_updates',  label: 'Product updates and new features',                          defaultOn: false },
];

function NotifToggles() {
  const [prefs, setPrefs] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('notif_prefs') || '{}');
      const defaults = Object.fromEntries(NOTIF_ITEMS.map(i => [i.key, i.defaultOn]));
      return { ...defaults, ...stored };
    } catch { return Object.fromEntries(NOTIF_ITEMS.map(i => [i.key, i.defaultOn])); }
  });

  const toggle = (key) => {
    setPrefs(prev => {
      const next = { ...prev, [key]: !prev[key] };
      localStorage.setItem('notif_prefs', JSON.stringify(next));
      return next;
    });
  };

  return (
    <div>
      {NOTIF_ITEMS.map(({ key, label }) => {
        const on = !!prefs[key];
        return (
          <div key={key} style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
            padding:'10px 0', borderBottom:'1px solid var(--gray-100)', cursor:'pointer' }}
            onClick={() => toggle(key)}>
            <span style={{ fontSize:13.5, color: on ? 'var(--gray-800)' : 'var(--gray-400)', userSelect:'none' }}>{label}</span>
            {/* Toggle pill */}
            <div style={{
              position:'relative', width:40, height:22, borderRadius:22, flexShrink:0,
              background: on ? 'var(--purple-mid)' : 'var(--gray-300)',
              transition:'background .2s',
            }}>
              <div style={{
                position:'absolute', top:3, left: on ? 21 : 3,
                width:16, height:16, borderRadius:'50%', background:'#fff',
                boxShadow:'0 1px 3px rgba(0,0,0,.2)', transition:'left .2s',
              }} />
            </div>
          </div>
        );
      })}
      <div style={{fontSize:12,color:'var(--gray-400)',marginTop:8}}>Preferences saved locally to this browser.</div>
    </div>
  );
}
import { CheckCircle } from 'lucide-react';

export default function Profile() {
  const nav = useNavigate();
  const { user, setUser, signOut } = useAuth();
  const [stats, setStats]         = useState(null);
  const [profile, setProfile]     = useState({ first_name:'', last_name:'', organization:'' });
  const [pw, setPw]               = useState({ current_password:'', new_password:'', confirm_password:'' });
  const [saved, setSaved]         = useState(false);
  const [pwSaved, setPwSaved]     = useState(false);
  const [error, setError]         = useState('');
  const [pwError, setPwError]     = useState('');
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState('');

  useEffect(() => {
    if (user) setProfile({ first_name: user.first_name||'', last_name: user.last_name||'', organization: user.organization||'' });
    getMyStats().then(setStats).catch(()=>{});
  }, [user]);

  const handleSave = async e => {
    e.preventDefault();
    setError('');
    try {
      const updated = await updateMe(profile);
      if (setUser) setUser(u => ({...u, ...updated}));
      setSaved(true); setTimeout(()=>setSaved(false),2500);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save changes.');
    }
  };

  const handlePwChange = async e => {
    e.preventDefault();
    setPwError('');
    if (pw.new_password !== pw.confirm_password) { setPwError('Passwords do not match.'); return; }
    try {
      await changePassword(pw);
      setPw({current_password:'',new_password:'',confirm_password:''});
      setPwSaved(true);
      // Sign out after 3 seconds so user confirms new password works on next login
      setTimeout(() => { signOut(); nav('/login?reason=password_changed'); }, 3000);
    } catch (err) {
      setPwError(err.response?.data?.detail || 'Failed to change password.');
    }
  };

  const handleDeleteAccount = async () => {
    if (deleteConfirm !== 'DELETE') return;
    try {
      await deleteAccount();
      signOut();
      nav('/login');
    } catch {}
  };

  return (
    <AppShell>
      <PageHeader icon="👤" title="Profile & Settings" />
      <div className="page-content">
        <div style={{ maxWidth:680 }}>

          {/* FR129 — Profile info */}
          <div className="card mb-4">
            <div className="card-title">Personal Information</div>
            {error && <Alert type="error">{error}</Alert>}
            {saved && <Alert type="success">Profile updated successfully.</Alert>}
            <form onSubmit={handleSave}>
              <div className="form-row-2">
                <div className="form-group">
                  <label className="form-label">First Name</label>
                  <input className="form-input" value={profile.first_name} onChange={e=>setProfile(p=>({...p,first_name:e.target.value}))} />
                </div>
                <div className="form-group">
                  <label className="form-label">Last Name</label>
                  <input className="form-input" value={profile.last_name} onChange={e=>setProfile(p=>({...p,last_name:e.target.value}))} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Email Address <span className="badge badge-green ml-2" style={{fontSize:10}}>{user?.is_verified?'Verified':'Unverified'}</span></label>
                <input className="form-input" value={user?.email||''} readOnly style={{background:'var(--gray-50)',cursor:'not-allowed'}} />
                <div style={{fontSize:11,color:'var(--gray-400)',marginTop:4}}>Email cannot be changed here. Contact support to update your email address.</div>
              </div>
              <div className="form-group">
                <label className="form-label">Organization</label>
                <input className="form-input" value={profile.organization} onChange={e=>setProfile(p=>({...p,organization:e.target.value}))} placeholder="Your organization" />
              </div>
              <div className="flex justify-end">
                <button type="submit" className="btn btn-primary">{saved?'✓ Saved':'Save Changes'}</button>
              </div>
            </form>
          </div>

          {/* FR131 — Account info */}
          <div className="card mb-4">
            <div className="card-title">Account Information</div>
            <div className="grid-3" style={{gap:12}}>
              {[
                {l:'Account Created',v:user?.created_at?new Date(user.created_at).toLocaleDateString():'—'},
                {l:'Total Sessions',v:stats?.total_sessions??'—'},
                {l:'Time Saved',v:stats?`${Math.round(stats?.total_time_saved_minutes||0)}m`:'—'},
              ].map(({l,v})=>(
                <div key={l} className="stat-card" style={{textAlign:'center'}}>
                  <div className="stat-value" style={{fontSize:18}}>{v}</div>
                  <div className="stat-label">{l}</div>
                </div>
              ))}
            </div>
          </div>

          {/* FR130 — Change password */}
          <div className="card mb-4">
            <div className="card-title">🔒 Change Password</div>
            {pwError && <Alert type="error">{pwError}</Alert>}
            {pwSaved && <Alert type="success">Password changed successfully. You will be logged out in 3 seconds — please log back in with your new password.</Alert>}
            <form onSubmit={handlePwChange}>
              {['current_password','new_password','confirm_password'].map(k=>(
                <div className="form-group" key={k}>
                  <label className="form-label">{k==='current_password'?'Current Password':k==='new_password'?'New Password':'Confirm New Password'}</label>
                  <input className="form-input" type="password" placeholder="••••••••"
                    value={pw[k]} onChange={e=>setPw(p=>({...p,[k]:e.target.value}))} required />
                </div>
              ))}
              <div className="flex justify-end">
                <button type="submit" className="btn btn-primary">Update Password</button>
              </div>
            </form>
          </div>

          {/* FR133 — Notification preferences */}
          <div className="card mb-4">
            <div className="card-title">🔔 Notification Preferences</div>
            <div style={{fontSize:13,color:'var(--gray-600)',marginBottom:12,lineHeight:1.55}}>
              Choose which email notifications you receive.
            </div>
            <NotifToggles />
          </div>

          {/* FR132 — Delete account */}
          <div className="card" style={{borderColor:'#FECACA'}}>
            <div className="card-title" style={{color:'var(--red)'}}>⚠️ Danger Zone</div>
            <div className="danger-row">
              <div>
                <div className="label">Delete Account</div>
                <div className="sub">Permanently delete your account and all associated data. This action cannot be undone.</div>
              </div>
              <button className="btn btn-danger btn-sm" onClick={()=>setShowDelete(true)}>Delete Account</button>
            </div>
          </div>
        </div>
      </div>

      {showDelete && (
        <div className="timeout-overlay">
          <div className="timeout-modal" style={{maxWidth:440}}>
            <h3 style={{color:'var(--red)'}}>Delete Account</h3>
            <p>This will permanently delete your account and all associated sessions, results, and data. This action cannot be undone.</p>
            <p style={{marginTop:12,fontSize:13,fontWeight:600}}>Type DELETE to confirm:</p>
            <input className="form-input mt-2" value={deleteConfirm} onChange={e=>setDeleteConfirm(e.target.value)} placeholder="DELETE" />
            <div className="flex gap-3 justify-end mt-4">
              <button className="btn btn-secondary" onClick={()=>{setShowDelete(false);setDeleteConfirm('')}}>Cancel</button>
              <button className="btn btn-danger" disabled={deleteConfirm!=='DELETE'} onClick={handleDeleteAccount}>Delete My Account</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
