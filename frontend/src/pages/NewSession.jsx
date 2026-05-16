// src/pages/NewSession.jsx  FR051–FR096
import { useState, useRef, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { createSession, getSession, uploadProject, configureOperators, setBudget, startTesting, listFossProjects, updateSession } from '../api/client';
import { AppShell, WizardHeader, Alert, InfoBox, TooltipIcon } from '../components/UI';

// Operators supported by IMPT — grouped by framework support
// Effectiveness ratings grounded in Just et al. (2014), n=357 real faults from Defects4J.
// ROR and ABS: directly cited (75-85% fault detection).
// SDL: directly cited (35-45% fault detection).
// AOR, COR: derived from Just et al.'s fault distribution data.
// UOI, LCR, NEGATE_RETURN, NULL_RETURN, CRP: estimates, no direct citation.
// framework: 'both' | 'java' | 'js'
const OPERATORS = [
  { code:'ROR',           name:'Relational Operator Replacement', eff:80, lvl:'High',     framework:'both', desc:'Changes comparison operators (<,>,==,!=). Example: x<10 → x<=10' },
  { code:'ABS',           name:'Conditional Boundary Shift',      eff:80, lvl:'High',     framework:'java', desc:'Shifts boundary conditions. Example: if(x>10) → if(x>=10). Java/PIT only.' },
  { code:'NEGATE_RETURN', name:'Negate Return Value',             eff:75, lvl:'High',     framework:'both', desc:'Negates boolean/primitive return values. Example: return true → return false' },
  { code:'COR',           name:'Conditional Operator Replacement',eff:75, lvl:'High',     framework:'both', desc:'Removes or alters conditional expressions. Example: if(a&&b) → if(a)' },
  { code:'AOR',           name:'Arithmetic Operator Replacement', eff:72, lvl:'Moderate', framework:'both', desc:'Replaces arithmetic operators (+,-,*,/,%). Example: a+b → a-b' },
  { code:'UOI',           name:'Unary Operator Insertion',        eff:68, lvl:'Moderate', framework:'both', desc:'Adds/removes unary operators. Example: x → -x' },
  { code:'LCR',           name:'Logical Connector Replacement',   eff:72, lvl:'Moderate', framework:'js',   desc:'Swaps logical connectors. Example: && → ||. JavaScript/Stryker only.' },
  { code:'NULL_RETURN',   name:'Null/Empty Return Value',         eff:65, lvl:'Moderate', framework:'both', desc:'Replaces return values with null or empty equivalents. Example: return obj → return null' },
  { code:'CRP',           name:'Constant Replacement',            eff:55, lvl:'Moderate', framework:'js',   desc:'Replaces string/regex constants. JavaScript/Stryker only.' },
  { code:'SDL',           name:'Statement Deletion',              eff:40, lvl:'Low',       framework:'both', desc:'Deletes an entire statement or block. Lower fault-detection rate per Just et al. (2014).' },
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

  // Resume session from history — redirect to correct step based on status
  const resumeSession = (session) => {
    const { id, status } = session;
    if (!status || status === 'not_started') return nav(`/sessions/${id}/upload`);
    if (status === 'uploaded')               return nav(`/sessions/${id}/operators`);
    if (status === 'configured')             return nav(`/sessions/${id}/budget`);
    if (status === 'ready')                  return nav(`/sessions/${id}/review`);
    if (status === 'running')                return nav(`/running/${id}`);
    if (status === 'completed')              return nav(`/results/${id}`);
    return nav(`/sessions/${id}/upload`);
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
  const [dragOver, setDragOver]   = useState(false);
  const [uploadDone, setUploadDone] = useState(false);
  const [tab, setTab]           = useState('upload');  // 'upload' | 'foss'
  const [fossProjects, setFossProjects] = useState([]);
  const [fossFilter, setFossFilter] = useState('all');  // all | java | javascript
  const [fossSelected, setFossSelected] = useState(null);

  useEffect(() => {
    getSession(id).then(s => {
      setSession(s);
      if (s.upload_path && s.status !== 'not_started') setUploadDone(true);
      if (s.foss_project_id) { setTab('foss'); setUploadDone(true); }
      if (s.language)         { setFossFilter(s.language); }
    }).catch(err => {
      if (err?.response?.status === 404 || err?.response?.status === 403)
        nav('/dashboard');
      else
        setError('Failed to load session. Please check your connection and try again.');
    });
    listFossProjects().then(setFossProjects).catch(() => {});
  }, [id]);

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
    setUploading(true); setError(''); setProgress(20);
    try {
      const fd = new FormData(); fd.append('file', file);
      setProgress(50);
      const updated = await uploadProject(id, fd);
      setProgress(100);
      setSession(updated);
      setUploadDone(true);
    } catch (err) {
      setProgress(0);
      setError(err.response?.data?.detail || 'Upload failed. Please check your project structure.');
    } finally {
      setUploading(false);
    }
  };

  const uploaded = uploadDone || (session?.status && session.status !== 'not_started' && !!session?.upload_path);
  const lang = session?.language || 'java';

  return (
    <AppShell>
      <WizardHeader title={session?.name || 'New Test Session'} step={2} totalSteps={5} stepLabel="Upload Project"
        right={<button className="hdr-btn ghost" onClick={() => nav('/dashboard')}>Cancel</button>} />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 720, margin: '0 auto' }}>
          <h2 style={{ fontSize:17,fontWeight:700,marginBottom:8 }}>Select Your Project</h2>

          {/* Tab switcher */}
          <div style={{ display:'flex',gap:0,marginBottom:16,borderBottom:'2px solid var(--gray-200)' }}>
            {[['upload','📁 Upload Your Own'],['foss','🔬 Use FOSS Project']].map(([t,l])=>(
              <button key={t}
                style={{ padding:'8px 18px',fontWeight:600,fontSize:13,border:'none',cursor:'pointer',
                  background:'transparent', color: tab===t?'var(--purple-mid)':'var(--gray-500)',
                  borderBottom: tab===t?'2px solid var(--purple-mid)':'2px solid transparent',
                  marginBottom:'-2px' }}
                onClick={()=>setTab(t)}>{l}
              </button>
            ))}
          </div>

          {/* FOSS project panel */}
          {tab === 'foss' && (
            <div>
              <p style={{ fontSize:13,color:'var(--gray-500)',marginBottom:12 }}>
                Select a pre-loaded open-source project. These have pre-computed exhaustive baselines for ground-truth comparison.
              </p>
              {/* Language filter hidden — determined by Step 1 selection */}
              <div style={{ display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))',gap:10,maxHeight:380,overflowY:'auto' }}>
                {fossProjects
                  .filter(p => fossFilter==='all' || p.language===fossFilter)
                  .map(p => (
                  <div key={p.id}
                    style={{ border:`2px solid ${fossSelected?.id===p.id?'var(--purple-mid)':'var(--gray-200)'}`,
                      borderRadius:8,padding:'12px 14px',cursor:'pointer',
                      background: fossSelected?.id===p.id?'var(--purple-xlight)':'#fff' }}
                    onClick={()=>setFossSelected(p)}>
                    <div style={{ display:'flex',justifyContent:'space-between',alignItems:'flex-start' }}>
                      <div style={{ fontWeight:700,fontSize:13 }}>{p.name}</div>
                      <span style={{ fontSize:10,fontWeight:700,padding:'2px 6px',borderRadius:999,
                        background: p.language==='java'?'#dbeafe':'#dcfce7',
                        color: p.language==='java'?'#1d4ed8':'#15803d' }}>
                        {p.language==='java'?'Java':'JS'}
                      </span>
                    </div>
                    <div style={{ fontSize:11,color:'var(--gray-500)',marginTop:3 }}>{p.description.slice(0,90)}…</div>
                    <div style={{ display:'flex',gap:8,marginTop:6,flexWrap:'wrap' }}>
                      <span style={{ fontSize:10,color:'var(--gray-500)' }}>📏 {p.loc.toLocaleString()} LOC</span>
                      <span style={{ fontSize:10,color:'var(--gray-500)' }}>🏷 {p.size_band}</span>
                      {p.has_baseline
                        ? <span style={{ fontSize:10,color:'var(--green)',fontWeight:600 }}>✓ Baseline: {(p.baseline_mutation_score*100).toFixed(1)}%</span>
                        : <span style={{ fontSize:10,color:'var(--amber)' }}>⏳ Baseline pending</span>}
                    </div>
                  </div>
                ))}
              </div>
              {fossSelected && (
                <div style={{ marginTop:12,padding:'10px 14px',background:'var(--green-xlight)',
                  border:'1px solid var(--green-light)',borderRadius:8,fontSize:13 }}>
                  Selected: <strong>{fossSelected.name}</strong> ({fossSelected.loc.toLocaleString()} LOC · {fossSelected.version}) ·{' '}
                  {fossSelected.has_baseline
                    ? <span style={{color:'var(--green)',fontWeight:600}}>Ground truth baseline available ({(fossSelected.baseline_mutation_score*100).toFixed(1)}% exhaustive score)</span>
                    : <span style={{color:'var(--amber)'}}>No baseline yet — will use estimation</span>}
                </div>
              )}
              <div className="flex justify-between mt-4">
                <button className="btn btn-secondary" onClick={()=>nav('/new-session')}>← Back</button>
                <button className="btn btn-primary btn-lg"
                  disabled={!fossSelected || loading}
                  onClick={async () => {
                    if (!fossSelected) return;
                    setLoading(true); setError('');
                    try {
                      await updateSession(id, { foss_project_id: fossSelected.id, language: fossSelected.language });
                      nav(`/sessions/${id}/operators`);
                    } catch(e){ setError(e.response?.data?.detail||'Failed to select project.'); }
                    finally{ setLoading(false); }
                  }}>
                  {loading?'Saving…':'Use This Project →'}
                </button>
              </div>
            </div>
          )}

          {/* Upload panel */}
          {tab === 'upload' && <div>
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
              {uploaded ? `✓ ${session?.upload_filename}` : file ? file.name : 'Drag and drop project folder here'}
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
                {[['Files',session.file_count||0],['Lines of Code',session?.loc?.toLocaleString()||0],['Test Files',session.test_count||0]].map(([l,v])=>(
                  <div key={l} style={{ textAlign:'center' }}>
                    <div style={{ fontSize:20,fontWeight:700,color:'var(--gray-800)' }}>{v}</div>
                    <div style={{ fontSize:11,color:'var(--gray-500)' }}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:8,fontSize:12,color:'var(--gray-500)' }}>
                Framework detected: <strong>{session?.detected_framework}</strong>
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
          </div>}  {/* end tab === 'upload' */}
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
  const [selected, setSelected] = useState(new Set());
  const [availableOps, setAvailableOps] = useState(OPERATORS);
  const [error, setError]   = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getSession(id).then(s => {
      setSession(s);
      const lang = s.language || 'javascript';
      // Show only operators supported by the selected language's framework
      const available = OPERATORS.filter(o =>
        o.framework === 'both' ||
        (lang === 'java'       && o.framework === 'java') ||
        (lang === 'javascript' && o.framework === 'js')
      );
      setAvailableOps(available);
      if (s.selected_operators) {
        try {
          const ops = JSON.parse(s.selected_operators);
          const validCodes = new Set(available.map(o => o.code));
          setSelected(new Set(ops.filter(o => validCodes.has(o))));
        } catch {}
      } else {
        // Default: select all High effectiveness operators for this language
        setSelected(new Set(available.filter(o => o.lvl === 'High').map(o => o.code)));
      }
    }).catch(err => { if(!err?.response?.status || err?.response?.status===404 || err?.response?.status===403) nav('/dashboard'); });
  }, [id]);

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
              <button className="btn btn-outline btn-sm" onClick={()=>setSelected(new Set(availableOps.map(o=>o.code)))}>Select All</button>
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

          {OPERATORS.filter(op => availableOps.some(a => a.code === op.code)).map(op => (
            <div key={op.code} className={`op-item ${selected.has(op.code)?'checked':''}`}
              onClick={()=>toggle(op.code)}>
              <input type="checkbox" checked={selected.has(op.code)} onChange={()=>toggle(op.code)}
                style={{accentColor:'var(--purple-mid)',width:16,height:16,flexShrink:0}} />
              <div className="op-info">
                <div className="op-name">
                  {op.code} — {op.name}
                  <span className={`eff-tag ${op.lvl==='High'?'eff-high':op.lvl==='Low'?'eff-low':'eff-med'}`}>
                    {op.eff}% ({op.lvl} Effectiveness)
                  </span>
                  {op.framework !== 'both' && (
                    <span style={{
                      fontSize:'0.7rem', padding:'1px 6px', borderRadius:4, marginLeft:6,
                      background: op.framework==='java' ? '#dbeafe' : '#dcfce7',
                      color:      op.framework==='java' ? '#1d4ed8' : '#15803d',
                      fontWeight: 600,
                    }}>
                      {op.framework==='java' ? 'Java/PIT only' : 'JS/Stryker only'}
                    </span>
                  )}
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
  const [strategy, setStrategy] = useState('impt');
  const [runExhaustive, setRunExhaustive] = useState(false);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getSession(id).then(s => {
      setSession(s);
      if (s.time_budget_minutes)  setBudgetVal(s.time_budget_minutes);
      if (s.selected_strategy)    setStrategy(s.selected_strategy);
      if (s.run_exhaustive !== undefined) setRunExhaustive(s.run_exhaustive);
    }).catch(err => { if(!err?.response?.status || err?.response?.status===404 || err?.response?.status===403) nav('/dashboard'); });
  }, [id]);

  if (!session) return <AppShell><div className="page-content" style={{textAlign:'center',paddingTop:60,color:'var(--gray-400)'}}>Loading…</div></AppShell>;

  const estCoverage = Math.min(100, Math.round(10 + (budget/120)*85));
  const correlation = budget >= 30 ? 'High (≥0.95)' : budget >= 15 ? 'Medium (0.85-0.94)' : 'Low (<0.85)';
  const corrColor   = budget >= 30 ? 'var(--green)' : budget >= 15 ? 'var(--amber)' : 'var(--red)';

  const STRATEGIES = [
    { value:'impt',           label:'⭐ IMPT Intelligent Prioritization', desc:'Multi-factor scoring, subsumption analysis, knapsack optimization. Recommended.' },
    { value:'operator_based', label:'🔬 Operator-Based Prioritization',   desc:'Selects mutants by historical operator effectiveness. Simple heuristic.' },
    { value:'random',         label:'🎲 Random Sampling',                  desc:'Selects mutants uniformly at random. Baseline comparison strategy.' },
  ];

  const handleNext = async () => {
    setLoading(true); setError('');
    try {
      await setBudget(id, {
        time_budget_minutes: budget,
        selected_strategy:   strategy,
        run_exhaustive:      runExhaustive,
        run_comparison:      false,
        run_operator_based:  false,
      });
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

              {/* Strategy selector */}
              <div className="mt-4">
                <label className="form-label">Prioritization Strategy</label>
                {STRATEGIES.map(s => (
                  <div key={s.value}
                    className={`op-item ${strategy===s.value?'checked':''}`}
                    style={{marginBottom:6}}
                    onClick={()=>setStrategy(s.value)}>
                    <input type="radio" checked={strategy===s.value} onChange={()=>setStrategy(s.value)}
                      style={{accentColor:'var(--purple-mid)',width:16,height:16,flexShrink:0}} />
                    <div className="op-info">
                      <div className="op-name">{s.label}</div>
                      <div className="op-desc">{s.desc}</div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Exhaustive baseline checkbox */}
              <div className="mt-4" style={{background:'var(--amber-light)',border:'1px solid #FDE68A',borderRadius:8,padding:'12px 14px'}}>
                <label className="form-check" style={{fontWeight:600}}>
                  <input type="checkbox" checked={runExhaustive} onChange={e=>setRunExhaustive(e.target.checked)} />
                  Also run Exhaustive Baseline (Ground Truth)
                </label>
                <div style={{fontSize:12,color:'var(--gray-600)',marginLeft:22,marginTop:4,lineHeight:1.55}}>
                  Runs ALL mutants after your chosen strategy completes. Provides real ground-truth mutation score and true correlation.
                  <strong> Warning: significantly increases total execution time.</strong>
                </div>
                {!runExhaustive && (
                  <div style={{fontSize:11,color:'var(--gray-500)',marginLeft:22,marginTop:4}}>
                    Without exhaustive: correlation shown is a <em>statistical estimate</em> (Wilson CI). With exhaustive: it's <em>ground truth</em>.
                  </div>
                )}
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

  useEffect(() => { getSession(id).then(setSession).catch(err => { if(!err?.response?.status || err?.response?.status===404 || err?.response?.status===403) nav('/dashboard'); }); },[id]);

  const ops = session?.selected_operators ? JSON.parse(session.selected_operators) : [];
  const strategyLabel = {
    impt:           '⭐ IMPT Intelligent Prioritization',
    operator_based: '🔬 Operator-Based Prioritization',
    random:         '🎲 Random Sampling',
  }[session?.selected_strategy || 'impt'] || session?.selected_strategy;

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
      <WizardHeader title={session?.name} step={5} totalSteps={5} stepLabel="Review & Start"
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
              ['Language', session?.language === 'java' ? 'Java' : 'JavaScript'],
              ['Project File', session?.upload_filename || '—'],
              ['Lines of Code', session?.loc?.toLocaleString() || '—'],
              ['Selected Operators', `${ops.length} of ${OPERATORS.length} (${ops.join(', ')})`],
              ['Time Budget', `${session?.time_budget_minutes} minutes`],
              ['Prioritization Strategy', strategyLabel],
              ['Exhaustive Baseline', session?.run_exhaustive ? '✓ Yes — Ground Truth comparison' : 'No — Statistical estimate (Wilson CI)'],
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

          {/* Smart time estimate */}
          {(() => {
            const budget      = session?.time_budget_minutes || 20;
            const loc         = session?.loc || 5000;
            const opCount     = ops.length || 5;
            const isJava      = session?.language === 'java';
            const isExhaustive = session?.run_exhaustive;

            // Base estimate: ~0.5s per mutant for JS (mocha), ~2s for Java (PIT)
            // Rough mutant density: ~3 mutants per 10 LOC
            const estMutants   = Math.round(loc * 0.3 * (opCount / 8));
            const secPerMutant = isJava ? 2.5 : 0.8;
            const rawExhaustive = Math.round(estMutants * secPerMutant / 60); // minutes
            const strategy     = session?.selected_strategy || 'impt';
            const reductionPct = strategy === 'impt' ? 0.65 : strategy === 'operator_based' ? 0.5 : 0.6;
            const estPrimary   = Math.max(1, Math.round(rawExhaustive * (1 - reductionPct)));
            const estTotal     = isExhaustive ? estPrimary + rawExhaustive : estPrimary;
            const cappedPrimary = Math.min(estPrimary, budget);

            const fmt = m => m < 1 ? '< 1 min' : m < 60 ? `~${m} min` : `~${(m/60).toFixed(1)} hr`;

            return (
              <div style={{ background:'#EFF6FF', border:'1px solid #BFDBFE', borderRadius:8,
                padding:'12px 16px', marginBottom:16, fontSize:13, lineHeight:1.7 }}>
                <div style={{ fontWeight:700, marginBottom:6 }}>⏱ Estimated Run Time</div>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'4px 16px' }}>
                  <span style={{ color:'var(--gray-600)' }}>Estimated mutants:</span>
                  <span style={{ fontWeight:600 }}>{estMutants.toLocaleString()}</span>
                  <span style={{ color:'var(--gray-600)' }}>Strategy run ({strategy.toUpperCase()}):</span>
                  <span style={{ fontWeight:600, color:'var(--purple-mid)' }}>{fmt(cappedPrimary)}</span>
                  {isExhaustive && <>
                    <span style={{ color:'var(--gray-600)' }}>Exhaustive baseline:</span>
                    <span style={{ fontWeight:600, color:'var(--amber)' }}>{fmt(rawExhaustive)}</span>
                  </>}
                  <span style={{ color:'var(--gray-600)', fontWeight:600 }}>Total estimated:</span>
                  <span style={{ fontWeight:700, color:'var(--green)' }}>{fmt(Math.min(estTotal, budget + (isExhaustive ? rawExhaustive : 0)))}</span>
                </div>
                <div style={{ fontSize:11, color:'var(--gray-500)', marginTop:6 }}>
                  Estimates based on {loc?.toLocaleString() || '?'} LOC × {opCount} operators.
                  Actual time may vary depending on test suite speed.
                  {isExhaustive && ' Exhaustive baseline runs after the primary strategy completes.'}
                </div>
              </div>
            );
          })()}

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
