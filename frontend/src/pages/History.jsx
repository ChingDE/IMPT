// src/pages/History.jsx — Test History with filters and search
import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSessions, deleteSession } from '../api/client';
import { AppShell, PageHeader, ConfirmModal } from '../components/UI';

const ScoreBadge = ({ score }) => {
  if (score == null || score === 0) return <span style={{ color:'var(--gray-400)', fontSize:13 }}>—</span>;
  const pct   = score <= 1 ? score * 100 : score;
  const color = pct >= 85 ? '#16a34a' : pct >= 70 ? '#ca8a04' : pct >= 55 ? '#ea580c' : '#dc2626';
  const bg    = pct >= 85 ? '#dcfce7' : pct >= 70 ? '#fef9c3' : pct >= 55 ? '#ffedd5' : '#fee2e2';
  return (
    <span style={{ fontWeight:700, fontSize:13, padding:'3px 10px',
      borderRadius:999, background:bg, color }}>{pct.toFixed(1)}%</span>
  );
};

const SELECT = ({ value, onChange, children }) => (
  <select value={value} onChange={e => onChange(e.target.value)}
    style={{ padding:'7px 10px', borderRadius:6, border:'1px solid var(--gray-200)',
      fontSize:13, color:'var(--gray-700)', background:'#fff', cursor:'pointer' }}>
    {children}
  </select>
);

export default function History() {
  const nav = useNavigate();
  const [sessions,     setSessions]     = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [search,       setSearch]       = useState('');
  const [filterLang,   setFilterLang]   = useState('all');
  const [filterStrat,  setFilterStrat]  = useState('all');
  const [filterDate,   setFilterDate]   = useState('all');
  const [sort,         setSort]         = useState('newest');
  const [page,         setPage]         = useState(1);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const PER_PAGE = 10;

  useEffect(() => {
    listSessions().then(setSessions).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const completedOnly = sessions.filter(s => s.status === 'completed');

  const filtered = useMemo(() => {
    const now = new Date();
    return completedOnly
      .filter(s => {
        if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false;
        if (filterLang  !== 'all' && s.language          !== filterLang)  return false;
        if (filterStrat !== 'all' && s.selected_strategy !== filterStrat) return false;
        if (filterDate  !== 'all') {
          const days = (now - new Date(s.updated_at || s.created_at)) / 86400000;
          if (days > parseInt(filterDate)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sort === 'newest')   return new Date(b.updated_at||b.created_at) - new Date(a.updated_at||a.created_at);
        if (sort === 'oldest')   return new Date(a.updated_at||a.created_at) - new Date(b.updated_at||b.created_at);
        if (sort === 'score_hi') return (b.mutation_score||0) - (a.mutation_score||0);
        if (sort === 'score_lo') return (a.mutation_score||0) - (b.mutation_score||0);
        return 0;
      });
  }, [completedOnly, search, filterLang, filterStrat, filterDate, sort]);

  const paged = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const pages = Math.ceil(filtered.length / PER_PAGE);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await deleteSession(deleteTarget.id);
    setSessions(s => s.filter(x => x.id !== deleteTarget.id));
    setDeleteTarget(null);
  };

  const exportCSV = () => {
    const rows = [
      ['Session Name', 'Language', 'Date', 'Mutation Score (%)', 'Mutants Executed', 'Total Mutants', 'Strategy', 'Time Saved (%)'],
      ...filtered.map(s => [
        s.name,
        s.language || '—',
        new Date(s.updated_at || s.created_at).toLocaleString(),
        s.mutation_score != null ? s.mutation_score.toFixed(1) : '—',
        s.executed_mutants ?? '—',
        s.total_mutants ?? '—',
        s.selected_strategy || '—',
        s.time_saved_pct != null ? s.time_saved_pct.toFixed(1) : '—',
      ])
    ];
    const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `impt-test-history-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell>
      <PageHeader icon="📋" title="Test History"
        right={
          <input className="form-input"
            style={{ width:240, height:34, fontSize:13, background:'rgba(255,255,255,.15)',
              borderColor:'rgba(255,255,255,.3)', color:'#fff' }}
            placeholder="🔍 Search sessions…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1); }} />
        }
      />
      <div className="page-content">
        {/* Filters */}
        <div className="card mb-4">
          <div style={{ display:'flex', gap:16, flexWrap:'wrap', alignItems:'flex-end' }}>
            <div>
              <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4, fontWeight:600, textTransform:'uppercase' }}>Language</div>
              <SELECT value={filterLang} onChange={v => { setFilterLang(v); setPage(1); }}>
                <option value="all">All Languages</option>
                <option value="javascript">JavaScript</option>
                <option value="java">Java</option>
              </SELECT>
            </div>
            <div>
              <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4, fontWeight:600, textTransform:'uppercase' }}>Strategy</div>
              <SELECT value={filterStrat} onChange={v => { setFilterStrat(v); setPage(1); }}>
                <option value="all">All Strategies</option>
                <option value="impt">IMPT Intelligent</option>
                <option value="operator_based">Operator-Based</option>
                <option value="random">Random</option>
              </SELECT>
            </div>
            <div>
              <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4, fontWeight:600, textTransform:'uppercase' }}>Date Range</div>
              <SELECT value={filterDate} onChange={v => { setFilterDate(v); setPage(1); }}>
                <option value="all">All Time</option>
                <option value="7">Last 7 Days</option>
                <option value="30">Last 30 Days</option>
                <option value="90">Last 90 Days</option>
              </SELECT>
            </div>
            <div>
              <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4, fontWeight:600, textTransform:'uppercase' }}>Sort</div>
              <SELECT value={sort} onChange={v => { setSort(v); setPage(1); }}>
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="score_hi">Highest Score</option>
                <option value="score_lo">Lowest Score</option>
              </SELECT>
            </div>
            <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
              <button className="btn btn-secondary btn-sm" onClick={exportCSV}>⬇ Export CSV</button>
              <button className="btn btn-primary btn-sm" onClick={() => nav('/new-session')}>+ New Session</button>
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="card">
          {loading ? (
            <div style={{ textAlign:'center', padding:40, color:'var(--gray-400)' }}>Loading…</div>
          ) : completedOnly.length === 0 ? (
            <div style={{ textAlign:'center', padding:'60px 20px' }}>
              <div style={{ fontSize:48, marginBottom:16 }}>🧬</div>
              <div style={{ fontSize:18, fontWeight:700, color:'var(--gray-700)', marginBottom:8 }}>No completed sessions yet</div>
              <div style={{ fontSize:14, color:'var(--gray-500)', marginBottom:24, lineHeight:1.65 }}>
                Complete your first mutation test to see history here.
              </div>
              <button className="btn btn-primary" onClick={() => nav('/new-session')}>🚀 Start a Test Session</button>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Session Name</th>
                    <th>Language</th>
                    <th>Test Date</th>
                    <th>Mutation Score</th>
                    <th>Mutants Tested</th>
                    <th>Strategy</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map(s => (
                    <tr key={s.id}>
                      <td style={{ fontWeight:600, cursor:'pointer', color:'var(--purple-mid)' }}
                        onClick={() => nav(`/results/${s.id}`)}>
                        {s.name}
                      </td>
                      <td><span className="badge badge-blue">{s.language || '—'}</span></td>
                      <td style={{ fontSize:12, color:'var(--gray-500)' }}>
                        {new Date(s.updated_at||s.created_at).toLocaleString('en-US',
                          { month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit' })}
                      </td>
                      <td><ScoreBadge score={s.mutation_score} /></td>
                      <td style={{ fontSize:13, color:'var(--gray-600)' }}>
                        {s.executed_mutants && s.total_mutants
                          ? `${s.executed_mutants} / ${s.total_mutants}` : '—'}
                      </td>
                      <td style={{ fontSize:12, color:'var(--gray-600)' }}>
                        {s.selected_strategy === 'impt'           ? '⭐ IMPT' :
                         s.selected_strategy === 'operator_based' ? '🔬 Operator' :
                         s.selected_strategy === 'random'         ? '🎲 Random' : '—'}
                      </td>
                      <td>
                        <div style={{ display:'flex', gap:6 }}>
                          <button className="btn btn-primary btn-sm"
                            onClick={() => nav(`/results/${s.id}`)}>View</button>
                          <button className="btn btn-secondary btn-sm"
                            onClick={() => nav(`/compare?a=${s.id}`)}>Compare</button>
                          <button className="btn btn-sm"
                            style={{ color:'var(--red)', border:'1px solid #fecaca', background:'#fff' }}
                            onClick={() => setDeleteTarget(s)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {paged.length === 0 && (
                    <tr><td colSpan={7} style={{ textAlign:'center', padding:20, color:'var(--gray-400)' }}>
                      No sessions match your filters
                    </td></tr>
                  )}
                </tbody>
              </table>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginTop:16 }}>
                <span style={{ fontSize:13, color:'var(--gray-500)' }}>
                  Showing {paged.length} of {filtered.length} sessions
                </span>
                {pages > 1 && (
                  <div className="pagination">
                    <button className="page-num" onClick={() => setPage(Math.max(1, page - 1))}>←</button>
                    {Array.from({ length: Math.min(pages, 5) }, (_, i) => i + 1).map(p => (
                      <button key={p} className={`page-num ${p === page ? 'active' : ''}`}
                        onClick={() => setPage(p)}>{p}</button>
                    ))}
                    {pages > 5 && <span style={{ padding:'0 4px', color:'var(--gray-400)' }}>…</span>}
                    <button className="page-num" onClick={() => setPage(Math.min(pages, page + 1))}>→</button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
      {deleteTarget && (
        <ConfirmModal title="Delete Session"
          message={`Delete "${deleteTarget.name}"? This cannot be undone.`}
          confirmLabel="Delete" onConfirm={handleDelete} onCancel={() => setDeleteTarget(null)} />
      )}
    </AppShell>
  );
}
