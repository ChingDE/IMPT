// src/pages/Admin.jsx  FR135-FR158
import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getAdminStats, getAdminCharts, getRecentActivity, getHealthMetrics,
  listAdminUsers, adminVerifyEmail, suspendUser, unsuspendUser,
  deleteUser, getSystemConfig, updateConfig, getAuditLogs,
} from '../api/client';
import { AppShell, PageHeader, Alert, ConfirmModal } from '../components/UI';

// ── Mini bar chart ────────────────────────────────────────────────
function MiniBarChart({ days, values, color, label }) {
  const max = Math.max(...values, 1);
  const W = 480, H = 72, PAD = 4;
  const bw = (W - PAD * 2) / values.length - 2;
  return (
    <div>
      <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4 }}>{label}</div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width:'100%', height:72 }}>
        {values.map((v, i) => {
          const bh = Math.max(2, (v / max) * (H - PAD * 2));
          const x  = PAD + i * ((W - PAD * 2) / values.length);
          return <rect key={i} x={x} y={H - PAD - bh} width={bw} height={bh} rx={2} fill={color} opacity={0.8}>
            <title>{days[i]}: {v}</title>
          </rect>;
        })}
      </svg>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color:'var(--gray-400)', marginTop:2 }}>
        <span>{days[0]?.slice(5)}</span><span>{days[days.length-1]?.slice(5)}</span>
      </div>
    </div>
  );
}

function MiniLineChart({ days, values, color, label }) {
  const defined = values.filter(v => v != null);
  if (!defined.length) return (
    <div>
      <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4 }}>{label}</div>
      <div style={{ height:72, display:'grid', placeItems:'center', color:'var(--gray-400)', fontSize:12 }}>No data yet</div>
    </div>
  );
  const max = Math.max(...defined) + 5;
  const min = Math.max(0, Math.min(...defined) - 5);
  const W = 480, H = 72, PAD = 6;
  const pts = values.map((v, i) => {
    if (v == null) return null;
    const x = PAD + (i / (values.length - 1)) * (W - PAD * 2);
    const y = H - PAD - ((v - min) / (max - min || 1)) * (H - PAD * 2);
    return [x, y];
  });
  const path = pts.filter(Boolean).map((p, i, arr) => `${i===0?'M':'L'}${p[0]},${p[1]}`).join(' ');
  return (
    <div>
      <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4 }}>{label}</div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width:'100%', height:72 }}>
        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        {pts.filter(Boolean).map(([x,y], i) => <circle key={i} cx={x} cy={y} r={3} fill={color} />)}
      </svg>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color:'var(--gray-400)', marginTop:2 }}>
        <span>{days[0]?.slice(5)}</span><span>{days[days.length-1]?.slice(5)}</span>
      </div>
    </div>
  );
}

// ── Admin Dashboard ───────────────────────────────────────────────
export function AdminDashboard() {
  const nav = useNavigate();
  const [stats,    setStats]    = useState(null);
  const [charts,   setCharts]   = useState(null);
  const [activity, setActivity] = useState([]);
  const [health,   setHealth]   = useState(null);

  const refresh = () => {
    getAdminStats().then(setStats).catch(()=>{});
    getAdminCharts().then(setCharts).catch(()=>{});
    getRecentActivity().then(setActivity).catch(()=>{});
    getHealthMetrics().then(setHealth).catch(()=>{});
  };

  useEffect(() => {
    refresh();
    const t = setInterval(() => {
      getHealthMetrics().then(setHealth).catch(()=>{});
      getRecentActivity().then(setActivity).catch(()=>{});
    }, 30000);
    return () => clearInterval(t);
  }, []);

  const lvlColor = l => l==='ERROR'?'var(--red)':l==='WARNING'?'var(--amber)':'var(--blue)';

  return (
    <AppShell>
      <PageHeader icon="🛡️" title="Admin Dashboard"
        right={<span style={{ background:'rgba(255,255,255,.15)',color:'rgba(255,255,255,.9)',padding:'4px 12px',borderRadius:999,fontSize:12,fontWeight:600 }}>
          Auto-refresh · 30s
        </span>} />
      <div className="page-content">

        <div className="flex gap-3 mb-4">
          {[['👥 Users','/admin/users'],['⚙️ Config','/admin/config'],['📋 Logs','/admin/logs']].map(([l,p])=>(
            <button key={p} className="btn btn-outline btn-sm" onClick={()=>nav(p)}>{l}</button>
          ))}
        </div>

        {/* FR136 — Stats */}
        <div className="grid-4 mb-4">
          {[
            {l:'Total Users',    v:stats?.total_users??'—',    c:'blue'},
            {l:'Total Sessions', v:stats?.total_sessions??'—', c:'purple'},
            {l:'Tests Run',      v:stats?.completed_jobs??'—', c:'green'},
            {l:'Active (7d)',    v:stats?.active_users_7d??'—',c:'amber'},
          ].map(({l,v,c})=>(
            <div key={l} className={`stat-card ${c}`}>
              <div className="stat-label">{l}</div>
              <div className="stat-value">{v}</div>
            </div>
          ))}
        </div>

        {/* FR138 — Charts */}
        {charts && (
          <div className="card mb-4">
            <div className="card-title" style={{marginBottom:16}}>📈 Activity — Last 14 Days</div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:24}}>
              <MiniBarChart days={charts.days} values={charts.registrations} color="var(--blue)"       label="New Registrations / Day" />
              <MiniBarChart days={charts.days} values={charts.sessions}      color="var(--purple-mid)" label="Testing Sessions / Day" />
              <MiniLineChart days={charts.days} values={charts.avg_scores}   color="var(--green)"      label="Avg Mutation Score (%) / Day" />
            </div>
          </div>
        )}

        {/* FR137 — Activity feed */}
        <div className="card mb-4">
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
            <div className="card-title" style={{margin:0}}>📡 Recent Activity</div>
            <button className="btn btn-secondary btn-sm" onClick={()=>nav('/admin/logs')}>View All Logs →</button>
          </div>
          {activity.length === 0 ? (
            <div style={{color:'var(--gray-400)',fontSize:13,fontStyle:'italic'}}>No recent activity.</div>
          ) : (
            <table className="data-table">
              <thead><tr><th>Time</th><th>Level</th><th>Category</th><th>Action</th><th>Result</th></tr></thead>
              <tbody>
                {activity.map(a=>(
                  <tr key={a.id}>
                    <td style={{fontSize:11,color:'var(--gray-500)',whiteSpace:'nowrap'}}>{new Date(a.created_at).toLocaleTimeString()}</td>
                    <td><span style={{fontSize:11,fontWeight:700,color:lvlColor(a.level)}}>{a.level}</span></td>
                    <td><span className="badge badge-gray" style={{fontSize:10}}>{a.category}</span></td>
                    <td style={{fontSize:12}}>{a.action}</td>
                    <td><span className={`badge ${a.outcome==='success'?'badge-green':'badge-red'}`} style={{fontSize:10}}>{a.outcome}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* FR158 — Health */}
        {health && !health.error && (
          <div className="card mb-4">
            <div className="card-title">🖥️ Server Health</div>
            <div className="grid-4" style={{gap:12}}>
              {[
                {l:'CPU',     v:`${health.cpu_pct?.toFixed(1)||0}%`,    warn:health.cpu_pct>80},
                {l:'Memory',  v:`${health.memory_pct?.toFixed(1)||0}%`, warn:health.memory_pct>80},
                {l:'Disk',    v:`${health.disk_pct?.toFixed(1)||0}%`,   warn:health.disk_pct>80},
                {l:'RAM',     v:`${health.memory_used_gb?.toFixed(1)||0}/${health.memory_total_gb?.toFixed(0)||0} GB`, warn:false},
              ].map(({l,v,warn})=>(
                <div key={l} className="stat-card" style={{textAlign:'center'}}>
                  <div className="stat-value" style={{fontSize:18,color:warn?'var(--red)':'var(--gray-800)'}}>{v}</div>
                  <div className="stat-label">{l}</div>
                  {warn && <div style={{fontSize:11,color:'var(--red)',marginTop:4}}>⚠ High</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

// ── Admin Users ───────────────────────────────────────────────────
export function AdminUsers() {
  const [users,        setUsers]        = useState([]);
  const [search,       setSearch]       = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [msg,          setMsg]          = useState('');

  const load = (s=search, f=statusFilter) => {
    listAdminUsers({ search:s||undefined, status:f||undefined })
      .then(setUsers).catch(()=>{});
  };
  useEffect(()=>{ load(); },[]);

  const act = async (fn, successMsg) => { await fn(); setMsg(successMsg); load(); };

  const FilterBtn = ({label, value}) => (
    <button className={`btn btn-sm ${statusFilter===value?'btn-primary':'btn-secondary'}`}
      onClick={()=>{ setStatusFilter(value); load(search, value); }}>{label}</button>
  );

  return (
    <AppShell>
      <PageHeader icon="👥" title="User Management"
        right={<input className="form-input"
          style={{width:240,height:34,fontSize:13,background:'rgba(255,255,255,.15)',borderColor:'rgba(255,255,255,.3)',color:'#fff'}}
          placeholder="🔍 Search users…" value={search}
          onChange={e=>{setSearch(e.target.value);load(e.target.value,statusFilter)}} />}
      />
      <div className="page-content">
        {msg && <div className="mb-3"><Alert type="success" onDismiss={()=>setMsg('')}>{msg}</Alert></div>}

        {/* FR141 — Filters (wired to backend) */}
        <div className="card mb-3">
          <div className="flex gap-2" style={{flexWrap:'wrap'}}>
            <FilterBtn label="All"           value="" />
            <FilterBtn label="✓ Verified"    value="verified" />
            <FilterBtn label="✗ Unverified"  value="unverified" />
            <FilterBtn label="● Active"      value="active" />
            <FilterBtn label="⊘ Suspended"   value="suspended" />
          </div>
        </div>

        <div className="card">
          <div style={{fontSize:12,color:'var(--gray-500)',marginBottom:8}}>{users.length} user(s) shown</div>
          <table className="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Org</th><th>Verified</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
            <tbody>
              {users.map(u=>(
                <tr key={u.id}>
                  <td style={{fontWeight:600}}>{u.first_name} {u.last_name}</td>
                  <td>{u.email}</td>
                  <td style={{color:'var(--gray-500)',fontSize:12}}>{u.organization||'—'}</td>
                  <td>{u.is_verified
                    ? <span className="badge badge-green">✓ Verified</span>
                    : <span className="badge badge-amber">✗ Pending</span>}
                  </td>
                  <td>{u.is_active
                    ? <span className="badge badge-green">Active</span>
                    : <span className="badge badge-red">Suspended</span>}
                  </td>
                  <td style={{fontSize:11,color:'var(--gray-500)'}}>{new Date(u.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="flex gap-1" style={{flexWrap:'wrap'}}>
                      {/* FR143 — Manual verify */}
                      {!u.is_verified && (
                        <button className="btn btn-outline btn-sm" style={{fontSize:11}}
                          onClick={()=>act(()=>adminVerifyEmail(u.id),'Email verified.')}>Verify</button>
                      )}
                      {/* FR144 — Suspend/Unsuspend */}
                      {u.is_active
                        ? <button className="btn btn-secondary btn-sm" style={{fontSize:11,color:'var(--amber)'}}
                            onClick={()=>act(()=>suspendUser(u.id),'User suspended.')}>Suspend</button>
                        : <button className="btn btn-secondary btn-sm" style={{fontSize:11,color:'var(--green)'}}
                            onClick={()=>act(()=>unsuspendUser(u.id),'User unsuspended.')}>Unsuspend</button>
                      }
                      {u.role!=='admin' && (
                        <button className="btn btn-secondary btn-sm" style={{fontSize:11,color:'var(--red)'}}
                          onClick={()=>setDeleteTarget(u)}>Delete</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {users.length===0 && <tr><td colSpan={7} style={{textAlign:'center',padding:20,color:'var(--gray-400)'}}>No users found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {deleteTarget && (
        <ConfirmModal title="Delete User"
          message={`Delete ${deleteTarget.first_name} ${deleteTarget.last_name} (${deleteTarget.email}) and all their data? This cannot be undone.`}
          confirmLabel="Delete User"
          onConfirm={async()=>{ await deleteUser(deleteTarget.id); load(); setDeleteTarget(null); }}
          onCancel={()=>setDeleteTarget(null)} />
      )}
    </AppShell>
  );
}

// ── Admin Config ──────────────────────────────────────────────────
export function AdminConfig() {
  const [config, setConfig] = useState([]);
  const [edits,  setEdits]  = useState({});
  const [saved,  setSaved]  = useState('');

  const reload = () => getSystemConfig().then(setConfig).catch(()=>{});
  useEffect(()=>{ reload(); },[]);

  const handleSave = async key => {
    const val = edits[key] ?? config.find(c=>c.key===key)?.value;
    await updateConfig(key, val);
    setSaved(key); setTimeout(()=>setSaved(''),2000);
    reload();
  };

  const regEnabled = config.find(c=>c.key==='registration_enabled')?.value === 'true';

  return (
    <AppShell>
      <PageHeader icon="⚙️" title="System Configuration" />
      <div className="page-content">

        {/* FR149 — Registration toggle */}
        <div className="card mb-4" style={{borderLeft:'4px solid var(--amber)',background:'var(--amber-light)'}}>
          <div style={{fontWeight:700,fontSize:14,marginBottom:8,color:'var(--amber)'}}>⚠ Registration Mode</div>
          <p style={{fontSize:13,color:'var(--gray-700)',marginBottom:12}}>
            Registration is currently <strong>{regEnabled?'OPEN — new users can sign up':'DISABLED — new sign-ups blocked'}</strong>.
          </p>
          <button className="btn btn-secondary btn-sm" onClick={async()=>{
            await updateConfig('registration_enabled', String(!regEnabled));
            reload();
          }}>
            {regEnabled ? '🔒 Disable Registration' : '🔓 Enable Registration'}
          </button>
        </div>

        {/* FR147 — Settings table */}
        <div className="card">
          <div className="card-title" style={{marginBottom:12}}>System Settings</div>
          <table className="data-table">
            <thead><tr><th>Setting</th><th>Value</th><th>Last Updated</th><th></th></tr></thead>
            <tbody>
              {config.filter(c=>c.key!=='registration_enabled').map(c=>(
                <tr key={c.key}>
                  <td style={{fontWeight:600}}>{c.key.replace(/_/g,' ').replace(/\b\w/g,x=>x.toUpperCase())}</td>
                  <td>
                    <input className="form-input" style={{height:32,fontSize:13}}
                      value={edits[c.key]??c.value}
                      onChange={e=>setEdits(ed=>({...ed,[c.key]:e.target.value}))} />
                  </td>
                  <td style={{fontSize:12,color:'var(--gray-500)'}}>{new Date(c.updated_at).toLocaleDateString()}</td>
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

// ── Admin Logs ────────────────────────────────────────────────────
export function AdminLogs() {
  const nav = useNavigate();
  const [logs,     setLogs]     = useState([]);
  const [level,    setLevel]    = useState('');
  const [category, setCategory] = useState('');
  const [search,   setSearch]   = useState('');
  const [errCount, setErrCount] = useState(0);

  const load = () => {
    getAuditLogs({ level:level||undefined, category:category||undefined, limit:200 })
      .then(setLogs).catch(()=>{});
    getAuditLogs({ level:'ERROR', limit:500 }).then(ls => {
      const cutoff = Date.now() - 86400000;
      setErrCount(ls.filter(l=>new Date(l.created_at).getTime()>cutoff).length);
    }).catch(()=>{});
  };
  useEffect(()=>{ load(); },[level,category]);

  const filtered = useMemo(()=>{
    if (!search) return logs;
    const q = search.toLowerCase();
    return logs.filter(l=>(l.message||'').toLowerCase().includes(q)||(l.action||'').toLowerCase().includes(q));
  },[logs,search]);

  const lvlColor = l => l==='ERROR'?'var(--red)':l==='WARNING'?'var(--amber)':'var(--blue)';

  return (
    <AppShell>
      <PageHeader icon="📋" title="Audit Logs"
        right={<input className="form-input"
          style={{width:240,height:34,fontSize:13,background:'rgba(255,255,255,.15)',borderColor:'rgba(255,255,255,.3)',color:'#fff'}}
          placeholder="🔍 Search messages…" value={search}
          onChange={e=>setSearch(e.target.value)} />}
      />
      <div className="page-content">
        <button className="btn btn-secondary btn-sm mb-4" onClick={()=>nav('/admin')}>← Back</button>

        {/* FR156 — Error alert */}
        {errCount > 0 && (
          <div className="mb-3">
            <Alert type="error">
              ⚠ <strong>{errCount}</strong> error(s) in the last 24 hours.
              {errCount > 50 ? ' High error rate — investigate immediately.' : ''}
            </Alert>
          </div>
        )}

        {/* FR154 — Filters */}
        <div className="card mb-4">
          <div className="flex gap-3" style={{alignItems:'flex-end',flexWrap:'wrap'}}>
            <div>
              <label className="form-label" style={{fontSize:11}}>Level</label>
              <select className="form-select" style={{height:34,fontSize:13}} value={level} onChange={e=>setLevel(e.target.value)}>
                <option value="">All Levels</option>
                <option>INFO</option><option>WARNING</option><option>ERROR</option>
              </select>
            </div>
            <div>
              <label className="form-label" style={{fontSize:11}}>Category</label>
              <select className="form-select" style={{height:34,fontSize:13}} value={category} onChange={e=>setCategory(e.target.value)}>
                <option value="">All Categories</option>
                <option>AUTH</option><option>TESTING</option><option>ADMIN</option><option>SYSTEM</option>
              </select>
            </div>
            <div style={{marginLeft:'auto'}}>
              <a href="/api/admin/logs/export/csv" className="btn btn-secondary btn-sm">⬇ Export CSV</a>
            </div>
          </div>
        </div>

        {/* FR153 — Log table */}
        <div className="card">
          <div style={{fontSize:12,color:'var(--gray-500)',marginBottom:8}}>{filtered.length} entries</div>
          <table className="data-table">
            <thead><tr><th>Timestamp</th><th>Level</th><th>Category</th><th>Action</th><th>Message</th><th>IP</th><th>Result</th></tr></thead>
            <tbody>
              {filtered.map(l=>(
                <tr key={l.id}>
                  <td style={{fontSize:11,color:'var(--gray-500)',whiteSpace:'nowrap'}}>{new Date(l.created_at).toLocaleString()}</td>
                  <td><span style={{fontSize:11,fontWeight:700,color:lvlColor(l.level)}}>{l.level}</span></td>
                  <td><span className="badge badge-gray" style={{fontSize:10}}>{l.category}</span></td>
                  <td style={{fontSize:12,fontFamily:'var(--mono)'}}>{l.action}</td>
                  <td style={{fontSize:12,maxWidth:300,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}} title={l.message}>{l.message}</td>
                  <td style={{fontSize:11,color:'var(--gray-500)'}}>{l.ip_address||'—'}</td>
                  <td><span className={`badge ${l.outcome==='success'?'badge-green':'badge-red'}`} style={{fontSize:10}}>{l.outcome}</span></td>
                </tr>
              ))}
              {filtered.length===0 && <tr><td colSpan={7} style={{textAlign:'center',padding:20,color:'var(--gray-400)'}}>No logs found</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
