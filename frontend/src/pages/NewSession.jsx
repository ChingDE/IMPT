// src/pages/NewSession.jsx  FR051–FR096
import { useState, useRef, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { createSession, getSession, uploadProject, configureOperators, setBudget, startTesting } from '../api/client';
import { AppShell, WizardHeader, Alert, InfoBox, TooltipIcon } from '../components/UI';

const OPERATORS = [
  { code:'AOR', name:'Arithmetic Operator Replacement', eff:92, lvl:'High', desc:'Replaces arithmetic operators (+,-,*,/). Example: a+b → a-b' },
  { code:'ROR', name:'Relational Operator Replacement', eff:88, lvl:'High', desc:'Changes comparison operators (<,>,==,!=). Example: x<10 → x<=10' },
  { code:'COR', name:'Conditional Operator Replacement', eff:85, lvl:'High', desc:'Alters boolean conditions. Example: if(a) → if(!a)' },
  { code:'SOR', name:'Shift Operator Replacement',       eff:76, lvl:'Moderate', desc:'Replaces bitwise shift operators.' },
  { code:'LCR', name:'Logical Connector Replacement',    eff:71, lvl:'Moderate', desc:'Replace logical connectors. Example: && → ||' },
  { code:'UOI', name:'Unary Operator Insertion',         eff:85, lvl:'High', desc:'Add/remove unary operators. Example: x → -x' },
  { code:'SDL', name:'Statement Deletion',               eff:75, lvl:'Moderate', desc:'Remove a statement entirely.' },
  { code:'CRP', name:'Constant Replacement',             eff:65, lvl:'Moderate', desc:'Replace constants with different values.' },
];

// ── Step 1: Create session ─────────────────────────────────────
export function NewSessionCreate() {
  const nav = useNavigate();
  const [form, setForm] = useState({ name: '', language: 'java', description: '' });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  const validate = () => {
    const e = {};
    if (!form.name.trim()) e.name = 'Session name is required';
    else if (!/^[A-Za-z0-9\s\-_]+$/.test(form.name)) e.name = 'Only letters, numbers, spaces, hyphens, underscores';
    else if (form.name.length > 100) e.name = 'Session name must be 100 characters or fewer';
    return e;
  };

  const handleSubmit = async e => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setLoading(true);
    try {
      const session = await createSession({ name: form.name.trim(), language: form.language, description: form.description || undefined });
      nav(`/sessions/${session.id}/upload`);
    } catch (err) {
      setErrors({ global: err.response?.data?.detail || 'Failed to create session.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <WizardHeader title="New Test Session" step={1} totalSteps={5} stepLabel="Create Session"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 560, margin: '0 auto' }}>
          <h2 style={{ fontSize:17,fontWeight:700,marginBottom:20 }}>Create New Session</h2>
          {errors.global && <Alert type="error">{errors.global}</Alert>}
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Session Name *</label>
              <input className={`form-input ${errors.name ? 'error' : ''}`}
                placeholder="e.g. Calculator-Unit-Tests" maxLength={100}
                value={form.name} onChange={e => { setForm(f=>({...f,name:e.target.value})); setErrors({}); }} />
              {errors.name && <div className="form-hint err">{errors.name}</div>}
              <div style={{ fontSize:11,color:'var(--gray-400)',marginTop:4 }}>{form.name.length}/100 characters</div>
            </div>
            <div className="form-group">
              <label className="form-label">Programming Language *</label>
              <select className="form-select" value={form.language} onChange={e => setForm(f=>({...f,language:e.target.value}))}>
                <option value="java">Java</option>
                <option value="javascript">JavaScript</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Description <span style={{color:'var(--gray-400)',fontWeight:400}}>(Optional)</span></label>
              <textarea className="form-input" rows={3} maxLength={500} placeholder="Brief description of what you're testing…"
                value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))}
                style={{ resize:'vertical' }} />
              <div style={{ fontSize:11,color:'var(--gray-400)',marginTop:4 }}>{form.description.length}/500 characters</div>
            </div>
            <div className="flex justify-between mt-4">
              <button type="button" className="btn btn-secondary" onClick={() => nav('/dashboard')}>Cancel</button>
              <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
                {loading ? 'Creating…' : 'Create Session →'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </AppShell>
  );
}

// ── Step 2: Upload project ─────────────────────────────────────
export function NewSessionUpload() {
  const { id } = useParams();
  const nav = useNavigate();
  const fileRef = useRef();
  const [session, setSession]   = useState(null);
  const [file, setFile]         = useState(null);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => { getSession(id).then(setSession).catch(() => nav('/dashboard')); }, [id]);

  if (!session) return (
    <AppShell>
      <div className="page-content" style={{ textAlign:'center', paddingTop:60, color:'var(--gray-400)' }}>
        Loading session…
      </div>
    </AppShell>
  );

  const handleFile = f => {
    if (!f) return;
    if (!f.name.endsWith('.zip')) { setError('Invalid file type. Please upload a .zip file.'); return; }
    if (f.size > 50 * 1024 * 1024) { setError('File size exceeds 50MB limit.'); return; }
    setFile(f); setError('');
  };

  const handleUpload = async () => {
    if (!file) { setError('Please select a file to upload.'); return; }
    setUploading(true); setError(''); setProgress(0);
    try {
      const fd = new FormData(); fd.append('file', file);
      // Simulate progress
      const interval = setInterval(() => setProgress(p => Math.min(p + 10, 90)), 200);
      const updated = await uploadProject(id, fd);
      clearInterval(interval); setProgress(100);
      setSession(updated);
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please check your project structure.');
    } finally {
      setUploading(false);
    }
  };

  const uploaded = session?.status !== 'not_started';
  const lang = session?.language || 'java';

  return (
    <AppShell>
      <WizardHeader title={session?.name || 'New Test Session'} step={2} totalSteps={5} stepLabel="Upload Project"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 720, margin: '0 auto' }}>
          <h2 style={{ fontSize:17,fontWeight:700,marginBottom:8 }}>Upload Your Project</h2>
          <p style={{ fontSize:13,color:'var(--gray-500)',marginBottom:16 }}>
            Please upload a ZIP file containing your project with test cases. Ensure build configuration
            ({lang === 'java' ? 'pom.xml or build.gradle for Java' : 'package.json for JavaScript'}) is included.
          </p>

          {error && <Alert type="error">{error}</Alert>}

          {/* Upload zone */}
          <div className={`drop-zone ${dragOver?'active':''} ${uploaded?'success':''}`}
            style={{ marginBottom:16 }}
            onClick={() => !uploaded && fileRef.current?.click()}
            onDragOver={e=>{e.preventDefault();setDragOver(true)}}
            onDragLeave={()=>setDragOver(false)}
            onDrop={e=>{e.preventDefault();setDragOver(false);handleFile(e.dataTransfer.files[0])}}>
            <div style={{ fontSize:36,marginBottom:8 }}>{uploaded?'✅':file?'📦':'☁️'}</div>
            <div style={{ fontSize:15,fontWeight:600,color:'var(--gray-700)',marginBottom:4 }}>
              {uploaded ? `✓ ${session.upload_filename}` : file ? file.name : 'Drag and drop project folder here'}
            </div>
            <div style={{ fontSize:13,color:'var(--gray-400)',marginBottom:8 }}>
              {uploaded ? 'Project uploaded successfully!' : 'or'}
            </div>
            {!uploaded && !file && (
              <button className="btn btn-primary" style={{pointerEvents:'none'}}>📁 Choose File</button>
            )}
            {!uploaded && file && (
              <div style={{ fontSize:12,color:'var(--gray-500)' }}>{(file.size/1024/1024).toFixed(1)} MB</div>
            )}
            <input ref={fileRef} type="file" accept=".zip" style={{ display:'none' }}
              onChange={e => handleFile(e.target.files[0])} />
          </div>

          {/* Upload progress */}
          {uploading && (
            <div className="mb-3">
              <div style={{ fontSize:13,color:'var(--gray-600)',marginBottom:6 }}>Uploading… {progress}%</div>
              <div style={{ background:'var(--gray-200)',height:8,borderRadius:4,overflow:'hidden' }}>
                <div style={{ width:`${progress}%`,height:'100%',background:'var(--purple-mid)',borderRadius:4,transition:'width .2s' }} />
              </div>
            </div>
          )}

          {/* Project details after upload */}
          {uploaded && session && (
            <div style={{ background:'var(--green-xlight)',border:'1px solid var(--green-light)',borderRadius:8,padding:'14px 16px',marginBottom:16 }}>
              <div style={{ fontWeight:600,color:'var(--green)',marginBottom:8 }}>✓ Project Uploaded Successfully</div>
              <div className="grid-3" style={{ gap:12 }}>
                {[['Files',session.file_count||0],['Lines of Code',session.loc?.toLocaleString()||0],['Test Files',session.test_count||0]].map(([l,v])=>(
                  <div key={l} style={{ textAlign:'center' }}>
                    <div style={{ fontSize:20,fontWeight:700,color:'var(--gray-800)' }}>{v}</div>
                    <div style={{ fontSize:11,color:'var(--gray-500)' }}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:8,fontSize:12,color:'var(--gray-500)' }}>
                Framework detected: <strong>{session.detected_framework}</strong>
              </div>
            </div>
          )}

          <InfoBox>
            <strong>💡 File size limit:</strong> Maximum 50MB. Only .zip files are accepted.{' '}
            {lang==='java' ? 'Java projects must include pom.xml or build.gradle.' : 'JavaScript projects must include package.json.'}
          </InfoBox>

          <div className="flex justify-between mt-4">
            <button className="btn btn-secondary" onClick={() => nav('/new-session')}>← Back</button>
            {!uploaded ? (
              <button className="btn btn-primary btn-lg" onClick={handleUpload} disabled={!file || uploading}>
                {uploading ? 'Uploading…' : 'Upload & Continue →'}
              </button>
            ) : (
              <button className="btn btn-primary btn-lg" onClick={() => nav(`/sessions/${id}/operators`)}>
                Next: Configure Operators →
              </button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Step 3: Configure operators ────────────────────────────────
export function NewSessionOperators() {
  const { id } = useParams();
  const nav    = useNavigate();
  const [session, setSession] = useState(null);
  const [selected, setSelected] = useState(new Set(OPERATORS.map(o=>o.code)));
  const [error, setError]   = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { getSession(id).then(s => { setSession(s); if(s.selected_operators) setSelected(new Set(JSON.parse(s.selected_operators))); }).catch(()=>nav('/dashboard')); }, [id]);

  if (!session) return <AppShell><div className="page-content" style={{textAlign:'center',paddingTop:60,color:'var(--gray-400)'}}>Loading…</div></AppShell>;

  const toggle = code => setSelected(s => { const n=new Set(s); n.has(code)?n.delete(code):n.add(code); return n; });

  const handleNext = async () => {
    if (selected.size === 0) { setError('Please select at least one mutation operator.'); return; }
    setLoading(true); setError('');
    try {
      await configureOperators(id, [...selected]);
      nav(`/sessions/${id}/budget`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save configuration.');
    } finally { setLoading(false); }
  };

  return (
    <AppShell>
      <WizardHeader title={session?.name || 'New Test Session'} step={3} totalSteps={5} stepLabel="Configure Mutations"
        right={<button className="hdr-btn ghost" onClick={()=>nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth:720,margin:'0 auto' }}>
          <h2 style={{ fontSize:17,fontWeight:700,marginBottom:4 }}>Configure Mutation Testing</h2>
          <p style={{ fontSize:13,color:'var(--gray-500)',marginBottom:16 }}>
            Select which mutation operators to include. Effectiveness ratings show how often each operator exposes test gaps.
          </p>

          {error && <Alert type="error">{error}</Alert>}

          {/* FR074 — Select/Deselect all */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex gap-2">
              <button className="btn btn-outline btn-sm" onClick={()=>setSelected(new Set(OPERATORS.map(o=>o.code)))}>Select All</button>
              <button className="btn btn-outline-gray btn-sm" onClick={()=>setSelected(new Set())}>Deselect All</button>
            </div>
            {/* FR075 — Count */}
            <div style={{ fontSize:13,color:'var(--gray-500)',fontWeight:600 }}>
              {selected.size} of {OPERATORS.length} operators selected
            </div>
          </div>

          {/* FR077 — Warning for < 5 operators */}
          {selected.size > 0 && selected.size < 5 && (
            <Alert type="warn">Warning: Selecting very few operators may result in limited test suite quality assessment.</Alert>
          )}

          {OPERATORS.map(op => (
            <div key={op.code} className={`op-item ${selected.has(op.code)?'checked':''}`}
              onClick={()=>toggle(op.code)}>
              <input type="checkbox" checked={selected.has(op.code)} onChange={()=>toggle(op.code)}
                style={{accentColor:'var(--purple-mid)',width:16,height:16,flexShrink:0}} />
              <div className="op-info">
                <div className="op-name">
                  {op.code} — {op.name}
                  <span className={`eff-tag ${op.lvl==='High'?'eff-high':'eff-med'}`}>
                    {op.eff}% ({op.lvl} Effectiveness)
                  </span>
                </div>
                <div className="op-desc">{op.desc}</div>
              </div>
            </div>
          ))}

          <div className="flex justify-between mt-4">
            <button className="btn btn-secondary" onClick={()=>nav(`/sessions/${id}/upload`)}>← Back</button>
            <button className="btn btn-primary btn-lg" onClick={handleNext} disabled={loading||selected.size===0}>
              {loading?'Saving…':'Next: Set Time Budget →'}
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Step 4: Time budget ────────────────────────────────────────
export function NewSessionBudget() {
  const { id } = useParams();
  const nav    = useNavigate();
  const [session, setSession] = useState(null);
  const [budget, setBudgetVal] = useState(20);
  const [runComparison, setRunComparison] = useState(true);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { getSession(id).then(s=>{setSession(s);if(s.time_budget_minutes)setBudgetVal(s.time_budget_minutes);}).catch(()=>nav('/dashboard')); },[id]);

  if (!session) return <AppShell><div className="page-content" style={{textAlign:'center',paddingTop:60,color:'var(--gray-400)'}}>Loading…</div></AppShell>;

  // FR087 — Dynamic metrics
  const estCoverage = Math.min(100, Math.round(10 + (budget/120)*85));
  const correlation = budget >= 30 ? 'High (≥0.95)' : budget >= 15 ? 'Medium (0.85-0.94)' : 'Low (<0.85)';
  const corrColor   = budget >= 30 ? 'var(--green)' : budget >= 15 ? 'var(--amber)' : 'var(--red)';

  const handleNext = async () => {
    setLoading(true); setError('');
    try {
      await setBudget(id, { time_budget_minutes: budget, run_comparison: runComparison });
      nav(`/sessions/${id}/review`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save budget.');
    } finally { setLoading(false); }
  };

  return (
    <AppShell>
      <WizardHeader title={session?.name||'New Test Session'} step={4} totalSteps={5} stepLabel="Set Time Budget"
        right={<button className="hdr-btn ghost" onClick={()=>nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth:720,margin:'0 auto' }}>
          <h2 style={{ fontSize:17,fontWeight:700,marginBottom:4 }}>Set Time Budget</h2>
          <p style={{ fontSize:13,color:'var(--gray-500)',marginBottom:16 }}>How much time do you want to spend testing?</p>

          {error && <Alert type="error">{error}</Alert>}

          <div className="grid-2" style={{ gap:24 }}>
            <div>
              {/* FR082 — Time budget input */}
              <label className="form-label">Time Budget (minutes)</label>
              <input type="range" min={5} max={120} value={budget}
                style={{'--v':`${((budget-5)/115)*100}%`}}
                onChange={e=>setBudgetVal(+e.target.value)} />
              <div className="slider-val">{budget} <span>min</span></div>
              <div className="slider-labels"><span>5 min (Fast)</span><span>120 min (Thorough)</span></div>

              {/* FR083 — Validation */}
              {budget < 5 && <Alert type="error">Time budget must be at least 5 minutes.</Alert>}

              {/* FR084 — Yellow warning for < 10 min */}
              {budget >= 5 && budget < 10 && (
                <Alert type="warn">⚠ Low time budget may result in reduced mutation coverage and lower correlation with exhaustive testing.</Alert>
              )}

              {/* FR086 — Green for ≥ 30 min */}
              {budget >= 30 && (
                <Alert type="success">✓ High time budget selected. Expect high confidence coverage and correlation with exhaustive testing.</Alert>
              )}

              {/* FR093 — Comparison toggle */}
              <div className="mt-4">
                <label className="form-check">
                  <input type="checkbox" checked={runComparison} onChange={e=>setRunComparison(e.target.checked)} />
                  Run comparison with Random Sampling strategy
                </label>
                <div style={{ fontSize:12,color:'var(--gray-400)',marginLeft:22 }}>
                  Default: on. Disabling reduces execution time but removes comparative metrics.
                </div>
              </div>

              {/* FR088 — Recommendations */}
              <div className="mt-4">
                <div className="section-head">Use Case Recommendations</div>
                {[
                  { range:'30+ min', label:'Quality Gates', desc:'Thorough CI/CD pipeline validation' },
                  { range:'15-20 min', label:'Trend Monitoring', desc:'Regular test quality tracking' },
                  { range:'5-15 min', label:'Preliminary Testing', desc:'Quick feedback during development' },
                ].map(r => (
                  <div key={r.label} style={{ background:'var(--gray-50)',border:'1px solid var(--gray-200)',borderRadius:6,padding:'10px 12px',marginBottom:6,fontSize:12.5,cursor:'pointer' }}
                    onClick={()=>{const m=parseInt(r.range);setBudgetVal(m>=30?30:m>=15?17:10)}}>
                    <strong>{r.label}</strong> ({r.range}) — {r.desc}
                  </div>
                ))}
              </div>
            </div>

            {/* FR087 — Real-time preview */}
            <div>
              <div className="card" style={{ background:'var(--gray-50)' }}>
                <div className="card-title" style={{ fontSize:13 }}>Estimation Preview</div>
                {[
                  ['Estimated Coverage', `${estCoverage}%`, estCoverage>=70?'var(--green)':'var(--amber)'],
                  ['Predicted Correlation', correlation, corrColor],
                  ['Confidence Level', budget>=30?'High':budget>=15?'Medium':'Low', corrColor],
                  ['Time Budget', `${budget} minutes`, 'var(--gray-700)'],
                ].map(([l,v,c])=>(
                  <div className="summary-row" key={l}>
                    <span className="lbl">{l}</span>
                    <span className="val" style={{ color:c }}>{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-between mt-4">
            <button className="btn btn-secondary" onClick={()=>nav(`/sessions/${id}/operators`)}>← Back</button>
            <button className="btn btn-primary btn-lg" onClick={handleNext} disabled={loading||budget<5}>
              {loading?'Saving…':'Next: Review & Start →'}
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// ── Step 5: Review & Start ─────────────────────────────────────
export function NewSessionReview() {
  const { id } = useParams();
  const nav    = useNavigate();
  const [session, setSession] = useState(null);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  useEffect(() => { getSession(id).then(setSession).catch(()=>nav('/dashboard')); },[id]);

  const ops = session?.selected_operators ? JSON.parse(session.selected_operators) : [];

  const handleStart = async () => {
    setShowConfirm(false);
    setLoading(true); setError('');
    try {
      await startTesting(id);
      nav(`/running/${id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start testing.');
    } finally { setLoading(false); }
  };

  if (!session) return <AppShell><div className="page-content" style={{ textAlign:'center',paddingTop:60 }}>Loading…</div></AppShell>;

  return (
    <AppShell>
      <WizardHeader title={session.name} step={5} totalSteps={5} stepLabel="Review & Start"
        right={<button className="hdr-btn ghost" onClick={()=>nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth:720,margin:'0 auto' }}>
          <h2 style={{ fontSize:17,fontWeight:700,marginBottom:4 }}>Review Configuration</h2>
          <p style={{ fontSize:13,color:'var(--gray-500)',marginBottom:20 }}>Review your settings before starting mutation testing.</p>

          {error && <Alert type="error">{error}</Alert>}

          {/* FR091 — Summary */}
          <div className="card" style={{ background:'var(--gray-50)',marginBottom:16 }}>
            <div className="card-title" style={{ fontSize:13 }}>Session Summary</div>
            {[
              ['Session Name', session.name],
              ['Language', session.language === 'java' ? 'Java' : 'JavaScript'],
              ['Project File', session.upload_filename || '—'],
              ['Lines of Code', session.loc?.toLocaleString() || '—'],
              ['Selected Operators', `${ops.length} of ${OPERATORS.length} (${ops.join(', ')})`],
              ['Time Budget', `${session.time_budget_minutes} minutes`],
              ['Comparison Strategies', session.run_comparison ? 'IMPT Intelligent + Random Sampling' : 'IMPT Intelligent only'],
            ].map(([l,v])=>(
              <div className="summary-row" key={l}>
                <span className="lbl">{l}</span>
                <span className="val" style={{ maxWidth:360,textAlign:'right',fontSize:13 }}>{v}</span>
              </div>
            ))}
          </div>

          {/* FR092 — Edit links */}
          <div className="flex gap-2 mb-4" style={{ flexWrap:'wrap' }}>
            <button className="btn btn-outline-gray btn-sm" onClick={()=>nav(`/sessions/${id}/upload`)}>✏ Edit Project</button>
            <button className="btn btn-outline-gray btn-sm" onClick={()=>nav(`/sessions/${id}/operators`)}>✏ Edit Operators</button>
            <button className="btn btn-outline-gray btn-sm" onClick={()=>nav(`/sessions/${id}/budget`)}>✏ Edit Time Budget</button>
          </div>

          <InfoBox>
            <strong>⏱ Estimated duration:</strong> {session.time_budget_minutes} minutes.
            The test will run in the background — you can safely navigate away and return to check progress.
          </InfoBox>

          <div className="flex justify-between mt-4">
            <button className="btn btn-secondary" onClick={()=>nav(`/sessions/${id}/budget`)}>← Back</button>
            <div className="flex gap-3">
              <button className="btn btn-secondary" onClick={()=>nav('/dashboard')}>Cancel</button>
              <button className="btn btn-success btn-lg" onClick={()=>setShowConfirm(true)} disabled={loading}>
                {loading ? 'Starting…' : '🚀 Start Mutation Testing'}
              </button>
            </div>
          </div>
          {/* FR095 — Confirmation modal before starting */}
          {showConfirm && (
            <div className="timeout-overlay">
              <div className="timeout-modal" style={{ maxWidth:440 }}>
                <h3 style={{ marginBottom:8 }}>Ready to start mutation testing?</h3>
                <p style={{ fontSize:13.5,color:'var(--gray-600)',lineHeight:1.65,marginBottom:16 }}>
                  This will execute mutation testing with your configured settings.{' '}
                  <br /><strong>Estimated time: {session?.time_budget_minutes} minute(s).</strong>
                </p>
                <div className="flex gap-3 justify-end">
                  <button className="btn btn-secondary" onClick={()=>setShowConfirm(false)} autoFocus>Cancel</button>
                  <button className="btn btn-success" onClick={handleStart} disabled={loading}>
                    {loading ? 'Starting…' : 'Confirm & Start'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
