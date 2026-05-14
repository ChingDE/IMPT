// src/pages/History.jsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSessions, deleteSession } from '../api/client';
import { AppShell, PageHeader, StatusBadge, ConfirmModal } from '../components/UI';

export default function History() {
  const nav = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [search, setSearch]     = useState('');
  const [filter, setFilter]     = useState('all');
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [page, setPage]         = useState(1);
  const PER_PAGE = 10;

  useEffect(() => { listSessions().then(setSessions).catch(()=>{}); }, []);

  const filtered = sessions.filter(s => {
    const matchSearch = !search || s.name.toLowerCase().includes(search.toLowerCase());
    const matchFilter = filter === 'all' || s.status === filter;
    return matchSearch && matchFilter;
  });

  const paged = filtered.slice((page-1)*PER_PAGE, page*PER_PAGE);
  const pages = Math.ceil(filtered.length / PER_PAGE);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await deleteSession(deleteTarget.id);
    setSessions(s => s.filter(x => x.id !== deleteTarget.id));
    setDeleteTarget(null);
  };

  return (
    <AppShell>
      <PageHeader icon="📋" title="Test History"
        right={
          <input className="form-input" style={{width:240,height:34,fontSize:13,background:'rgba(255,255,255,.15)',borderColor:'rgba(255,255,255,.3)',color:'#fff'}}
            placeholder="🔍 Search sessions…" value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}} />
        }
      />
      <div className="page-content">
        <div className="card mb-4">
          <div className="flex gap-2 flex-wrap">
            {['all','not_started','running','completed','failed'].map(f=>(
              <button key={f} className={`btn btn-sm ${filter===f?'btn-primary':'btn-secondary'}`}
                onClick={()=>{setFilter(f);setPage(1)}}>
                {f === 'all' ? 'All' : f.replace('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <table className="data-table">
            <thead><tr><th>Session Name</th><th>Language</th><th>Status</th><th>Created</th><th>Last Modified</th><th>Actions</th></tr></thead>
            <tbody>
              {paged.map(s=>(
                <tr key={s.id}>
                  <td className="bold" style={{cursor:'pointer'}} onClick={() => {
                      const id = s.id;
                      if (s.status === 'completed')  return nav(`/results/${id}`);
                      if (s.status === 'running')    return nav(`/running/${id}`);
                      if (s.status === 'ready')      return nav(`/sessions/${id}/review`);
                      if (s.status === 'configured') return nav(`/sessions/${id}/budget`);
                      if (s.status === 'uploaded')   return nav(`/sessions/${id}/operators`);
                      return nav(`/sessions/${id}/upload`);
                    }}>{s.name}</td>
                  <td><span className="badge badge-blue">{s.language}</span></td>
                  <td><StatusBadge status={s.status} /></td>
                  <td className="text-muted text-sm">{new Date(s.created_at).toLocaleDateString()}</td>
                  <td className="text-muted text-sm">{new Date(s.updated_at).toLocaleDateString()}</td>
                  <td>
                    <div className="flex gap-2">
                      {s.status === 'completed' && <button className="btn btn-primary btn-sm" onClick={()=>nav(`/results/${s.id}`)}>View</button>}
                      <button className="btn btn-secondary btn-sm" style={{color:'var(--red)'}} onClick={()=>setDeleteTarget(s)}>Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
              {paged.length===0 && <tr><td colSpan={6} style={{textAlign:'center',padding:20,color:'var(--gray-400)'}}>No sessions found</td></tr>}
            </tbody>
          </table>
          <div className="flex items-center justify-between mt-4">
            <span className="text-muted text-sm">Showing {Math.min(filtered.length,PER_PAGE)} of {filtered.length} sessions</span>
            {pages>1 && (
              <div className="pagination">
                <button className="page-num" onClick={()=>setPage(Math.max(1,page-1))}>←</button>
                {Array.from({length:Math.min(pages,5)},(_,i)=>i+1).map(p=>(
                  <button key={p} className={`page-num ${p===page?'active':''}`} onClick={()=>setPage(p)}>{p}</button>
                ))}
                <button className="page-num" onClick={()=>setPage(Math.min(pages,page+1))}>→</button>
              </div>
            )}
          </div>
        </div>
      </div>
      {deleteTarget && <ConfirmModal title="Delete Session" message={`Delete "${deleteTarget.name}"? This cannot be undone.`}
        confirmLabel="Delete" onConfirm={handleDelete} onCancel={()=>setDeleteTarget(null)} />}
    </AppShell>
  );
}
