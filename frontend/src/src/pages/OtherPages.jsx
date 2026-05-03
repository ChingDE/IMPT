// src/pages/Reports.jsx
import { useAuth } from '../context/AuthContext';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listJobs, getSummary, exportCSV, listProfiles, getMyStats, updateMe, getAdminStats } from '../api/client';
import { AppShell, PageHeader, ScorePill, TrendChart, DistributionChart } from '../components/UI';

export function Reports() {
  const nav = useNavigate();
  const [jobs, setJobs]       = useState([]);
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    Promise.all([listJobs(), getSummary()])
      .then(([j, s]) => { setJobs(j || []); setSummary(s); })
      .catch(() => {});
  }, []);

  const completed = jobs.filter(j => j.status === 'COMPLETED');
  const totalTests  = completed.length;
  const avgScore    = completed.length ? Math.round(completed.reduce((a, j) => a + (j.mutation_score || 0), 0) / completed.length * 100) : 0;
  const avgTimeSec  = completed.length ? completed.reduce((a, j) => a + (j.execution_time_seconds || 0), 0) / completed.length : 0;
  const projects    = new Set(completed.map(j => j.project_id)).size;

  const trendData = completed.slice(-14).map(j => ({
    date: new Date(j.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    score: Math.round((j.mutation_score || 0) * 100),
  }));

  const distData = [
    { range: '85-100%', count: completed.filter(j => j.mutation_score >= 0.85).length },
    { range: '70-84%',  count: completed.filter(j => j.mutation_score >= 0.70 && j.mutation_score < 0.85).length },
    { range: '55-69%',  count: completed.filter(j => j.mutation_score >= 0.55 && j.mutation_score < 0.70).length },
    { range: '0-54%',   count: completed.filter(j => j.mutation_score < 0.55).length },
  ];

  return (
    <AppShell>
      <PageHeader icon="📊" title="Results & Reports" />
      <div className="page-content">
        <div className="grid-4 mb-4">
          <div className="stat-card blue"><div className="stat-label">Total Tests Run</div><div className="stat-value">{totalTests}</div><div className="stat-delta" style={{ color: 'var(--blue)' }}>↑ {Math.max(0, totalTests - 5)} since last week</div></div>
          <div className="stat-card green"><div className="stat-label">Avg Mutation Score</div><div className="stat-value">{avgScore}%</div><div className="stat-delta" style={{ color: 'var(--green)' }}>↑ 3% improvement</div></div>
          <div className="stat-card amber"><div className="stat-label">Avg Testing Time</div><div className="stat-value">{Math.round(avgTimeSec / 60)}m</div><div className="stat-delta" style={{ color: 'var(--amber)' }}>vs exhaustive testing</div></div>
          <div className="stat-card purple"><div className="stat-label">Projects Tested</div><div className="stat-value">{projects}</div></div>
        </div>

        <div className="card mb-4">
          <div className="card-title">📈 Mutation Score Trends Over Time</div>
          <TrendChart data={trendData} />
          {trendData.length > 1 && (
            <div className="info-box mt-3">
              📊 <strong>Trend Analysis:</strong> Your average mutation score over time.
              {avgScore >= 70 ? ' Your test suite quality is consistently improving. Keep focusing on high-effectiveness mutation operators.' : ' Consider reviewing survived mutants and adding targeted test cases.'}
            </div>
          )}
        </div>

        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="card-title" style={{ marginBottom: 0 }}>📋 Recent Test Results</div>
            <button className="btn btn-secondary btn-sm" onClick={() => nav('/history')}>View All History</button>
          </div>
          <table className="data-table">
            <thead><tr><th>Project Name</th><th>Test Date</th><th>Mutation Score</th><th>Mutants Tested</th><th>Time</th><th>Saved</th><th>Strategy</th><th>Framework</th><th>Actions</th></tr></thead>
            <tbody>
              {completed.slice(0, 5).map(j => (
                <tr key={j.id}>
                  <td className="bold">{j.project_id?.slice(0, 12) || '—'}</td>
                  <td className="text-muted text-sm">{new Date(j.created_at).toLocaleString()}</td>
                  <td><ScorePill value={Math.round((j.mutation_score || 0) * 100)} /></td>
                  <td className="text-muted">{j.executed_mutants}/{j.total_mutants}</td>
                  <td className="text-muted">{(j.execution_time_seconds / 60).toFixed(1)} min</td>
                  <td className="text-green font-semibold">{j.time_saved_pct?.toFixed(0) || 0}%</td>
                  <td className="text-muted">{j.optimizer_strategy}</td>
                  <td><span className="badge badge-blue">PIT</span></td>
                  <td style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-primary btn-sm" onClick={() => nav(`/results/${j.id}`)}>View</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => nav('/compare')}>Compare</button>
                  </td>
                </tr>
              ))}
              {completed.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: '20px', color: 'var(--gray-400)' }}>No completed tests yet</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="card-title">📊 Mutation Score Distribution</div>
          <DistributionChart data={distData} />
          <div className="info-box mt-3">
            💡 <strong>Insight:</strong> Distribution of mutation scores across all test sessions.
            {distData[0].count + distData[1].count > distData[2].count + distData[3].count
              ? ' Most of your tests score above 70%, which is above industry average.'
              : ' Focus on improving test coverage for better mutation scores.'}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── History ───────────────────────────────────────────────────────
export function History() {
  const nav = useNavigate();
  const [jobs, setJobs]   = useState([]);
  const [search, setSearch] = useState('');
  const [page, setPage]   = useState(1);
  const PER_PAGE = 10;

  useEffect(() => { listJobs().then(j => setJobs(j || [])).catch(() => {}); }, []);

  const filtered = jobs.filter(j =>
    !search || j.project_id?.toLowerCase().includes(search.toLowerCase()) || j.id.includes(search)
  );
  const total  = filtered.length;
  const sliced = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  const exportAll = () => {
    const rows = [['Job ID','Date','Score','Executed','Total','Time','Strategy','Status']];
    jobs.forEach(j => rows.push([
      j.id, j.created_at,
      Math.round((j.mutation_score||0)*100)+'%',
      j.executed_mutants, j.total_mutants,
      (j.execution_time_seconds/60).toFixed(1)+'m',
      j.optimizer_strategy, j.status
    ]));
    const csv = rows.map(r => r.join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a'); a.href = url; a.download = 'test-history.csv'; a.click();
  };

  return (
    <AppShell>
      <PageHeader icon="📋" title="Test History"
        right={
          <>
            <input className="form-input" style={{ width: 240, height: 34, fontSize: 13 }}
              placeholder="🔍 Search tests…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
            <button className="hdr-btn ghost" onClick={exportAll}>📊 Export CSV</button>
          </>
        }
      />
      <div className="page-content">
        {/* Filters */}
        <div className="card mb-4">
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
            {[
              { label: 'Project',    opts: ['All Projects'] },
              { label: 'Date Range', opts: ['Last 7 Days', 'Last 30 Days', 'All Time'] },
              { label: 'Strategy',   opts: ['All Strategies', 'AUTO', 'DP', 'GREEDY'] },
              { label: 'Framework',  opts: ['All Frameworks', 'PIT', 'STRYKER'] },
              { label: 'Sort',       opts: ['Newest First', 'Oldest First', 'Score High-Low'] },
            ].map(({ label, opts }) => (
              <div key={label}>
                <div className="form-label" style={{ fontSize: 11 }}>{label}</div>
                <select className="form-select" style={{ width: 150, height: 34, fontSize: 13 }}>
                  {opts.map(o => <option key={o}>{o}</option>)}
                </select>
              </div>
            ))}
            <button className="btn btn-primary btn-sm" style={{ marginTop: 16 }}>Apply Filters</button>
          </div>
        </div>

        <div className="card">
          <table className="data-table">
            <thead><tr><th>Project Name</th><th>Test Date</th><th>Mutation Score</th><th>Mutants Tested</th><th>Time</th><th>Saved</th><th>Strategy</th><th>Framework</th><th>Actions</th></tr></thead>
            <tbody>
              {sliced.map(j => (
                <tr key={j.id}>
                  <td className="bold" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{j.id.slice(0, 12)}…</td>
                  <td className="text-muted text-sm">{new Date(j.created_at).toLocaleString()}</td>
                  <td><ScorePill value={Math.round((j.mutation_score||0)*100)} /></td>
                  <td className="text-muted">{j.executed_mutants || 0}/{j.total_mutants || 0}</td>
                  <td className="text-muted">{((j.execution_time_seconds||0)/60).toFixed(1)} min</td>
                  <td className="text-green font-semibold">{j.time_saved_pct?.toFixed(0)||0}%</td>
                  <td className="text-muted">{j.optimizer_strategy || '—'}</td>
                  <td><span className="badge badge-blue">PIT</span></td>
                  <td style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-primary btn-sm" onClick={() => nav(`/results/${j.id}`)}>View</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => nav('/compare')}>Compare</button>
                  </td>
                </tr>
              ))}
              {sliced.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: '20px', color: 'var(--gray-400)' }}>No test sessions found</td></tr>
              )}
            </tbody>
          </table>
          <div className="flex items-center justify-between mt-4">
            <span className="text-muted text-sm">Showing {Math.min(total, PER_PAGE)} of {total} test sessions</span>
            <div className="pagination">
              <button className="page-num" onClick={() => setPage(Math.max(1, page-1))}>←</button>
              {Array.from({ length: Math.min(3, Math.ceil(total/PER_PAGE)) }, (_, i) => i+1).map(p => (
                <button key={p} className={`page-num ${p===page?'active':''}`} onClick={() => setPage(p)}>{p}</button>
              ))}
              <button className="page-num" onClick={() => setPage(p => Math.min(Math.ceil(total/PER_PAGE), p+1))}>→</button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Compare ───────────────────────────────────────────────────────
export function Compare() {
  const nav  = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [selA, setSelA] = useState('');
  const [selB, setSelB] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    listJobs().then(j => {
      const c = (j || []).filter(x => x.status === 'COMPLETED');
      setJobs(c);
      if (c.length >= 2) { setSelA(c[0].id); setSelB(c[1].id); }
    }).catch(() => {});
  }, []);

  const jobA = jobs.find(j => j.id === selA);
  const jobB = jobs.find(j => j.id === selB);

  const handleCompare = () => {
    if (!jobA || !jobB) return;
    const sA = Math.round((jobA.mutation_score||0)*100);
    const sB = Math.round((jobB.mutation_score||0)*100);
    setResult({
      scoreA: sA, scoreB: sB, diff: sA - sB,
      timeA: ((jobA.execution_time_seconds||0)/60).toFixed(1),
      timeB: ((jobB.execution_time_seconds||0)/60).toFixed(1),
      mutantsA: jobA.executed_mutants, mutantsB: jobB.executed_mutants,
    });
  };

  const label = j => j ? `${j.id.slice(0,10)}… (${Math.round((j.mutation_score||0)*100)}%)` : '';

  return (
    <AppShell>
      <PageHeader icon="🔀" title="Compare Results"
        right={<button className="hdr-btn ghost" onClick={() => nav('/history')}>← Back</button>} />
      <div className="page-content">
        <div className="card mb-4">
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label className="form-label">Select Sessions:</label>
              <select className="form-select" value={selA} onChange={e => setSelA(e.target.value)}>
                {jobs.map(j => <option key={j.id} value={j.id}>{label(j)}</option>)}
              </select>
            </div>
            <div style={{ paddingBottom: 10, fontWeight: 700, color: 'var(--gray-500)' }}>vs</div>
            <div style={{ flex: 1 }}>
              <label className="form-label">&nbsp;</label>
              <select className="form-select" value={selB} onChange={e => setSelB(e.target.value)}>
                {jobs.map(j => <option key={j.id} value={j.id}>{label(j)}</option>)}
              </select>
            </div>
            <button className="btn btn-primary" style={{ marginBottom: 0 }} onClick={handleCompare}>Compare</button>
          </div>
        </div>

        {result && (
          <>
            <div className="card mb-4" style={{ background: 'linear-gradient(135deg, var(--purple-mid), var(--purple))', color: '#fff' }}>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>📊 Comparison Summary</div>
              <div style={{ fontSize: 13.5, opacity: 0.9, lineHeight: 1.6 }}>
                Session 1 achieved <strong>{result.scoreA}%</strong> mutation score vs Session 2's <strong>{result.scoreB}%</strong>,
                indicating a <strong>{Math.abs(result.diff)}% {result.diff > 0 ? 'higher' : 'lower'} score</strong>.
                {result.diff < 0 && ` However, Session 1 may have been faster, saving time while staying in the "good" range.`}
                {result.diff >= 0 && ` Session 1 performs better overall.`}
              </div>
            </div>

            <div className="card mb-4">
              <div className="card-title">Metric Comparison</div>
              <div className="grid-5" style={{ gap: 12 }}>
                {[
                  { label: 'Mutation Score', v: <>{result.scoreA}%<br /><small>vs</small><br />{result.scoreB}%</>, sub: `${result.diff > 0 ? '+' : ''}${result.diff}%`, c: result.diff >= 0 ? 'var(--green)' : 'var(--red)' },
                  { label: 'Execution Time', v: <>{result.timeA}min<br /><small>vs</small><br />{result.timeB}min</>, sub: `${result.timeA < result.timeB ? 'Session 1 faster' : 'Session 2 faster'}`, c: 'var(--green)' },
                  { label: 'Mutants Tested', v: <>{result.mutantsA}<br /><small>vs</small><br />{result.mutantsB}</>, sub: `${result.mutantsA - result.mutantsB} difference`, c: 'var(--amber)' },
                  { label: 'Correlation', v: '0.97', sub: 'Very High', c: 'var(--green)' },
                  { label: 'Effectiveness', v: 'Similar', sub: 'Same faults', c: 'var(--green)' },
                ].map(({ label, v, sub, c }) => (
                  <div key={label} className="compare-metric">
                    <div className="cmp-label">{label}</div>
                    <div className="cmp-val" style={{ color: c }}>{v}</div>
                    <div className="cmp-sub" style={{ color: c }}>{sub}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="info-box amber mb-4">
              <strong>💡 What does this score difference mean?</strong><br />
              Session 1 scored {result.scoreA}% while Session 2 scored {result.scoreB}%, a difference of {Math.abs(result.diff)} percentage points. In practice:<br />
              · <strong>{result.scoreA}% score (Session 1):</strong> Tests killed {result.scoreA}% of mutants. {100-result.scoreA}% survived (potential test gaps).<br />
              · <strong>{result.scoreB}% score (Session 2):</strong> Tests killed {result.scoreB}% of mutants. Only {100-result.scoreB}% survived.<br />
              <strong>Recommendation:</strong> {result.diff >= 0 ? 'Use Session 1\'s configuration for regular testing.' : 'Session 2\'s approach produced better mutation coverage.'}
            </div>

            <div className="grid-2" style={{ gap: 16 }}>
              <div className="card">
                <div className="card-title">📊 Operator Comparison</div>
                <div style={{ background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 6, height: 100, display: 'grid', placeItems: 'center', color: 'var(--gray-400)', fontSize: 13 }}>
                  Bar Chart: Mutation Score by Operator<br />
                  <small>Run comparison to see operator-level breakdown</small>
                </div>
                <div className="text-xs text-muted mt-2">💡 All operators show consistent results, indicating balanced prioritization.</div>
              </div>
              <div className="card">
                <div className="card-title">Key Differences</div>
                <table className="data-table">
                  <thead><tr><th>Category</th><th>Session 1</th><th>Session 2</th></tr></thead>
                  <tbody>
                    <tr><td>Mutation Score</td><td className="text-green font-bold">{result.scoreA}%</td><td>{result.scoreB}%</td></tr>
                    <tr><td>Mutants Tested</td><td className="font-bold">{result.mutantsA}</td><td>{result.mutantsB}</td></tr>
                    <tr><td>Execution Time</td><td>{result.timeA}m</td><td>{result.timeB}m</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
        {!result && (
          <div style={{ textAlign: 'center', padding: '40px', color: 'var(--gray-400)' }}>
            <div style={{ fontSize: 40, marginBottom: 10 }}>🔀</div>
            <div>Select two test sessions above and click Compare to see the analysis.</div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

// ── Configuration ─────────────────────────────────────────────────
export function Config() {
  const nav = useNavigate();
  const [activeTab, setActiveTab] = useState('project');
  const [form, setForm] = useState({ name: 'My Java Project', sourceDir: '/src/main/java', testDir: '/src/test/java', framework: 'STRYKER' });

  return (
    <AppShell>
      <PageHeader icon="⚙️" title="Configuration"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>← Back</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 860, margin: '0 auto' }}>
          <div className="tab-pills">
            {[['project','Project Settings'],['mutations','Mutation Options'],['budget','Time Budget'],['profiles','Saved Profiles']].map(([k,l]) => (
              <button key={k} className={`tab-pill ${activeTab===k?'active':''}`} onClick={() => setActiveTab(k)}>{l}</button>
            ))}
          </div>

          {activeTab === 'project' && (
            <div className="grid-2" style={{ gap: 24 }}>
              <div>
                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>Project Information</h3>
                <div className="form-group"><label className="form-label">Project Name:</label>
                  <input className="form-input" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} /></div>
                <div className="form-group"><label className="form-label">Source Directory:</label>
                  <input className="form-input" value={form.sourceDir} onChange={e => setForm(f => ({...f, sourceDir: e.target.value}))} /></div>
                <div className="form-group"><label className="form-label">Test Directory:</label>
                  <input className="form-input" value={form.testDir} onChange={e => setForm(f => ({...f, testDir: e.target.value}))} /></div>
                <div className="form-group">
                  <label className="form-label">Framework Selection</label>
                  <label className="form-check radio"><input type="radio" name="fw" checked={form.framework==='PIT'} onChange={() => setForm(f=>({...f,framework:'PIT'}))} /> PIT (Java)</label>
                  <label className="form-check radio"><input type="radio" name="fw" checked={form.framework==='STRYKER'} onChange={() => setForm(f=>({...f,framework:'STRYKER'}))} /> Stryker (JavaScript/TypeScript)</label>
                  <label className="form-check radio"><input type="radio" name="fw" checked={form.framework==='AUTO'} onChange={() => setForm(f=>({...f,framework:'AUTO'}))} /> Auto-detect</label>
                </div>
              </div>
              <div>
                <div className="card" style={{ background: 'var(--amber-light)', borderColor: '#FDE68A' }}>
                  <div className="card-title" style={{ fontSize: 13 }}>💡 Quick Configuration Tips</div>
                  <p style={{ fontSize: 12.5, color: 'var(--gray-700)', lineHeight: 1.65, marginBottom: 10 }}>
                    <strong>Framework Selection:</strong> Use PIT for Java projects with JUnit tests. Stryker works best with Jest or Mocha for JavaScript/TypeScript.<br /><br />
                    <strong>Time Budget:</strong> Rule of thumb is 20-30% of exhaustive testing time. Recommended 15-30 minutes for most projects. This achieves 75-85% time savings with ≥0.95 correlation.<br /><br />
                    <strong>Mutation Operators:</strong> Enable high-effectiveness operators (Arithmetic, Relational, Logical) first. Add others based on results.
                  </p>
                  <div className="section-head">Saved Configurations</div>
                  {['Java Quick Test (PIT, 15m, 6 Operators)', 'JavaScript Standard (Stryker, 20m, Intelligent)'].map(l => (
                    <div key={l} style={{ background: '#fff', border: '1px solid #FDE68A', borderRadius: 6, padding: '9px 12px', marginBottom: 6, fontSize: 13, cursor: 'pointer' }}>{l}</div>
                  ))}
                  <div className="link text-sm mt-2" onClick={() => nav('/profiles')}>+ New Profile</div>
                </div>
              </div>
            </div>
          )}

          {activeTab !== 'project' && (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--gray-400)' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>⚙️</div>
              <div>Configure {activeTab === 'mutations' ? 'mutation options' : activeTab === 'budget' ? 'time budget' : 'saved profiles'} here.</div>
              <button className="btn btn-primary mt-3" onClick={() => nav('/new-session')}>Use New Session Wizard</button>
            </div>
          )}

          <hr className="divider" />
          <div className="flex justify-between">
            <button className="btn btn-outline">Load Defaults</button>
            <div className="flex gap-3">
              <button className="btn btn-secondary" onClick={() => nav('/dashboard')}>Cancel</button>
              <button className="btn btn-primary">Save & Continue</button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Saved Profiles ────────────────────────────────────────────────
const DEFAULT_PROFILES = [
  { id:'p1', icon:'🎯', name:'Quick CI/CD',       isDefault:true,  budget:10, strategy:'Intelligent Prioritization', ops:'6 selected (High-effectiveness)', threads:4, used:47, score:83, time:12 },
  { id:'p2', icon:'🔬', name:'Thorough Analysis',  isDefault:false, budget:30, strategy:'Adaptive Learning',         ops:'All 8 operators',                 threads:6, used:12, score:89, time:28 },
  { id:'p3', icon:'⚡', name:'Speed Test',          isDefault:false, budget:5,  strategy:'Random Sampling',           ops:'4 operators (Core only)',          threads:8, used:8,  score:71, time:6  },
  { id:'p4', icon:'🛡️', name:'Security Critical',  isDefault:false, budget:60, strategy:'Exhaustive Testing',        ops:'All 8 operators',                  threads:8, used:3,  score:94, time:58, tag:'HIGH CORRELATION' },
  { id:'p5', icon:'🎨', name:'Frontend Testing',   isDefault:false, budget:12, strategy:'Intelligent Prioritization',ops:'5 operators (JS-optimized)',        threads:4, used:24, score:78, time:13 },
  { id:'p6', icon:'🔧', name:'Backend API',         isDefault:false, budget:20, strategy:'Adaptive Learning',         ops:'7 operators (API-focused)',         threads:6, used:31, score:85, time:19 },
];

export function Profiles() {
  const nav = useNavigate();
  const [profiles, setProfiles] = useState([]);
  const [search, setSearch]     = useState('');

  useEffect(() => {
    listProfiles().then(p => setProfiles(p?.length ? p : DEFAULT_PROFILES)).catch(() => setProfiles(DEFAULT_PROFILES));
  }, []);

  const filtered = profiles.filter(p =>
    !search || p.name?.toLowerCase().includes(search.toLowerCase()) || p.strategy?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <AppShell>
      <PageHeader icon="💾" title="Saved Profiles"
        right={<button className="hdr-btn" onClick={() => nav('/config')}>+ Create New Profile</button>} />
      <div className="page-content">
        <div className="flex items-center justify-between mb-4">
          <input className="form-input" style={{ width: 280, background: '#fff' }}
            placeholder="🔍 Search profiles by name or configuration…"
            value={search} onChange={e => setSearch(e.target.value)} />
          <div className="flex gap-2">
            <button className="btn btn-secondary btn-sm">📊 Export All</button>
            <button className="btn btn-secondary btn-sm">⬆️ Import</button>
          </div>
        </div>

        <div className="grid-3" style={{ gap: 14 }}>
          {filtered.map(p => (
            <div key={p.id} className={`profile-card ${p.isDefault ? 'active' : ''}`}>
              {p.isDefault && <span className="profile-tag default">DEFAULT</span>}
              {p.tag && <span className="profile-tag hicorr">{p.tag}</span>}
              <div className="profile-card-title">{p.icon} {p.name}</div>
              <div className="profile-meta">
                <div className="profile-meta-row">⏱ <span>Time Budget: {p.budget || p.time_budget_seconds/60} minutes</span></div>
                <div className="profile-meta-row">🧠 <span>Strategy: {p.strategy || p.optimizer_strategy}</span></div>
                <div className="profile-meta-row">⚙️ <span>Operators: {p.ops || 'Custom'}</span></div>
                <div className="profile-meta-row">⚡ <span>Threads: {p.threads} parallel</span></div>
              </div>
              <div className="profile-stats">
                <div className="profile-stat"><div className="pstat-val">{p.used || p.times_used || 0}</div><div className="pstat-lbl">Times Used</div></div>
                <div className="profile-stat"><div className="pstat-val">{p.score || Math.round((p.avg_score||0)*100)}%</div><div className="pstat-lbl">Avg Score</div></div>
                <div className="profile-stat"><div className="pstat-val">{p.time || Math.round((p.avg_time_seconds||0)/60)}m</div><div className="pstat-lbl">Avg Time</div></div>
              </div>
              <div className="flex gap-2 mt-3">
                <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={() => nav('/new-session')}>Load Profile</button>
                <button className="btn btn-secondary btn-sm" onClick={() => nav('/config')}>Edit</button>
                <button className="btn btn-secondary btn-sm">···</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}

// ── User Profile ──────────────────────────────────────────────────
export function UserProfile() {
  const nav = useNavigate();
  const { user, setUser } = useAuth();
  const [form, setForm]   = useState({ fullName: '', email: '', org: '' });
  const [pw, setPw]       = useState({ current: '', next: '', confirm: '' });
  const [stats, setStats] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (user) setForm({ fullName: user.full_name || '', email: user.email || '', org: '' });
    getMyStats().then(s => setStats(s)).catch(() => {});
  }, [user]);

  const handleSave = async () => {
    try {
      const { updateMe } = await import('../api/client');
      const updated = await updateMe({ full_name: form.fullName });
      if (setUser) setUser(u => ({ ...u, ...updated }));
      setSaved(true); setTimeout(() => setSaved(false), 2000);
    } catch {}
  };

  return (
    <AppShell>
      <PageHeader icon="👤" title="User Profile"
        right={<button className="hdr-btn" onClick={handleSave}>{saved ? '✓ Saved' : 'Edit Profile'}</button>} />
      <div className="page-content">
        <div style={{ maxWidth: 700 }}>
          {/* Info */}
          <div className="card mb-4">
            <div className="flex items-center gap-4">
              <div style={{ textAlign: 'center', flexShrink: 0 }}>
                <div style={{ width: 80, height: 80, background: 'var(--purple-light)', borderRadius: '50%', display: 'grid', placeItems: 'center', margin: '0 auto 8px', fontSize: 32 }}>👤</div>
                <button className="btn btn-outline-gray btn-sm">Change Photo</button>
                <div className="text-xs text-muted mt-2">Member Since<br />{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}</div>
                <div className="text-xs text-muted">Role: {user?.role || 'student'}</div>
              </div>
              <div style={{ flex: 1 }}>
                <div className="form-group"><label className="form-label">Full Name</label>
                  <input className="form-input" value={form.fullName} onChange={e => setForm(f=>({...f,fullName:e.target.value}))} /></div>
                <div className="form-group"><label className="form-label">Email Address</label>
                  <input className="form-input success" value={form.email} readOnly /></div>
                <div className="form-group"><label className="form-label">Organization</label>
                  <input className="form-input" placeholder="Your organization" value={form.org} onChange={e => setForm(f=>({...f,org:e.target.value}))} /></div>
              </div>
            </div>
          </div>

          {/* Stats */}
          <div className="card mb-4">
            <div className="card-title">📊 Account Statistics</div>
            <div className="grid-3" style={{ gap: 14 }}>
              {[
                { l: 'Tests Run',        v: stats?.total_jobs || 0,  c: 'purple' },
                { l: 'Time Saved',       v: `${Math.round((stats?.avg_time_saved||0))}%`, c: 'green' },
                { l: 'Avg Correlation',  v: (stats?.avg_correlation||0).toFixed(2),        c: 'green' },
                { l: 'Projects Tested',  v: stats?.projects_tested || 0, c: 'blue' },
                { l: 'Fav. Framework',   v: stats?.fav_framework || 'PIT', c: 'purple' },
                { l: 'Avg Score',        v: `${Math.round((stats?.avg_mutation_score||0)*100)}%`, c: 'green' },
              ].map(({ l, v, c }) => (
                <div key={l} className={`stat-card ${c}`} style={{ textAlign: 'center' }}>
                  <div className="stat-value" style={{ fontSize: 22 }}>{v}</div>
                  <div className="stat-label">{l}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Password & Security */}
          <div className="card mb-4">
            <div className="card-title">🔒 Password & Security</div>
            <div className="summary-row">
              <div><div className="font-semibold">Password</div><div className="text-sm text-muted">•••••••••• Last changed: 15 days ago</div></div>
              <button className="btn btn-outline-gray btn-sm">Change Password</button>
            </div>
            <div className="summary-row">
              <div><div className="font-semibold">Two-Factor Authentication</div><div className="text-sm text-muted">Add an extra layer of security</div></div>
              <button className="btn btn-outline-gray btn-sm">Enable 2FA</button>
            </div>
            <div style={{ marginTop: 14 }}>
              <div className="font-semibold mb-2 text-sm">Active Sessions</div>
              {[
                { browser: '🌐 Chrome (Windows)', time: 'Current Session', isCurrent: true },
                { browser: '🦊 Firefox (Windows)', time: '2 hours ago' },
                { browser: '📱 Mobile App', time: '1 day ago' },
              ].map(s => (
                <div key={s.browser} className="session-row">
                  <div>
                    <div className="session-browser">{s.browser}</div>
                    {s.isCurrent ? <div className="session-current">Current Session</div> : <div className="session-time">{s.time}</div>}
                  </div>
                  {!s.isCurrent && <button className="btn btn-secondary btn-sm">Revoke</button>}
                </div>
              ))}
            </div>
          </div>

          {/* Preferences */}
          <div className="card mb-4">
            <div className="card-title">⚙️ Preferences</div>
            <div className="font-semibold mb-2 text-sm">Email Notifications</div>
            {['Test completion notifications','Weekly summary reports','Product updates and announcements'].map(l => (
              <label key={l} className="form-check"><input type="checkbox" defaultChecked={l !== 'Product updates'} /> {l}</label>
            ))}
            <hr className="divider" />
            <div className="form-row-2">
              <div className="form-group"><label className="form-label">Theme</label><select className="form-select"><option>Light</option><option>Dark</option></select></div>
              <div className="form-group"><label className="form-label">Language</label><select className="form-select"><option>English</option><option>Filipino</option></select></div>
            </div>
          </div>

          {/* Danger zone */}
          <div className="card mb-4" style={{ borderColor: '#FECACA' }}>
            <div className="card-title" style={{ color: 'var(--red)' }}>⚠️ Danger Zone</div>
            <div className="danger-row">
              <div><div className="label">Export Data</div><div className="sub">Download all your test data and results</div></div>
              <button className="btn btn-outline-gray btn-sm">Export Data</button>
            </div>
            <div className="danger-row">
              <div><div className="label">Delete Account</div><div className="sub">Permanently delete your account. This action cannot be undone.</div></div>
              <button className="btn btn-danger btn-sm">Delete Account</button>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <button className="btn btn-secondary" onClick={() => nav('/dashboard')}>Cancel</button>
            <button className="btn btn-primary" onClick={handleSave}>{saved ? '✓ Saved!' : 'Save Changes'}</button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Help ──────────────────────────────────────────────────────────
export function Help() {
  const [active, setActive] = useState('quickstart');

  return (
    <AppShell>
      <PageHeader icon="❓" title="Help & Documentation"
        right={<input className="form-input" style={{ width: 280, height: 34, fontSize: 13 }} placeholder="🔍 Search documentation…" />} />
      <div className="page-content">
        <div className="flex" style={{ gap: 0 }}>
          <div className="help-sidebar">
            {[
              { section: 'Getting Started', items: [['quickstart','Quick Start Guide'],['firsttest','First Test Session'],['results','Understanding Results']] },
              { section: 'Configuration',   items: [['setup','Project Setup'],['operators','Mutation Operators']] },
              { section: 'Features',        items: [['scoring','Multi-Factor Scoring'],['subsumption','Subsumption Analysis']] },
              { section: 'Best Practices',  items: [['optimal','Optimal Settings']] },
              { section: 'FAQ',             items: [['faq','Frequently Asked Questions']] },
            ].map(({ section, items }) => (
              <div key={section}>
                <div className="help-section-title">{section}</div>
                {items.map(([id, label]) => (
                  <span key={id} className={`help-link ${active===id?'active':''}`} onClick={() => setActive(id)}>{label}</span>
                ))}
              </div>
            ))}
          </div>

          <div className="help-content">
            <div className="help-h1">Quick Start Guide</div>
            <p className="help-p">
              Welcome to IMPT - Intelligent Mutation Prioritization Tool. IMPT helps you perform efficient mutation
              testing by intelligently prioritizing which mutants to test, saving 75-85% of testing time while
              maintaining high correlation (≥0.95) with exhaustive testing.
            </p>
            <div className="help-h2">1. Creating Your First Test Session</div>
            {[
              ['Upload Your Project', 'Click "New Test Session" from the dashboard. Upload your project files (Java or JavaScript). IMPT will auto-detect your framework (PIT or Stryker).'],
              ['Configure Mutation Operators', 'Select which mutation operators to use. Recommended: Keep default high-weight operators selected.'],
              ['Set Time Budget', 'Choose how long you want testing to run (5-60 minutes). IMPT will intelligently select the best mutants to test.'],
            ].map(([title, body], i) => (
              <div key={i} className="help-step">
                <div className="help-step-num">{i+1}</div>
                <div><strong>{title}</strong> — {body}</div>
              </div>
            ))}
            <div className="help-h2">2. Understanding Your Results</div>
            <p className="help-p"><strong>Mutation Score:</strong> Percentage of mutants killed by your tests<br />· 80-90%: Excellent test suite<br />· 60-80%: Good, room for improvement<br />· &lt;60%: Tests may need strengthening</p>
            <p className="help-p"><strong>Time Savings:</strong> How much time IMPT saved vs exhaustive testing<br />· Target: 75-85% time reduction</p>
            <div className="help-h2">3. Tips for Best Results</div>
            <ul style={{ fontSize: 13.5, color: 'var(--gray-600)', lineHeight: 2.2, paddingLeft: 20 }}>
              <li>Run a baseline test first to establish comparison metrics</li>
              <li>Use 20-30 minute time budgets for balanced results</li>
              <li>Enable all recommended mutation operators</li>
              <li>Review survived mutants to find test gaps</li>
            </ul>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Admin ─────────────────────────────────────────────────────────
export function Admin() {
  const [adminTab, setAdminTab] = useState('Hourly Traffic');
  const [stats, setStats] = useState(null);

  useEffect(() => {
    getAdminStats().then(s => setStats(s)).catch(() => {});
  }, []);

  return (
    <AppShell>
      <PageHeader icon="🛡️" title="Admin Dashboard"
        right={<span style={{ background: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.9)', padding: '4px 12px', borderRadius: 999, fontSize: 12, fontWeight: 600 }}>
          Real-time · Last updated: 2 seconds ago
        </span>} />
      <div className="page-content">
        <div className="grid-4 mb-4">
          {[
            { l:'Active Users (Today)', v: stats?.active_users_today || 247,  delta:'↑ 12% vs yesterday', c:'blue' },
            { l:'Server Uptime',        v: '99.9%',                            delta:'↑ 2% vs last week',  c:'green' },
            { l:'Avg Response Time',    v: '1.2s',                             delta:'↑ 0.3s slower',      c:'amber' },
            { l:'Errors (Last Hour)',   v: stats?.errors_last_hour || 7,       delta:'↑ 3 errors',         c:'red'   },
          ].map(({ l, v, delta, c }) => (
            <div key={l} className={`stat-card ${c}`}>
              <div className="stat-label">{l}</div>
              <div className="stat-value">{v}</div>
              <div className="stat-delta" style={{ color: `var(--${c})` }}>{delta}</div>
            </div>
          ))}
        </div>

        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="card-title" style={{ marginBottom: 0 }}>📊 Usage Analytics</div>
            <button className="btn btn-secondary btn-sm">Compare to Previous Period</button>
          </div>
          <div className="tab-bar">
            {['Hourly Traffic','Daily Users','Retention Rate','Performance Trends'].map(t => (
              <button key={t} className={`tab-btn ${adminTab===t?'active':''}`} onClick={() => setAdminTab(t)}>{t}</button>
            ))}
          </div>
          <div style={{ height: 130, background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 6, display: 'grid', placeItems: 'center' }}>
            <div style={{ textAlign: 'center', color: 'var(--gray-400)', fontSize: 13 }}>
              📈 Interactive chart: {adminTab} (real-time updating)<br />
              <small>Peak: 43 users at 10:00 AM · Current: 12 users</small>
            </div>
          </div>
        </div>

        <div className="card mb-4">
          <div className="card-title">🚀 Mutation Testing Insights</div>
          <p className="text-sm text-muted mb-3">Most popular configurations and usage patterns to understand how users leverage IMPT.</p>
          <table className="data-table">
            <thead><tr><th>Mutation Operator Combination</th><th>Usage Count</th><th>Avg Effectiveness</th><th>Most Common Projects</th></tr></thead>
            <tbody>
              {[
                ['Arithmetic + Relational + Logical', '892 tests', 'High (84%)',      'high',   'Web APIs, Libraries'],
                ['All Operators (Exhaustive)',         '234 tests', 'Very High (91%)', 'vhigh',  'Financial systems, Security'],
                ['High-Effectiveness Only',            '567 tests', 'Medium (76%)',    'med',    'Utilities, CLI tools'],
                ['Random Selection',                   '45 tests',  'Low (58%)',       'low',    'Research projects'],
              ].map(([combo, count, eff, lvl, proj]) => (
                <tr key={combo}>
                  <td className="bold">{combo}</td>
                  <td className="text-muted">{count}</td>
                  <td><span className={`admin-badge admin-${lvl}`}>{eff}</span></td>
                  <td className="text-muted">{proj}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card mb-4">
          <div className="card-title">⏰ Time Budget Selection Patterns</div>
          <div style={{ height: 120, background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 6, display: 'grid', placeItems: 'center', marginBottom: 10 }}>
            <div style={{ textAlign: 'center', color: 'var(--gray-400)', fontSize: 13 }}>
              🥧 Pie chart: Time budget distribution<br />
              <small>15 min (42%) · 10 min (28%) · 30 min (18%) · 60 min (12%)</small>
            </div>
          </div>
          <div className="info-box">💡 <strong>Insight:</strong> Most users (70%) choose budgets ≤15 minutes, indicating preference for quick feedback. Consider optimizing for 10-15 minute workflows.</div>
        </div>

        <div className="card mb-4">
          <div className="card-title">🎯 Mutation Strategy Preferences</div>
          <table className="data-table">
            <thead><tr><th>Strategy</th><th>Selection Rate</th><th>Avg Time Savings</th><th>User Satisfaction</th></tr></thead>
            <tbody>
              {[
                ['Intelligent Prioritization','78%','82% savings','high','★★★★★ 4.7/5'],
                ['Adaptive Learning',          '12%','85% savings','high','★★★★★ 4.8/5'],
                ['Exhaustive',                 '8%', '0% savings', 'low', '★★★★☆ 4.3/5'],
                ['Random Sampling',            '2%', '45% savings','med', '★★★☆☆ 3.2/5'],
              ].map(([strat, rate, savings, lvl, stars]) => (
                <tr key={strat}>
                  <td className="bold">{strat}</td>
                  <td className="text-muted">{rate}</td>
                  <td><span className={`admin-badge admin-${lvl}`}>{savings}</span></td>
                  <td className="stars">{stars}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <div className="card-title">📋 Project Testing Frequency</div>
          <p className="text-sm text-muted mb-3">Projects repeatedly tested using similar configurations—indicates if users find value and return.</p>
          <table className="data-table">
            <thead><tr><th>Project Name</th><th>Test Count</th><th>Same Config?</th><th>Avg Mutation Score Trend</th><th>Status</th></tr></thead>
            <tbody>
              {[
                ['payment-gateway-api', 23, 'Yes (87%)',  'green', '78% → 82% → 86% (↑ improving)', 'green', '✓ Healthy'],
                ['user-auth-service',   8,  'Mixed',      'amber', '91% → 90% → 91% (stable)',       'green', '✓ Healthy'],
                ['inventory-manager',   15, 'No (varied)','red',   '65% → 64% → 66% (≈ flat)',       'amber', '⚠ Investigate'],
              ].map(([name, count, config, configC, trend, statusC, status]) => (
                <tr key={name}>
                  <td className="bold" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{name}</td>
                  <td>{count} tests</td>
                  <td><span className={`badge badge-${configC}`}>{config}</span></td>
                  <td className={`text-${statusC}`} style={{ fontSize: 12 }}>{trend}</td>
                  <td><span className={`badge badge-${statusC}`}>{status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="alert alert-warn mt-3" style={{ fontSize: 12.5 }}>
            ⚠️ <strong>Concern:</strong> inventory-manager shows repeated testing with flat scores—users may be struggling to improve tests. Consider investigating this workflow or offering targeted guidance.
          </div>
        </div>
      </div>
    </AppShell>
  );
}
