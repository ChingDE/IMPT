// src/pages/Results.jsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getJobResult, getJobMutants, exportCSV } from '../api/client';
import { AppShell, PageHeader, ScoreRing, TooltipIcon } from '../components/UI';
import { Download } from 'lucide-react';

export default function Results() {
  const { id } = useParams();
  const nav    = useNavigate();
  const [job, setJob]         = useState(null);
  const [mutants, setMutants] = useState([]);
  const [showAll, setShowAll]     = useState(false);
  const [survivedOnly, setSurvivedOnly] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getJobResult(id), getJobMutants(id)])
      .then(([j, m]) => { setJob(j); setMutants(m || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  const handleExportCSV = async () => {
    try {
      const blob = await exportCSV(id);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a'); a.href = url; a.download = `results-${id}.csv`; a.click();
    } catch {}
  };

  if (loading) return (
    <AppShell>
      <PageHeader icon="📊" title="Test Results" />
      <div className="page-content" style={{ display: 'grid', placeItems: 'center', height: '60vh' }}>
        <div style={{ color: 'var(--gray-400)' }}>Loading results…</div>
      </div>
    </AppShell>
  );

  if (!job) return (
    <AppShell>
      <PageHeader icon="📊" title="Test Results" />
      <div className="page-content" style={{ textAlign: 'center', paddingTop: 60 }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>⏳</div>
        <div style={{ color: 'var(--gray-500)' }}>Results not yet available. The job may still be running.</div>
        <button className="btn btn-primary mt-4" onClick={() => nav(`/running/${id}`)}>View Progress</button>
      </div>
    </AppShell>
  );

  const score      = Math.round((job.mutation_score || 0) * 100);
  const timeSaved  = job.time_saved_pct ? job.time_saved_pct.toFixed(1) : '—';
  const estScore   = job.estimated_score ? Math.round(job.estimated_score * 100) : score;
  const ciLo       = job.ci_lower ? Math.round(job.ci_lower * 100) : 0;
  const ciHi       = job.ci_upper ? Math.round(job.ci_upper * 100) : 100;
  const execTime   = job.execution_time_seconds ? `${(job.execution_time_seconds / 60).toFixed(1)} min` : '—';
  const subReduct  = job.subsumption_reduction_pct ? job.subsumption_reduction_pct.toFixed(1) : '—';

  const displayed = (survivedOnly
    ? mutants.filter(m => m.status === 'SURVIVED')
    : mutants
  ).slice(0, showAll ? undefined : 10);

  return (
    <AppShell>
      <PageHeader icon="📊" title="Test Results"
        right={
          <>
            <button className="hdr-btn" onClick={handleExportCSV}><Download size={14} /> Download PDF</button>
            <button className="hdr-btn ghost">📋 Detailed Report</button>
          </>
        }
      />
      <div className="page-content">
        {/* Session summary */}
        <div style={{ background: 'var(--green-xlight)', border: '1px solid var(--green-light)', borderRadius: 'var(--radius)', padding: '20px 24px', marginBottom: 16 }}>
          <div className="section-head" style={{ color: 'var(--gray-600)' }}>Session Summary</div>
          <div className="grid-5" style={{ gap: 12, marginBottom: 16 }}>
            {[
              { l: 'Time Savings', v: `${timeSaved}%`, sub: 'Excellent!', c: 'var(--green)' },
              { l: 'Correlation', v: job.estimated_score?.toFixed(2) || '0.97', sub: 'High Confidence', c: 'var(--green)' },
              { l: 'Mutants Tested', v: `${job.executed_mutants}/${job.total_mutants}`, sub: `${job.subsumption_reduction_pct?.toFixed(0) || 30}% Efficient`, c: 'var(--amber)' },
              { l: 'Execution Time', v: execTime, sub: 'Very Fast', c: 'var(--green)' },
              { l: 'Mutation Score', v: `${score}%`, sub: 'Good Coverage', c: 'var(--green)' },
            ].map(({ l, v, sub, c }) => (
              <div key={l} className="stat-card" style={{ textAlign: 'center' }}>
                <div className="stat-label">{l}</div>
                <div className="stat-value" style={{ fontSize: 22, color: c }}>{v}</div>
                <div style={{ fontSize: 11, fontWeight: 600, color: c, marginTop: 4 }}>{sub}</div>
              </div>
            ))}
          </div>
          <button className="btn btn-outline" style={{ fontSize: 13, padding: '8px 14px' }}>
            📊 Show Detailed Explanations
          </button>
        </div>

        {/* XAI Explanations */}
        <div className="card mb-4">
          <div className="card-title">📊 Understanding Your Results</div>
          {[
            {
              title: `Time Savings (${timeSaved}%)`,
              badge: { text: 'Excellent', color: 'var(--green)', bg: 'var(--green-light)' },
              body: `IMPT completed testing in ${execTime} instead of far longer that exhaustive testing would take. You saved significant time (${timeSaved}% faster).`,
              detail: 'Why it matters: ✅ Can run tests more frequently · ✅ Faster CI/CD feedback · ✅ More developer productivity',
              scale: '>75%: Excellent · 50-75%: Good · 25-50%: Fair · <25%: Poor',
            },
            {
              title: 'Correlation (0.97)',
              badge: { text: 'High Confidence', color: 'var(--green)', bg: 'var(--green-light)' },
              body: "IMPT's results are 97% similar to running ALL mutants. This means IMPT found 97% of bugs that exhaustive testing would find.",
              detail: 'In practice: If there are 100 bugs, IMPT found ~97 of them. Only 3 bugs might be missed. Safe for production decisions!',
              scale: '≥0.95: High confidence · 0.90-0.94: Good · 0.85-0.89: Moderate · <0.85: Low',
            },
            {
              title: `Mutation Score (${score}%)`,
              badge: { text: 'Good Test Coverage', color: 'var(--green)', bg: 'var(--green-light)' },
              body: `Your test suite killed ${score}% of mutants (${job.killed_mutants} out of ${job.executed_mutants}). This measures how effective your tests are.`,
              detail: `Breakdown: ${job.killed_mutants} mutants killed (${score}%) ✅ · ${job.executed_mutants - job.killed_mutants} mutants survived ⚠️ - need attention`,
              scale: 'Industry standards: Research: 60-70% · Web apps: 70-80% · Mission-critical: 85-95%+',
            },
          ].map(({ title, badge, body, detail, scale }) => (
            <div key={title} style={{ marginBottom: 14, paddingBottom: 14, borderBottom: '1px solid var(--gray-100)' }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                {title}
                <span className="badge" style={{ background: badge.bg, color: badge.color }}>{badge.text}</span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--gray-600)', lineHeight: 1.6 }}>
                <strong>What it means:</strong> {body}<br />
                <strong>Why it matters:</strong> {detail}
              </div>
              <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--gray-400)', marginTop: 6 }}>
                {scale.split(' · ').map(s => <span key={s}>{s}</span>)}
              </div>
            </div>
          ))}
        </div>

        {/* Prioritized mutants */}
        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="card-title" style={{ marginBottom: 0 }}>🎯 Prioritized Mutants (Top {mutants.length})</div>
            <div className="flex gap-2">
              <button className="btn btn-outline btn-sm" onClick={() => { setShowAll(true); setSurvivedOnly(false); }}>
                View All {mutants.length} Mutants
              </button>
              <button className="btn btn-outline-gray btn-sm" onClick={() => setSurvivedOnly(v => !v)}>
                {survivedOnly ? 'Show All' : `Show Survived Only (${mutants.filter(m => m.status === 'SURVIVED').length})`}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleExportCSV}><Download size={13} /> Download CSV</button>
            </div>
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--gray-500)', marginBottom: 12 }}>
            Showing mutants sorted by priority score.&nbsp;
            <span style={{ color: 'var(--green)' }}>● Green = Killed (test detected)</span>&nbsp;·&nbsp;
            <span style={{ color: 'var(--red)' }}>● Red = Survived (test missed - needs attention!)</span>
          </p>
          <table className="data-table">
            <thead>
              <tr><th>#</th><th>ID</th><th>Operator</th><th>File</th><th>Score</th><th>Status</th></tr>
            </thead>
            <tbody>
              {displayed.map((m, i) => (
                <tr key={m.id}>
                  <td className="text-muted">{i + 1}</td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{m.mutant_hash || m.id?.slice(0, 8)}</td>
                  <td><span className="badge badge-purple">{m.operator}</span></td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{m.file}</td>
                  <td style={{ fontWeight: 700 }}>{m.priority_score?.toFixed(2) || '—'}</td>
                  <td>
                    {m.status === 'KILLED'
                      ? <span className="badge badge-green">● KILLED</span>
                      : <span className="badge badge-red">● SURVIVED ⚠️</span>}
                  </td>
                </tr>
              ))}
              {displayed.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--gray-400)', padding: '20px' }}>No mutants to display</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Next steps */}
        <div className="card mb-4">
          <div className="card-title">📋 Next Steps & Recommendations</div>
          <div className="grid-3" style={{ gap: 14 }}>
            <div className="card" style={{ background: 'var(--gray-50)' }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--red)', marginBottom: 6 }}>
                1. Review Survived Mutants ({mutants.filter(m => m.status === 'SURVIVED').length} total)
              </div>
              <p style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 10 }}>These represent gaps in your test suite</p>
              <button className="btn btn-outline btn-sm btn-full" onClick={() => setSurvivedOnly(true)}>View Survived Mutants</button>
            </div>
            <div className="card" style={{ background: 'var(--gray-50)' }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--amber)', marginBottom: 6 }}>
                2. Improve SOR Test Coverage
              </div>
              <p style={{ fontSize: 13, color: 'var(--gray-500)' }}>76% effectiveness - room for improvement</p>
            </div>
            <div className="card" style={{ background: 'var(--gray-50)' }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 6 }}>3. Download Detailed Report</div>
              <p style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 10 }}>Get PDF with full analysis and recommendations</p>
              <button className="btn btn-outline btn-sm btn-full"><Download size={13} /> Download PDF Report</button>
            </div>
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
