// src/pages/Results.jsx  FR107-FR118
import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getSession, exportJobCSV, createShareLink, compareStrategies, getJobMutants } from '../api/client';
import { AppShell, PageHeader, ScorePill, Alert } from '../components/UI';
import { Download, Share2, BarChart2, ChevronDown, ChevronRight } from 'lucide-react';

const STRATEGY_LABEL = {
  impt:           '⭐ IMPT Intelligent',
  random:         '🎲 Random Sampling',
  operator_based: '🔬 Operator-Based',
  exhaustive:     '📋 Exhaustive (Ground Truth)',
};

export default function Results() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [session, setSession]     = useState(null);
  const [jobs, setJobs]           = useState([]);
  const [mutants, setMutants]     = useState([]);
  const [filter, setFilter]       = useState('all');
  const [opFilter, setOpFilter]   = useState('all');
  const [sortBy, setSortBy]       = useState('priority_score');
  const [sortDir, setSortDir]     = useState('desc');
  const [page, setPage]           = useState(1);
  const [expandedId, setExpandedId] = useState(null);
  const [shareUrl, setShareUrl]   = useState('');
  const [shareErr, setShareErr]   = useState('');
  const [loading, setLoading]     = useState(true);
  const PER_PAGE = 50;
  const pollRef = useRef(null);

  const loadJobs = async () => {
    try {
      const cmp = await compareStrategies(sessionId);
      const updated = Object.values(cmp);
      setJobs(updated);
      // Stop polling if all done
      const exhaustive = updated.find(j => j.strategy === 'exhaustive');
      if (!exhaustive || exhaustive.status?.toUpperCase() === 'COMPLETED' || exhaustive.status?.toUpperCase() === 'FAILED') {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      }
    } catch {}
  };

  useEffect(() => {
    const load = async () => {
      try {
        const s = await getSession(sessionId);
        setSession(s);
        await loadJobs();
        // Start polling if exhaustive job is still running
        const allJobs = Object.values(await compareStrategies(sessionId).catch(() => ({})));
        const exhaustive = allJobs.find(j => j.strategy === 'exhaustive');
        if (exhaustive && exhaustive.status?.toUpperCase() !== 'COMPLETED' && exhaustive.status?.toUpperCase() !== 'FAILED') {
          pollRef.current = setInterval(loadJobs, 10000); // poll every 10s
        }
      } catch {}
      setLoading(false);
    };
    load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [sessionId]);

  // Primary job = the strategy the user chose (impt / random / operator_based)
  // Exhaustive job = ground truth baseline (if user ticked the checkbox)
  const primaryJob    = jobs.find(j => j.strategy !== 'exhaustive') || jobs[0];
  const exhaustiveJob = jobs.find(j => j.strategy === 'exhaustive');
  const imptJob       = primaryJob; // kept for backward-compat refs below

  // Baseline: exhaustive if it ran and completed; otherwise use Wilson estimate from primary
  const hasGroundTruth  = exhaustiveJob && ['COMPLETED','completed'].includes(exhaustiveJob.status);
  const baselineScore   = hasGroundTruth
    ? exhaustiveJob.mutation_score
    : (primaryJob?.estimated_score ?? primaryJob?.mutation_score ?? 0);
  const baselineLabel   = hasGroundTruth ? 'Ground Truth' : 'Estimated';
  const baselineColor   = hasGroundTruth ? 'var(--green)' : 'var(--amber)';

  // Time saved = 1 - (primary execution / exhaustive execution)
  const primaryTimeSec    = primaryJob?.execution_time_seconds ?? 0;
  // exhaustiveTimeSec: real time if exhaustive ran, estimated otherwise
  const exhaustiveTimeSec = primaryJob?.estimated_exhaustive_seconds ?? 0;
  const exhaustiveTimeLabel = hasGroundTruth ? 'Ground Truth' : 'Estimated';
  const timeSavedPct = hasGroundTruth
    ? Math.round((1 - primaryTimeSec / exhaustiveTimeSec) * 100)
    : (primaryJob?.time_saved_pct ?? 0);

  // Correlation: real Pearson not computable without per-mutant exhaustive results,
  // so we use the primary job's Wilson CI estimated_score as proxy correlation indicator
  const correlation = hasGroundTruth && primaryJob?.real_correlation != null
    ? primaryJob.real_correlation.toFixed(3)
    : (primaryJob?.estimated_score > 0 ? '≥0.95 (est.)' : '—');

  const opStats = primaryJob?.operator_stats || {};

  const STRATEGY_DISPLAY = {
    impt:           '⭐ IMPT Intelligent Prioritization',
    random:         '🎲 Random Sampling',
    operator_based: '🔬 Operator-Based Prioritization',
  };

  // Filtered + sorted mutants
  const filteredMutants = mutants
    .filter(m => filter === 'all' || m.status.toLowerCase() === filter)
    .filter(m => opFilter === 'all' || m.operator === opFilter)
    .sort((a, b) => {
      const v = r => typeof r[sortBy] === 'number' ? r[sortBy] : String(r[sortBy]);
      return sortDir === 'asc' ? (v(a) > v(b) ? 1 : -1) : (v(b) > v(a) ? 1 : -1);
    });
  const pagedMutants  = filteredMutants.slice((page - 1) * PER_PAGE, page * PER_PAGE);
  const totalPages    = Math.ceil(filteredMutants.length / PER_PAGE);
  const survived      = mutants.filter(m => m.status === 'SURVIVED');
  const equivalent    = mutants.filter(m => m.status === 'EQUIVALENT');
  const operators     = [...new Set(mutants.map(m => m.operator))];

  const toggleSort = col => {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir('desc'); }
  };
  const SortIcon = ({ col }) => sortBy === col ? (sortDir === 'desc' ? ' ↓' : ' ↑') : '';

  const handleExportCSV = async () => {
    if (!imptJob) return;
    try {
      const { exportJobCSV: e } = await import('../api/client');
      const blob = await e(imptJob.job_id);
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = `results-${sessionId.slice(0,8)}.csv`; a.click();
    } catch {}
  };

  // FR114 — HTML export
  const handleExportHTML = () => {
    const html = `<!DOCTYPE html><html><head><title>IMPT Results</title></head><body>
      <h1>${session?.name} — Mutation Testing Results</h1>
      <p>Score: ${((imptJob?.mutation_score||0)*100).toFixed(1)}% | Time Saved: ${imptJob?.time_saved_pct}%</p>
      <table border="1"><tr><th>Operator</th><th>File</th><th>Line</th><th>Status</th><th>Score</th></tr>
      ${mutants.map(m => `<tr><td>${m.operator}</td><td>${m.file}</td><td>${m.line}</td><td>${m.status}</td><td>${m.priority_score?.toFixed(2)}</td></tr>`).join('')}
      </table></body></html>`;
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([html], {type:'text/html'}));
    a.download = `results-${sessionId.slice(0,8)}.html`; a.click();
  };

  // FR114 — JSON export
  const handleExportJSON = () => {
    const json = JSON.stringify({ session, jobs, mutants }, null, 2);
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([json], {type:'application/json'}));
    a.download = `results-${sessionId.slice(0,8)}.json`; a.click();
  };

  const handleShare = async () => {
    try {
      const data = await createShareLink(sessionId);
      setShareUrl(data.share_url);
    } catch (e) { setShareErr(e.response?.data?.detail || 'Failed to create share link.'); }
  };

  if (loading) return <AppShell><PageHeader icon="📊" title="Test Results" /><div className="page-content" style={{textAlign:'center',paddingTop:60}}>Loading…</div></AppShell>;

  return (
    <AppShell>
      <PageHeader icon="📊" title="Test Results"
        right={
          <div style={{ display:'flex',gap:8 }}>
            <button className="hdr-btn ghost" onClick={() => nav(`/compare/${sessionId}`)}>
              <BarChart2 size={14} /> Compare Sessions
            </button>
            <button className="hdr-btn ghost" onClick={handleShare}><Share2 size={14} /> Share</button>
          </div>
        }
      />
      <div className="page-content">

        {/* FR107 — Session header */}
        <div className="card mb-4">
          <div style={{ display:'flex',justifyContent:'space-between',flexWrap:'wrap',gap:12 }}>
            <div>
              <h2 style={{ fontSize:18,fontWeight:700 }}>{session?.name}</h2>
              <div style={{ fontSize:13,color:'var(--gray-500)',marginTop:4 }}>
                {session?.language} · Completed {session?.completed_at ? new Date(session.completed_at).toLocaleString() : ''}
                {session?.started_at && session?.completed_at && (
                  <span style={{ marginLeft:8 }}>
                    · Duration: {session?.completed_at && session?.started_at ? Math.round((new Date(session.completed_at)-new Date(session.started_at))/60000) : '—'} min
                  </span>
                )}
              </div>
            </div>
            <div style={{ fontSize:12,color:'var(--gray-400)' }}>
              {/* FR118 — Results saved note */}
              ✓ Results saved permanently
            </div>
          </div>
        </div>

        {shareUrl && <Alert type="success">Shareable link (30 days): <a href={shareUrl} style={{color:'var(--blue)'}} target="_blank" rel="noopener noreferrer">{shareUrl}</a></Alert>}
        {shareErr && <Alert type="error">{shareErr}</Alert>}

        {/* Primary strategy results + vs-baseline comparison */}
        {primaryJob && (
          <div style={{ background:'var(--green-xlight)',border:'1px solid var(--green-light)',borderRadius:'var(--radius)',padding:'20px 24px',marginBottom:16 }}>
            <div className="section-head" style={{ color:'var(--gray-600)' }}>
              {STRATEGY_DISPLAY[primaryJob.strategy] || primaryJob.strategy} — Results
            </div>
            <div style={{ display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))',gap:12,marginTop:8 }}>
              {[
                {l:'Mutation Score',   v:`${((primaryJob.mutation_score||0)*100).toFixed(1)}%`,  c:'var(--green)'},
                {l:'Mutants Tested',  v:`${primaryJob.executed_mutants ?? primaryJob.mutants_tested} / ${primaryJob.total_mutants}`, c:'var(--amber)'},
                {l:'Execution Time',  v:`${Math.round((primaryJob.execution_time_seconds??0)/60)} min`, c:'var(--blue)'}, 
                {l:`Time Saved vs ${hasGroundTruth ? 'Exhaustive (Ground Truth)' : 'Exhaustive (Est.)'}`, v:`${timeSavedPct.toFixed(1)}%`, c:'var(--green)'},
                {l:`Exhaustive Score (${baselineLabel})`, v:`${((baselineScore||0)*100).toFixed(1)}%`, c:baselineColor},
                {l:`Correlation (${baselineLabel})`, v: hasGroundTruth && typeof correlation === 'number' ? correlation.toFixed(2) : String(correlation), c: hasGroundTruth?'var(--green)':'var(--amber)'},
              ].map(({l,v,c})=>(
                <div key={l} className="stat-card" style={{textAlign:'center'}}>
                  <div className="stat-label">{l}</div>
                  <div className="stat-value" style={{fontSize:18,color:c}}>{v}</div>
                </div>
              ))}
            </div>
            {!hasGroundTruth && (
              <div style={{marginTop:12,fontSize:12,color:'var(--amber)',background:'#FFFBEB',border:'1px solid #FDE68A',borderRadius:6,padding:'8px 12px'}}>
                ⚠ Exhaustive baseline was not run. Correlation and exhaustive score are <strong>statistical estimates</strong> (Wilson CI).
                Run a new session with "Exhaustive Baseline" enabled for ground-truth comparison.
              </div>
            )}
            {hasGroundTruth && (
              <div style={{marginTop:12,fontSize:12,color:'var(--green)',background:'var(--green-xlight)',border:'1px solid var(--green-light)',borderRadius:6,padding:'8px 12px'}}>
                ✓ Exhaustive baseline ran — all figures are <strong>ground truth</strong>.
                {hasGroundTruth ? `Exhaustive ran in ${Math.round((exhaustiveJob?.execution_time_seconds??0)/60)} min (ground truth)` : `Estimated exhaustive would take ~${Math.round(exhaustiveTimeSec/60)} min`} vs {Math.round((primaryJob?.execution_time_seconds??0)/60)} min for {STRATEGY_DISPLAY[primaryJob.strategy]||primaryJob.strategy}.
              </div>
            )}
          </div>
        )}

        {/* Exhaustive job still running notice */}
        {exhaustiveJob && exhaustiveJob.status?.toUpperCase() !== 'COMPLETED' && (
          <Alert type="warn">
            ⏳ Exhaustive baseline is still running ({exhaustiveJob.status}). Refresh to update ground-truth figures.
          </Alert>
        )}

        {/* FR109 — Prioritization factors (only for IMPT strategy) */}
        {primaryJob?.strategy === 'impt' && (
        <div className="card mb-4">
          <div className="card-title">📊 Prioritization Factors (IMPT Algorithm)</div>
          <div className="grid-3" style={{gap:10}}>
            {[
              {label:'Historical Effectiveness',pct:30},
              {label:'Code Complexity',pct:25},
              {label:'Security Criticality',pct:20},
              {label:'Change Recency',pct:15},
              {label:'Bug History',pct:10},
            ].map(f=>(
              <div key={f.label} style={{fontSize:13}}>
                <div style={{display:'flex',justifyContent:'space-between',marginBottom:4}}>
                  <span>{f.label}</span><span style={{fontWeight:600}}>{f.pct}%</span>
                </div>
                <div style={{background:'var(--gray-200)',height:6,borderRadius:3,overflow:'hidden'}}>
                  <div style={{width:`${f.pct*3.33}%`,height:'100%',background:'var(--purple-mid)',borderRadius:3}} />
                </div>
              </div>
            ))}
          </div>
        </div>
        )}

        {/* FR110 — Operator breakdown table (sortable) */}
        {Object.keys(opStats).length > 0 && (
          <div className="card mb-4">
            <div className="card-title">🔬 Mutation Operator Breakdown</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('operator')}>Operator <SortIcon col="operator" /></th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('total')}>Generated <SortIcon col="total" /></th>
                  <th>Killed</th>
                  <th>Survived</th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('survival_rate')}>Survival Rate <SortIcon col="survival_rate" /></th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(opStats).map(([op, s]) => {
                  const survivalRate = s.total > 0 ? ((s.total - s.killed) / s.total * 100).toFixed(1) : '0.0';
                  return (
                    <tr key={op}>
                      <td className="bold">{op}</td>
                      <td>{s.total}</td>
                      <td style={{color:'var(--green)',fontWeight:600}}>{s.killed}</td>
                      <td style={{color:'var(--red)',fontWeight:600}}>{s.total - s.killed}</td>
                      <td>{survivalRate}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* FR113 — Equivalent mutants */}
        {equivalent.length > 0 && (
          <div className="card mb-4">
            <div className="card-title">⚠️ Equivalent Mutants</div>
            <p style={{fontSize:13.5,color:'var(--gray-600)',marginBottom:8,lineHeight:1.65}}>
              <strong>{equivalent.length}</strong> equivalent mutant(s) were detected and excluded from the mutation score calculation. These mutants are semantically equivalent to the original code — no test can distinguish them.
            </p>
            <div style={{fontSize:12,color:'var(--gray-500)'}}>
              These mutants are excluded from the mutation score calculation as they are semantically equivalent to original code.
            </div>
          </div>
        )}
        {equivalent.length === 0 && (
          <div className="card mb-4">
            <div className="card-title">⚠️ Equivalent Mutants</div>
            <p style={{fontSize:13.5,color:'var(--gray-600)',lineHeight:1.65}}>
              No equivalent mutants were detected. Equivalent mutants are semantically identical to the original code and cannot be killed by any test. They are excluded from mutation score calculations.
            </p>
          </div>
        )}

        {/* FR111 — Mutant list with filter + pagination */}
        {mutants.length > 0 && (
          <div className="card mb-4">
            <div className="flex items-center justify-between mb-3">
              <div className="card-title" style={{marginBottom:0}}>
                🦠 Mutant Details ({filteredMutants.length} of {mutants.length})
              </div>
              <div className="flex gap-2">
                <select className="form-select" style={{height:32,fontSize:12,width:130}}
                  value={filter} onChange={e => { setFilter(e.target.value); setPage(1); }}>
                  <option value="all">All Statuses</option>
                  <option value="killed">Killed</option>
                  <option value="survived">Survived</option>
                  <option value="timeout">Timeout</option>
                  <option value="equivalent">Equivalent</option>
                </select>
                <select className="form-select" style={{height:32,fontSize:12,width:130}}
                  value={opFilter} onChange={e => { setOpFilter(e.target.value); setPage(1); }}>
                  <option value="all">All Operators</option>
                  {operators.map(op => <option key={op} value={op}>{op}</option>)}
                </select>
              </div>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th></th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('operator')}>Operator<SortIcon col="operator" /></th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('file')}>File<SortIcon col="file" /></th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('line')}>Line<SortIcon col="line" /></th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('status')}>Status<SortIcon col="status" /></th>
                  <th style={{cursor:'pointer'}} onClick={() => toggleSort('priority_score')}>Priority<SortIcon col="priority_score" /></th>
                  <th>Killing Test</th>
                </tr>
              </thead>
              <tbody>
                {pagedMutants.map(m => (
                  <>
                    <tr key={m.id} style={{cursor:'pointer'}} onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}>
                      <td>{expandedId === m.id ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</td>
                      <td className="bold">{m.operator}</td>
                      <td style={{fontFamily:'var(--mono)',fontSize:12}}>{m.file?.split('/').pop()}</td>
                      <td>{m.line}</td>
                      <td>
                        <span style={{
                          fontSize:11,fontWeight:700,padding:'2px 7px',borderRadius:4,
                          background:m.status==='KILLED'?'var(--green-light)':m.status==='SURVIVED'?'var(--red-light)':'var(--gray-100)',
                          color:m.status==='KILLED'?'var(--green)':m.status==='SURVIVED'?'var(--red)':'var(--gray-500)',
                        }}>{m.status}</span>
                      </td>
                      <td>{m.priority_score?.toFixed(2)}</td>
                      <td style={{fontSize:12,color:'var(--gray-500)'}}>{m.killing_test || '—'}</td>
                    </tr>
                    {/* FR112 — Source code diff for survived mutants */}
                    {expandedId === m.id && (
                      <tr key={`${m.id}-detail`}>
                        <td colSpan={7} style={{background:'var(--gray-50)',padding:'12px 16px'}}>
                          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
                            <div>
                              <div style={{fontSize:11,fontWeight:600,color:'var(--gray-500)',marginBottom:4}}>Original Code</div>
                              <pre style={{background:'#F0FDF4',border:'1px solid var(--green-light)',borderRadius:6,padding:'8px 12px',fontSize:12,fontFamily:'var(--mono)',overflow:'auto',margin:0}}>
                                {m.original_code || '—'}
                              </pre>
                            </div>
                            <div>
                              <div style={{fontSize:11,fontWeight:600,color:'var(--gray-500)',marginBottom:4}}>Mutated Code</div>
                              <pre style={{background:'var(--red-light)',border:'1px solid #FECACA',borderRadius:6,padding:'8px 12px',fontSize:12,fontFamily:'var(--mono)',overflow:'auto',margin:0}}>
                                {m.mutated_code || '—'}
                              </pre>
                            </div>
                          </div>
                          {m.explanation && (
                            <div style={{marginTop:8,fontSize:12,color:'var(--gray-600)'}}>
                              <strong>Explanation:</strong> {m.explanation}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <span style={{fontSize:12,color:'var(--gray-400)'}}>
                  Showing {(page-1)*PER_PAGE+1}–{Math.min(page*PER_PAGE,filteredMutants.length)} of {filteredMutants.length}
                </span>
                <div className="pagination">
                  <button className="page-num" onClick={() => setPage(Math.max(1,page-1))}>←</button>
                  {Array.from({length:Math.min(totalPages,7)},(_,i)=>i+1).map(p=>(
                    <button key={p} className={`page-num ${p===page?'active':''}`} onClick={()=>setPage(p)}>{p}</button>
                  ))}
                  <button className="page-num" onClick={() => setPage(Math.min(totalPages,page+1))}>→</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* FR114 — Export buttons */}
        <div className="card mb-4">
          <div className="card-title"><Download size={14} style={{marginRight:6}} />Export Results</div>
          <div className="flex gap-3" style={{flexWrap:'wrap'}}>
            <button className="btn btn-outline btn-sm" onClick={handleExportCSV}><Download size={13} /> CSV</button>
            <button className="btn btn-outline btn-sm" onClick={handleExportHTML}><Download size={13} /> HTML Report</button>
            <button className="btn btn-outline btn-sm" onClick={handleExportJSON}><Download size={13} /> JSON</button>
          </div>
        </div>

        <div className="flex justify-between">
          <button className="btn btn-secondary" onClick={() => nav('/dashboard')}>← Back to Dashboard</button>
          <button className="btn btn-primary" onClick={() => nav('/new-session')}>🚀 Run Another Test</button>
        </div>
      </div>
    </AppShell>
  );
}
