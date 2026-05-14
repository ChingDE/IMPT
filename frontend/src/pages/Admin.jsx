// src/pages/Admin.jsx  FR135-FR158
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAdminStats, getHealthMetrics, listAdminUsers, adminVerifyEmail,
  suspendUser, unsuspendUser, deleteUser, getSystemConfig, updateConfig,
  getAuditLogs } from '../api/client';
import { AppShell, PageHeader, Alert, ConfirmModal } from '../components/UI';

// ── Admin Dashboard ───────────────────────────────────────────────
export function AdminDashboard() {
  const nav = useNavigate();
  const [stats, setStats]   = useState(null);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    getAdminStats().then(setStats).catch(()=>{});
    getHealthMetrics().then(setHealth).catch(()=>{});
    const t = setInterval(()=>getHealthMetrics().then(setHealth).catch(()=>{}), 30000);
    return ()=>clearInterval(t);
  }, []);

  return (
    <AppShell>
      <PageHeader icon="🛡️" title="Admin Dashboard"
        right={<span style={{background:'rgba(255,255,255,.15)',color:'rgba(255,255,255,.9)',padding:'4px 12px',borderRadius:999,fontSize:12,fontWeight:600}}>
          Real-time · Updates every 30s
        </span>} />
      <div className="page-content">
        {/* FR135 — Admin nav */}
        <div className="flex gap-3 mb-4">
          {[['👥 Users','/admin/users'],['⚙️ Config','/admin/config'],['📋 Logs','/admin/logs']].map(([l,p])=>(
            <button key={p} className="btn btn-outline btn-sm" onClick={()=>nav(p)}>{l}</button>
          ))}
        </div>

        {/* FR136 — System stats */}
        <div className="grid-4 mb-4">
          {[
            {l:'Total Users',v:stats?.total_users??'—',c:'blue'},
            {l:'Total Sessions',v:stats?.total_sessions??'—',c:'purple'},
            {l:'Tests Run',v:stats?.completed_jobs??'—',c:'green'},
            {l:'Active (7 days)',v:stats?.active_users_7d??'—',c:'amber'},
          ].map(({l,v,c})=>(
            <div key={l} className={`stat-card ${c}`}>
              <div className="stat-label">{l}</div>
              <div className="stat-value">{v}</div>
            </div>
          ))}
        </div>

        {/* FR137 — Recent activity */}
        <div className="card mb-4">
          <div className="card-title">📡 Recent Activity</div>
          <div style={{ fontSize:13,color:'var(--gray-500)',fontStyle:'italic' }}>
            Live activity feed. <span className="link" style={{marginLeft:8,fontStyle:'normal'}} onClick={()=>nav('/admin/logs')}>View all logs →</span>
          </div>
        </div>

        {/* FR158 — Health metrics */}
        {health && !health.error && (
          <div className="card mb-4">
            <div className="card-title">📡 Server Health</div>
            <div className="grid-4" style={{gap:12}}>
              {[
                {l:'CPU',v:`${health.cpu_pct?.toFixed(1)||0}%`,warn:health.cpu_pct>80},
                {l:'Memory',v:`${health.memory_pct?.toFixed(1)||0}%`,warn:health.memory_pct>80},
                {l:'Disk',v:`${health.disk_pct?.toFixed(1)||0}%`,warn:health.disk_pct>80},
                {l:'RAM Used',v:`${health.memory_used_gb?.toFixed(1)||0}/${health.memory_total_gb?.toFixed(0)||0} GB`,warn:false},
              ].map(({l,v,warn})=>(
                <div key={l} className="stat-card" style={{textAlign:'center'}}>
                  <div className="stat-value" style={{fontSize:18,color:warn?'var(--red)':'var(--gray-800)'}}>{v}</div>
                  <div className="stat-label">{l}</div>
                  {warn && <div style={{fontSize:11,color:'var(--red)',marginTop:4}}>⚠ High usage</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

// ── Admin Users ────────────────────────────────────────────────
export function AdminUsers() {
  const nav = useNavigate();
  const [users, setUsers]         = useState([]);
  const [search, setSearch]       = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);

  const [statusFilter, setStatusFilter] = useState('');
  const load = (s='') => listAdminUsers({search:s||undefined}).then(setUsers).catch(()=>{});
  useEffect(()=>{ load(); },[]);

  const handleVerify  = async id => { await adminVerifyEmail(id); load(search); };
  const handleSuspend = async id => { await suspendUser(id); load(search); };
  const handleUnsuspend = async id => { await unsuspendUser(id); load(search); };
  const handleDelete  = async () => { await deleteUser(deleteTarget.id); load(search); setDeleteTarget(null); };

  return (
    <AppShell>
      <PageHeader icon="👥" title="User Management"
        right={
          <input className="form-input" style={{width:240,height:34,fontSize:13,background:'rgba(255,255,255,.15)',borderColor:'rgba(255,255,255,.3)',color:'#fff'}}
            placeholder="🔍 Search users…" value={search}
            onChange={e=>{setSearch(e.target.value);load(e.target.value)}} />
        }
      />
      <div className="page-content">
        
        {/* FR141 — Filter bar */}
        <div className="card mb-3">
          <div className="flex gap-2" style={{flexWrap:'wrap'}}>
            {['all','verified','unverified'].map(f => (
              <button key={f} className={`btn btn-sm ${statusFilter===(f==='all'?'':f)?'btn-primary':'btn-secondary'}`}
                onClick={()=>setStatusFilter(f==='all'?'':f)}>
                {f.charAt(0).toUpperCase()+f.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Org</th><th>Verified</th><th>Active</th><th>Joined</th><th>Actions</th></tr></thead>
            <tbody>
              {users.map(u=>(
                <tr key={u.id}>
                  <td className="bold">{u.first_name} {u.last_name}</td>
                  <td>{u.email}</td>
                  <td className="text-muted">{u.organization||'—'}</td>
                  <td>{u.is_verified ? <span className="badge badge-green">✓</span> : <span className="badge badge-amber">✗</span>}</td>
                  <td>{u.is_active ? <span className="badge badge-green">Active</span> : <span className="badge badge-red">Suspended</span>}</td>
                  <td className="text-muted text-sm">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="flex gap-1" style={{flexWrap:'wrap'}}>
                      {!u.is_verified && <button className="btn btn-outline btn-sm" style={{fontSize:11}} onClick={()=>handleVerify(u.id)}>Verify</button>}
                      {u.is_active ? <button className="btn btn-secondary btn-sm" style={{fontSize:11,color:'var(--amber)'}} onClick={()=>handleSuspend(u.id)}>Suspend</button>
                        : <button className="btn btn-secondary btn-sm" style={{fontSize:11,color:'var(--green)'}} onClick={()=>handleUnsuspend(u.id)}>Unsuspend</button>}
                      {u.role !== 'admin' && <button className="btn btn-secondary btn-sm" style={{fontSize:11,color:'var(--red)'}} onClick={()=>setDeleteTarget(u)}>Delete</button>}
                    </div>
                  </td>
                </tr>
              ))}
              {users.length===0 && <tr><td colSpan={7} style={{textAlign:'center',padding:20,color:'var(--gray-400)'}}>No users found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {deleteTarget && <ConfirmModal title="Delete User"
        message={`Delete ${deleteTarget.first_name} ${deleteTarget.last_name} (${deleteTarget.email}) and all their data?`}
        confirmLabel="Delete User" onConfirm={handleDelete} onCancel={()=>setDeleteTarget(null)} />}
    </AppShell>
  );
}

// ── Admin Config ───────────────────────────────────────────────
export function AdminConfig() {
  const nav = useNavigate();
  const [config, setConfig] = useState([]);
  const [edits, setEdits]   = useState({});
  const [saved, setSaved]   = useState('');

  useEffect(()=>{ getSystemConfig().then(setConfig).catch(()=>{}); },[]);

  const handleSave = async key => {
    const val = edits[key] ?? config.find(c=>c.key===key)?.value;
    await updateConfig(key, val);
    setSaved(key); setTimeout(()=>setSaved(''),2000);
    getSystemConfig().then(setConfig);
  };

  return (
    <AppShell>
      <PageHeader icon="⚙️" title="System Configuration" />
      <div className="page-content">
        
        {/* FR149 — Registration mode */}
        <div className="card mb-4" style={{borderLeft:'4px solid var(--amber)',background:'var(--amber-light)'}}>
          <div style={{fontWeight:700,fontSize:14,marginBottom:8,color:'var(--amber)'}}>⚠ Maintenance Mode</div>
          <p style={{fontSize:13,color:'var(--gray-700)',marginBottom:12}}>
            Disabling registration prevents new users from signing up.
          </p>
          <button className="btn btn-secondary btn-sm"
            onClick={async () => {
              const current = config.find(c=>c.key==='registration_enabled')?.value === 'true';
              await updateConfig('registration_enabled', String(!current));
              getSystemConfig().then(setConfig);
            }}>
            {config.find(c=>c.key==='registration_enabled')?.value === 'true'
              ? '🔒 Disable Registration' : '🔓 Enable Registration'}
          </button>
        </div>
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Setting</th><th>Value</th><th>Last Updated</th><th></th></tr></thead>
            <tbody>
              {config.map(c=>(
                <tr key={c.key}>
                  <td className="bold">{c.key.replace(/_/g,' ').replace(/\b\w/g,x=>x.toUpperCase())}</td>
                  <td>
                    <input className="form-input" style={{height:32,fontSize:13}}
                      value={edits[c.key]??c.value}
                      onChange={e=>setEdits(ed=>({...ed,[c.key]:e.target.value}))} />
                  </td>
                  <td className="text-muted text-sm">{new Date(c.updated_at).toLocaleDateString()}</td>
                  <td>
                    <button className="btn btn-primary btn-sm" onClick={()=>handleSave(c.key)}>
                      {saved===c.key?'✓ Saved':'Save'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}

// ── Admin Logs ─────────────────────────────────────────────────
export function AdminLogs() {
  const nav = useNavigate();
  const [logs, setLogs]     = useState([]);
  const [level, setLevel]     = useState('');
  const [category, setCategory] = useState('');
  const [errorCount, setErrorCount] = useState(0);

  const load = () => {
    getAuditLogs({ level:level||undefined, category:category||undefined, limit:200 }).then(setLogs).catch(()=>{});
    getAuditLogs({ level:'ERROR', limit:200 }).then(ls => {
      const cutoff = Date.now() - 24*60*60*1000;
      setErrorCount(ls.filter(l => new Date(l.created_at).getTime() > cutoff).length);
    }).catch(()=>{});
  };
  useEffect(()=>{ load(); },[level,category]);

  const levelColor = l => l==='ERROR'?'var(--red)':l==='WARNING'?'var(--amber)':'var(--blue)';

  return (
    <AppShell>
      <PageHeader icon="📋" title="Audit Logs" />
      <div className="page-content">
        <button className="btn btn-secondary btn-sm mb-4" onClick={()=>nav('/admin')}>← Back</button>
        {errorCount > 0 && (
          <div className="alert alert-error mb-4">
            ⚠ <strong>{errorCount}</strong> ERROR event(s) in the last 24 hours.{errorCount > 50 ? ' High error rate detected!' : ''}
          </div>
        )}
        <div className="card mb-4">
          <div className="flex gap-3">
            <div>
              <label className="form-label" style={{fontSize:11}}>Level</label>
              <select className="form-select" style={{height:34,fontSize:13}} value={level} onChange={e=>setLevel(e.target.value)}>
                <option value="">All Levels</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </div>
            <div>
              <label className="form-label" style={{fontSize:11}}>Category</label>
              <select className="form-select" style={{height:34,fontSize:13}} value={category} onChange={e=>setCategory(e.target.value)}>
                <option value="">All Categories</option>
                <option value="AUTH">AUTH</option>
                <option value="TESTING">TESTING</option>
                <option value="ADMIN">ADMIN</option>
                <option value="SYSTEM">SYSTEM</option>
              </select>
            </div>
          </div>
        </div>
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Timestamp</th><th>Level</th><th>Category</th><th>Action</th><th>Message</th><th>IP</th><th>Result</th></tr></thead>
            <tbody>
              {logs.map(l=>(
                <tr key={l.id}>
                  <td className="text-muted text-sm" style={{whiteSpace:'nowrap'}}>{new Date(l.created_at).toLocaleString()}</td>
                  <td><span style={{fontSize:11,fontWeight:700,color:levelColor(l.level)}}>{l.level}</span></td>
                  <td><span className="badge badge-gray" style={{fontSize:10}}>{l.category}</span></td>
                  <td style={{fontSize:12.5,fontFamily:'var(--mono)'}}>{l.action}</td>
                  <td style={{fontSize:12.5,maxWidth:300,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{l.message}</td>
                  <td className="text-muted text-sm">{l.ip_address||'—'}</td>
                  <td><span className={`badge ${l.outcome==='success'?'badge-green':'badge-red'}`} style={{fontSize:10}}>{l.outcome}</span></td>
                </tr>
              ))}
              {logs.length===0 && <tr><td colSpan={7} style={{textAlign:'center',padding:20,color:'var(--gray-400)'}}>No logs found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
