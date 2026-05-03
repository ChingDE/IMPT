// src/pages/NewSession.jsx
import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createProject, uploadProject, submitJob } from '../api/client';
import { AppShell, WizardHeader, Alert, InfoBox, TooltipIcon } from '../components/UI';

const OPERATORS = [
  { code: 'AOR', name: 'Arithmetic Operator Replacement', eff: 92, lvl: 'High', desc: 'Replaces arithmetic operators (+, -, *, /). Example: a + b → a - b' },
  { code: 'ROR', name: 'Relational Operator Replacement', eff: 88, lvl: 'High', desc: 'Changes comparison operators (<, >, ==, !=). Example: x < 10 → x <= 10' },
  { code: 'COR', name: 'Conditional Operator Replacement', eff: 85, lvl: 'High', desc: 'Alter boolean conditions. Example: if (a) → if (!a)' },
  { code: 'SOR', name: 'Shift Operator Replacement', eff: 76, lvl: 'Moderate', desc: 'Replaces bitwise shift operators. Example: x << 2 → x >> 2' },
  { code: 'LCR', name: 'Logical Connector Replacement', eff: 71, lvl: 'Moderate', desc: 'Replace logical connectors. Example: && → ||' },
  { code: 'UOI', name: 'Unary Operator Insertion', eff: 85, lvl: 'High', desc: 'Add or remove unary operators. Example: x → -x' },
  { code: 'SDL', name: 'Statement Deletion', eff: 75, lvl: 'Moderate', desc: 'Remove a statement entirely.' },
  { code: 'CRP', name: 'Constant Replacement', eff: 65, lvl: 'Moderate', desc: 'Replace constants with different values.' },
];

const STRATEGIES = [
  { value: 'AUTO',   label: 'Intelligent Prioritization (Recommended)', desc: 'Uses multi-factor scoring to rank mutants by likelihood of finding test gaps. Achieves 75-85% time reduction with ≥0.95 correlation.' },
  { value: 'GREEDY', label: 'Adaptive Learning', desc: 'Adapts based on historical data. Best for repeated testing of same project.' },
  { value: 'DP',     label: 'Exhaustive Testing', desc: 'Tests all mutants. Highest accuracy, most time required.' },
];

export default function NewSession() {
  const nav = useNavigate();
  const fileRef = useRef();
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Step 1 state
  const [projectName, setProjectName] = useState('');
  const [framework, setFramework]     = useState('PIT');
  const [file, setFile]               = useState(null);
  const [project, setProject]         = useState(null);
  const [uploadState, setUploadState] = useState('idle'); // idle | success | error
  const [dragOver, setDragOver]       = useState(false);

  // Step 2 state
  const [strategy, setStrategy]       = useState('AUTO');
  const [threads, setThreads]         = useState(4);
  const [selectedOps, setSelectedOps] = useState(new Set(['AOR', 'ROR', 'COR', 'SOR']));

  // Step 3 state
  const [budget, setBudget]           = useState(20);
  const [outputOpts, setOutputOpts]   = useState({ html: true, csv: true, email: false, baseline: true });

  const toggleOp = code => setSelectedOps(s => {
    const n = new Set(s);
    n.has(code) ? n.delete(code) : n.add(code);
    return n;
  });

  const budgetPct = ((budget - 5) / 55) * 100;
  const estMutants = Math.round(selectedOps.size * 80 * (budget / 20));
  const toExecute  = Math.round(estMutants * 0.3);
  const timeSaved  = Math.round((1 - budget / (budget + 40)) * 100);

  // ── Step 1: Upload ────────────────────────────────────────────
  const handleFile = async (f) => {
    if (!f) return;
    setFile(f);
    if (!projectName) {
      setProjectName(f.name.replace(/\.(zip|tar\.gz|tgz)$/, ''));
    }
  };

  const handleDrop = e => {
    e.preventDefault(); setDragOver(false);
    handleFile(e.dataTransfer.files[0]);
  };

  const handleStep1Next = async () => {
    if (!projectName.trim()) { setError('Please enter a project name.'); return; }
    setError(''); setLoading(true);
    try {
      const p = await createProject({ name: projectName, framework, loc: 0, test_count: 0 });
      if (file) {
        const fd = new FormData(); fd.append('file', file);
        await uploadProject(p.id, fd);
        setUploadState('success');
      }
      setProject(p);
      setStep(2);
    } catch (err) {
      setUploadState('error');
      setError(err.response?.data?.detail || 'Upload failed. Check the archive contains pom.xml (Java) or package.json (JS).');
    } finally { setLoading(false); }
  };

  // ── Step 3: Submit ────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!project) return;
    setLoading(true); setError('');
    try {
      const job = await submitJob({
        project_id: project.id,
        time_budget_seconds: budget * 60,
        optimizer_strategy: strategy,
        jaccard_threshold: 0.90,
      });
      nav(`/running/${job.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit job.');
      setLoading(false);
    }
  };

  // ── Step 1 UI ─────────────────────────────────────────────────
  if (step === 1) return (
    <AppShell>
      <WizardHeader title="New Test Session" step={1} totalSteps={3} stepLabel="Upload Project"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 780, margin: '0 auto' }}>
          <h2 style={{ fontSize: 17, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
            Upload Your Project <TooltipIcon text="Upload a .zip or .tar.gz archive of your project" />
          </h2>

          {error && <Alert type="error" style={{ marginTop: 10 }}>{error}</Alert>}

          <InfoBox style={{ marginTop: 12 }}>
            <strong>💡 What we need:</strong> Your project should include source code, test files, and build
            configuration (pom.xml for Java or package.json for JavaScript).
            We'll automatically detect your project type and existing test suite.
          </InfoBox>

          {/* Drop zone */}
          <div
            className={`drop-zone ${dragOver ? 'active' : ''} ${uploadState === 'error' ? 'error' : ''} ${uploadState === 'success' ? 'success' : ''}`}
            style={{ margin: '16px 0' }}
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <div className="drop-icon">{uploadState === 'success' ? '✅' : uploadState === 'error' ? '⚠️' : '☁️'}</div>
            <div className="drop-text">
              {file ? file.name : 'Drag and drop project folder here'}
            </div>
            <div className="drop-sub" style={{ margin: '6px 0' }}>{file ? '' : 'or'}</div>
            {!file && <button className="btn btn-primary" style={{ pointerEvents: 'none' }}>📁 Browse Project Files</button>}
            <input ref={fileRef} type="file" accept=".zip,.tar.gz,.tgz" style={{ display: 'none' }}
              onChange={e => handleFile(e.target.files[0])} />
          </div>

          {uploadState === 'success' && (
            <Alert type="success">
              <strong>✓ Project Loaded Successfully</strong><br />
              {project?.name} · {framework} · {project?.loc?.toLocaleString() || 0} LOC detected
            </Alert>
          )}

          <div className="grid-2" style={{ gap: 24, marginTop: 8 }}>
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Project Details</h3>
              <div className="form-group">
                <label className="form-label">Project Name</label>
                <input className="form-input" placeholder="My Java Project" value={projectName} onChange={e => setProjectName(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Framework Selection</label>
                <label className="form-check radio">
                  <input type="radio" name="fw" checked={framework === 'PIT'} onChange={() => setFramework('PIT')} />
                  PIT (Java / Maven / Gradle)
                </label>
                <label className="form-check radio">
                  <input type="radio" name="fw" checked={framework === 'STRYKER'} onChange={() => setFramework('STRYKER')} />
                  Stryker (JavaScript / TypeScript)
                </label>
              </div>
              <div className="form-group">
                <label className="form-check">
                  <input type="checkbox" defaultChecked /> Exclude node_modules and build directories
                </label>
                <label className="form-check">
                  <input type="checkbox" /> Analyze only files modified in last commit
                </label>
              </div>
            </div>
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Quick Start Options</h3>
              {[
                ['☕', 'Load Sample Java Project'],
                ['🟡', 'Load Sample JavaScript Project'],
                ['🔗', 'Clone from GitHub'],
                ['📂', 'Load Last Used Project'],
                ['📁', 'Browse Recent Projects'],
              ].map(([icon, label]) => (
                <button key={label} className="quick-btn">{icon} {label} <TooltipIcon text={label} /></button>
              ))}

              {file && (
                <div className="detected-box mt-3">
                  <div className="section-head" style={{ color: 'var(--blue)', marginBottom: 8 }}>Detected Info:</div>
                  <div className="detected-row">✓ Framework: {framework === 'PIT' ? 'PIT (Java)' : 'Stryker (JavaScript)'}</div>
                  <div className="detected-row">✓ Archive: {file.name}</div>
                  <div className="detected-row">✓ Size: {(file.size / 1024 / 1024).toFixed(1)} MB</div>
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <button className="btn btn-secondary" onClick={() => nav('/dashboard')}>Cancel</button>
            <button className="btn btn-primary btn-lg" onClick={handleStep1Next} disabled={loading}>
              {loading ? 'Uploading…' : 'Next: Configure →'}
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );

  // ── Step 2: Configure ─────────────────────────────────────────
  if (step === 2) return (
    <AppShell>
      <WizardHeader title="New Test Session" step={2} totalSteps={3} stepLabel="Configure Mutations"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 780, margin: '0 auto' }}>
          <h2 style={{ fontSize: 17, fontWeight: 700, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
            Configure Mutation Testing <TooltipIcon text="Customize operators and strategy" />
          </h2>
          <p style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 18 }}>
            Customize which mutation operators to use and how IMPT should prioritize them for optimal efficiency.
          </p>

          {/* Strategy */}
          <div className="form-group">
            <label className="form-label">Mutation Strategy <TooltipIcon text="How IMPT selects and prioritizes mutants" /></label>
            <select className="form-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
              {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <InfoBox style={{ marginTop: 8 }}>
              <strong>📊 {STRATEGIES.find(s => s.value === strategy)?.label}</strong><br />
              {STRATEGIES.find(s => s.value === strategy)?.desc}
            </InfoBox>
          </div>

          {/* Thread count */}
          <div className="form-group">
            <label className="form-label">Parallel Execution (Thread Count) <TooltipIcon text="Number of parallel test runners" /></label>
            <input type="range" min={1} max={8} value={threads}
              style={{ '--v': `${((threads - 1) / 7) * 100}%` }}
              onChange={e => setThreads(+e.target.value)} />
            <div className="slider-labels"><span>1 thread</span><span style={{ color: 'var(--purple-mid)', fontWeight: 600 }}>{threads} threads</span><span>8 threads</span></div>
            <InfoBox style={{ marginTop: 8 }}>
              💡 <strong>Recommended: {threads} threads</strong><br />
              Testing will be ~{threads}x faster than single-threaded.
            </InfoBox>
          </div>

          {/* Operators */}
          <div className="form-group">
            <label className="form-label">Mutation Operators <TooltipIcon text="Which code changes to introduce" /></label>
            <p style={{ fontSize: 12.5, color: 'var(--gray-500)', marginBottom: 10 }}>
              Select which mutation operators to include. Effectiveness ratings show how often each operator exposes test gaps.
            </p>
            <InfoBox style={{ marginBottom: 12, fontSize: 12 }}>
              📚 <strong>Theoretical Background:</strong> Mutation operators systematically introduce small defects into code
              to verify that tests detect them. High-effectiveness operators frequently reveal real test suite weaknesses.
              Based on studies by Offutt, Rothermel, & Zapf (2002); Namin, Andrews, & Murdoch (2008);
              Papadakis, Kintis, Zhang, Jia, Traon, & Harman (2019).
            </InfoBox>
            {OPERATORS.map(op => (
              <div key={op.code} className={`op-item ${selectedOps.has(op.code) ? 'checked' : ''}`}
                onClick={() => toggleOp(op.code)}>
                <input type="checkbox" checked={selectedOps.has(op.code)} onChange={() => toggleOp(op.code)}
                  style={{ accentColor: 'var(--purple-mid)', width: 16, height: 16, flexShrink: 0 }} />
                <div className="op-info">
                  <div className="op-name">
                    {op.code} - {op.name}
                    <span className={`eff-tag ${op.lvl === 'High' ? 'eff-high' : 'eff-med'}`}>
                      {op.eff}% ({op.lvl} Effectiveness)
                    </span>
                  </div>
                  <div className="op-desc">{op.desc}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Summary */}
          <div className="card" style={{ background: 'var(--gray-50)' }}>
            <div className="card-title" style={{ fontSize: 13 }}>📊 Expected Testing Configuration</div>
            <div className="summary-row"><span className="lbl">Selected Mutation Operators</span><span className="val">{selectedOps.size} of {OPERATORS.length}</span></div>
            <div className="summary-row"><span className="lbl">Estimated Total Mutants</span><span className="val">~{estMutants} mutants</span></div>
            <div className="summary-row"><span className="lbl">Average Effectiveness Rating</span><span className="val text-green">
              {Math.round(OPERATORS.filter(o => selectedOps.has(o.code)).reduce((a, o) => a + o.eff, 0) / Math.max(selectedOps.size, 1))}% (High)
            </span></div>
            <div className="summary-row"><span className="lbl">Strategy</span><span className="val">{STRATEGIES.find(s => s.value === strategy)?.label.split(' (')[0]}</span></div>
            <Alert type="success" style={{ marginTop: 8, marginBottom: 0 }}>
              ✓ Optimal Configuration - This setup balances thoroughness with efficiency.
            </Alert>
          </div>

          <div className="flex justify-between mt-4">
            <button className="btn btn-secondary" onClick={() => setStep(1)}>← Back</button>
            <button className="btn btn-primary btn-lg" onClick={() => setStep(3)}>Next: Set Time Budget →</button>
          </div>
        </div>
      </div>
    </AppShell>
  );

  // ── Step 3: Time Budget ───────────────────────────────────────
  return (
    <AppShell>
      <WizardHeader title="New Test Session" step={3} totalSteps={3} stepLabel="Set Time Budget"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 780, margin: '0 auto' }}>
          <h2 style={{ fontSize: 17, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            Set Time Budget & Run <TooltipIcon text="How long to spend on mutation testing" />
          </h2>

          {error && <Alert type="error">{error}</Alert>}

          <div className="grid-2" style={{ gap: 24 }}>
            <div>
              <label className="form-label">Time Budget <TooltipIcon text="Total time for the mutation testing session" /></label>
              <p style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 14 }}>How much time do you want to spend testing?</p>
              <input type="range" min={5} max={60} value={budget}
                style={{ '--v': `${budgetPct}%` }}
                onChange={e => setBudget(+e.target.value)} />
              <div className="slider-val">{budget} <span>min</span></div>
              <div className="slider-labels"><span>5 minutes (Fast)</span><span>60 minutes (Thorough)</span></div>

              <InfoBox style={{ marginTop: 16 }}>
                <strong>📊 Estimated:</strong><br />
                Mutants tested: ~{toExecute} of {estMutants} ({Math.round(toExecute / Math.max(estMutants, 1) * 100)}%)<br />
                Time savings: 75-85% vs exhaustive testing<br />
                Expected correlation: <span className="badge badge-green" style={{ fontSize: 11 }}>≥0.95 (High)</span>
              </InfoBox>

              <InfoBox variant="green" style={{ marginTop: 10 }}>
                <strong>📊 What does "High Correlation (≥0.95)" mean?</strong><br /><br />
                <strong>Correlation measures how closely IMPT's results match exhaustive testing.</strong> A correlation of 0.95
                means 95% agreement between IMPT's prioritized testing and testing all mutants.<br /><br />
                <div style={{ background: 'rgba(255,255,255,0.6)', padding: '8px 10px', borderRadius: 6, marginTop: 6, fontSize: 12 }}>
                  💡 <strong>In practice:</strong> If exhaustive testing gives 85%, IMPT will report 83-87% (within ±2%).
                  This means you can trust IMPT's results while saving ~75% of testing time.
                </div>
              </InfoBox>

              <div style={{ marginTop: 16 }}>
                <div className="form-label" style={{ marginBottom: 8 }}>Output Options</div>
                {Object.entries({ html: 'Generate HTML report', csv: 'Export to CSV/JSON', email: 'Email results when complete', baseline: 'Save as baseline' }).map(([k, label]) => (
                  <label key={k} className="form-check">
                    <input type="checkbox" checked={outputOpts[k]} onChange={e => setOutputOpts(o => ({ ...o, [k]: e.target.checked }))} />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            <div>
              <div className="card" style={{ background: 'var(--gray-50)', marginBottom: 14 }}>
                <div className="card-title" style={{ fontSize: 13 }}>Estimation Preview</div>
                <div className="summary-row"><span className="lbl">Total Mutants</span><span className="val">~{estMutants}</span></div>
                <div className="summary-row"><span className="lbl">To Execute</span><span className="val text-amber">~{toExecute} ({Math.round(toExecute / Math.max(estMutants, 1) * 100)}%)</span></div>
                <div className="summary-row"><span className="lbl">Estimated Time</span><span className="val text-amber">{budget} minutes</span></div>
                <div className="summary-row"><span className="lbl">Expected Score</span><span className="val text-green">85-92%</span></div>
                <div className="summary-row"><span className="lbl">Confidence</span><span className="val text-green">High (≥0.95)</span></div>
                <div className="summary-row"><span className="lbl">Time Savings</span><span className="val text-green">~{budget + 20} minutes</span></div>
              </div>

              <div className="form-group">
                <label className="form-label">Quick Profiles <TooltipIcon text="Load a saved configuration preset" /></label>
                <select className="form-select">
                  <option>Standard Test (20 min)</option>
                  <option>Quick CI/CD (10 min)</option>
                  <option>Thorough Analysis (30 min)</option>
                  <option>Speed Test (5 min)</option>
                </select>
                <div className="text-xs text-muted mt-1">💡 Standard test balances speed and accuracy for most projects.</div>
              </div>
            </div>
          </div>

          <div className="flex justify-between mt-4" style={{ gap: 12 }}>
            <button className="btn btn-secondary" onClick={() => setStep(2)}>← Back</button>
            <div className="flex gap-3">
              <button className="btn btn-outline" onClick={() => nav('/profiles')}>Save as Profile</button>
              <button className="btn btn-success btn-lg" onClick={handleSubmit} disabled={loading}>
                {loading ? 'Starting…' : '🚀 Start Mutation Testing'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
