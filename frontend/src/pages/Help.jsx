// src/pages/Help.jsx
import { useState } from 'react';
import { AppShell, PageHeader } from '../components/UI';

export default function Help() {
  const [active, setActive] = useState('quickstart');
  const sections = [
    { id:'quickstart', label:'Quick Start Guide' },
    { id:'upload',     label:'Uploading Projects' },
    { id:'operators',  label:'Mutation Operators' },
    { id:'budget',     label:'Time Budget' },
    { id:'results',    label:'Understanding Results' },
    { id:'faq',        label:'FAQ' },
  ];

  const H = ({ children }) => (
    <h3 style={{ fontSize:15, fontWeight:700, color:'var(--purple-mid)', marginTop:24, marginBottom:8 }}>{children}</h3>
  );
  const P = ({ children }) => (
    <p style={{ fontSize:13.5, color:'var(--gray-600)', lineHeight:1.75, marginBottom:12 }}>{children}</p>
  );
  const Step = ({ n, title, children }) => (
    <div style={{ display:'flex', gap:12, marginBottom:16 }}>
      <div style={{ width:28, height:28, borderRadius:'50%', background:'var(--purple-mid)',
        color:'#fff', fontWeight:700, fontSize:13, display:'grid', placeItems:'center', flexShrink:0, marginTop:2 }}>{n}</div>
      <div>
        <div style={{ fontWeight:700, fontSize:14, marginBottom:4 }}>{title}</div>
        <div style={{ fontSize:13.5, color:'var(--gray-600)', lineHeight:1.7 }}>{children}</div>
      </div>
    </div>
  );
  const OpRow = ({ name, badge, framework, eff, desc, cite }) => (
    <div style={{ borderLeft:'3px solid var(--purple-mid)', paddingLeft:12, marginBottom:20 }}>
      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4, flexWrap:'wrap' }}>
        <span style={{ fontWeight:700, fontSize:14 }}>{name}</span>
        <span style={{ fontSize:11, fontWeight:700, padding:'2px 8px', borderRadius:999,
          background: eff >= 0.75 ? '#dcfce7' : eff >= 0.65 ? '#fef9c3' : '#fee2e2',
          color: eff >= 0.75 ? '#16a34a' : eff >= 0.65 ? '#ca8a04' : '#dc2626' }}>
          {Math.round(eff*100)}% effectiveness
        </span>
        <span style={{ fontSize:11, padding:'2px 8px', borderRadius:999,
          background:'#ede9fe', color:'var(--purple-mid)' }}>{framework}</span>
      </div>
      <P>{desc}</P>
      <div style={{ fontSize:11, color:'var(--gray-400)', fontStyle:'italic' }}>📚 {cite}</div>
    </div>
  );
  const QA = ({ q, a }) => (
    <div style={{ marginBottom:20 }}>
      <div style={{ fontWeight:700, fontSize:13.5, color:'var(--gray-800)', marginBottom:6 }}>Q: {q}</div>
      <div style={{ fontSize:13.5, color:'var(--gray-600)', lineHeight:1.75 }}>A: {a}</div>
    </div>
  );

  const content = {
    quickstart: (
      <>
        <P>Welcome to IMPT — Intelligent Mutation Prioritization Tool. Follow these five steps to run your first mutation testing session.</P>
        <Step n="1" title="Create a New Session">
          Click <strong>New Test Session</strong> in the sidebar. Enter a descriptive session name and select your project's programming language — Java or JavaScript.
        </Step>
        <Step n="2" title="Select a Project">
          Either upload your own project as a <strong>.zip file</strong>, or choose from IMPT's built-in library of open-source FOSS projects. FOSS projects are pre-configured and ready to test immediately — recommended for your first session.
        </Step>
        <Step n="3" title="Configure Mutation Operators">
          Select which types of code changes IMPT should introduce. The default selection of <strong>High effectiveness operators</strong> (AOR, ROR, NEGATE_RETURN, COR) is recommended for most projects. Only operators supported by your selected language will be shown.
        </Step>
        <Step n="4" title="Set Time Budget & Strategy">
          Set how long IMPT should run (5–120 minutes) and choose a prioritization strategy. <strong>IMPT Intelligent Prioritization</strong> is the default and recommended option — it uses the IMPT algorithm to select the most valuable mutants within your time budget. Optionally enable the Exhaustive Baseline to get a ground-truth comparison score.
        </Step>
        <Step n="5" title="Review & Start">
          Review your full configuration including the estimated run time, then click <strong>Start Mutation Testing</strong>. The session runs in the background and you will be redirected to the live progress screen automatically.
        </Step>
      </>
    ),

    upload: (
      <>
        <P>IMPT accepts project uploads as a <strong>.zip file</strong>. The zip must contain a recognizable project structure at the root level.</P>
        <H>Java Projects</H>
        <P>Your zip must include a <code>pom.xml</code> (Maven) or <code>build.gradle</code> (Gradle) file at the root. IMPT uses PIT (PITest) to run mutation testing on Java projects. Ensure your project compiles and all unit tests pass locally before uploading.</P>
        <P><strong>Supported build systems:</strong> Maven 3.6+, Gradle 7+</P>
        <P><strong>Required structure:</strong></P>
        <P style={{ fontFamily:'monospace', background:'var(--gray-50)', padding:'8px 12px', borderRadius:6 }}>
          project.zip<br/>
          ├── pom.xml (or build.gradle)<br/>
          ├── src/<br/>
          │   ├── main/java/...<br/>
          │   └── test/java/...
        </P>

        <H>JavaScript Projects</H>
        <P>Your zip must include a <code>package.json</code> at the root. IMPT uses Stryker to run mutation testing. Supported test runners are <strong>Jest</strong>, <strong>Mocha</strong>, and <strong>Vitest</strong> — detected automatically from your package.json.</P>
        <P><strong>Required structure:</strong></P>
        <P style={{ fontFamily:'monospace', background:'var(--gray-50)', padding:'8px 12px', borderRadius:6 }}>
          project.zip<br/>
          ├── package.json<br/>
          ├── src/ (or lib/)<br/>
          └── test/ (or __tests__/)
        </P>

        <H>FOSS Projects</H>
        <P>As an alternative to uploading, IMPT provides a curated library of real open-source projects pre-configured for mutation testing. These are recommended for evaluators who want to test IMPT without preparing their own project. Select the <strong>FOSS Projects</strong> tab in the upload step and click any project card to select it.</P>

        <H>File Size Limit</H>
        <P>Maximum upload size is <strong>50MB</strong>. If your project exceeds this, consider excluding build artifacts, <code>node_modules</code>, and binary files from the zip.</P>
      </>
    ),

    operators: (
      <>
        <P>Mutation operators define what kinds of code changes IMPT introduces into your source code. Each mutant is a version of your code with exactly one change applied. If your tests catch the change, the mutant is <strong style={{color:'#16a34a'}}>killed</strong>. If not, it <strong style={{color:'#dc2626'}}>survived</strong> — indicating a potential gap in your test suite.</P>
        <P>Effectiveness ratings are empirically grounded in published mutation testing research. Only operators supported by your selected language will appear during session configuration.</P>

        <H>High Effectiveness</H>
        <OpRow name="ROR — Relational Operator Replacement" badge="High" framework="Java & JavaScript" eff={0.80}
          desc="Replaces relational operators with alternatives (e.g., > becomes >=, < becomes ==). These mutants closely mimic off-by-one errors — one of the most common real-world bug categories — making them highly likely to be caught by well-written tests."
          cite="Just et al. 2014 (Defects4J, n=357): 75–85% real fault detection rate." />
        <OpRow name="ABS — Absolute Value Insertion" badge="High" framework="Java only (PIT)" eff={0.80}
          desc="Wraps numeric expressions with Math.abs(), negation, or zero substitution. Targets arithmetic boundary conditions that commonly cause sign-related bugs. Available only in PIT (Java)."
          cite="Just et al. 2014: 75–85% real fault detection; Wong et al. 1995: top operator selection." />
        <OpRow name="NEGATE_RETURN — Negate Return Value" badge="High" framework="Java & JavaScript" eff={0.75}
          desc="Negates boolean return values (true → false, false → true) or negates numeric returns. Directly tests whether callers handle return values correctly — frequently catches missing or inverted conditional logic in the calling code."
          cite="ISSTA 2023: NegateConditionals/ReturnVals account for ~50% of test crash events." />
        <OpRow name="COR — Conditional Operator Replacement" badge="High" framework="Java & JavaScript" eff={0.75}
          desc="Replaces logical operators in conditionals (e.g., && becomes ||, || becomes &&). Since roughly 60% of real software faults involve incorrect conditional logic, this operator has a high probability of exposing meaningful test gaps."
          cite="Just et al. 2014: ~60% of real faults involve conditional logic errors." />

        <H>Medium Effectiveness</H>
        <OpRow name="AOR — Arithmetic Operator Replacement" badge="Medium" framework="Java & JavaScript" eff={0.72}
          desc="Replaces arithmetic operators with alternatives (e.g., + becomes -, * becomes /). Targets computational errors in numeric logic. Most effective in projects with significant arithmetic operations such as financial calculations or data processing."
          cite="Just et al. 2014: ~25% of real faults are arithmetic; Offutt et al. 1996 sufficient set." />
        <OpRow name="LCR — Logical Connector Replacement" badge="Medium" framework="JavaScript only (Stryker)" eff={0.72}
          desc="Replaces bitwise and logical connectors (e.g., & becomes |, ^ becomes &). Part of Offutt's empirically validated sufficient operator set. Available in Stryker (JavaScript) only."
          cite="Offutt et al. 1996: member of the 5-operator sufficient set achieving 99.5% mutation score." />
        <OpRow name="UOI — Unary Operator Insertion" badge="Medium" framework="Java & JavaScript" eff={0.68}
          desc="Inserts unary operators such as negation or increment/decrement (e.g., x becomes -x, i becomes i++). Targets sign and increment errors. Produces a higher rate of equivalent mutants (syntactically different but semantically identical) which can slightly inflate survived counts."
          cite="Offutt et al. 1996 sufficient set; higher equivalent mutant rate noted in practice." />

        <H>Lower Effectiveness</H>
        <OpRow name="NULL_RETURN — Null / Empty Return" badge="Lower" framework="Java & JavaScript" eff={0.65}
          desc="Replaces object return values with null (Java) or undefined/empty equivalents (JavaScript). Tests whether callers handle null/undefined defensively. Commonly detected because null returns frequently cause NullPointerExceptions or crashes, but may survive in code with lenient null handling."
          cite="ISSTA 2023: NullReturnVals causes frequent NPEs; commonly but not universally detected." />
        <OpRow name="CRP — Constant Replacement" badge="Lower" framework="JavaScript only (Stryker)" eff={0.55}
          desc="Replaces numeric and string constants with alternative values (e.g., 0 becomes 1, 'hello' becomes ''). Effectiveness depends heavily on how well tests validate specific constant values. Projects with many magic numbers and poor assertion coverage show lower kill rates."
          cite="Estimated — limited strong empirical citations specific to this operator." />
        <OpRow name="SDL — Statement Deletion" badge="Lower" framework="Java & JavaScript" eff={0.40}
          desc="Removes entire statements from the code. While intuitive, this operator produces many survived mutants because removing a statement often doesn't affect observable output if the statement's effect is indirect. Most useful for identifying dead code or poorly covered execution paths."
          cite="Just et al. 2014: 35–45% real fault detection — lower than expression-level operators." />

        <H>Unavailable Operators</H>
        <P style={{ color:'var(--gray-500)', fontSize:13 }}>SOR (Shift Operator Replacement), VDL (Variable Deletion), and ODL (Operator Deletion) are not available — neither PIT nor Stryker supports them in standard configuration.</P>
      </>
    ),

    budget: (
      <>
        <P>The time budget controls the maximum duration IMPT will spend executing mutants. IMPT uses this budget to determine how many mutants to select and test using its prioritization algorithm.</P>

        <H>How the Budget Works</H>
        <P>Before testing begins, IMPT enumerates all possible mutants for your project and estimates how long each will take to execute. It then selects the highest-priority mutants that fit within your budget — maximizing coverage of the most valuable mutations in the available time.</P>
        <P>A shorter budget means fewer mutants are tested, but IMPT ensures those mutants are the most likely to reveal test gaps. The <strong>time saved vs exhaustive</strong> metric on the Results page shows how much time IMPT saved compared to running all mutants.</P>

        <H>Recommended Budgets</H>
        <div style={{ display:'grid', gap:10, marginBottom:16 }}>
          {[
            { range:'5–10 min',  label:'Preliminary',   color:'#fef9c3', border:'#fde047', desc:'Quick feedback during active development. Lower coverage but very fast. Suitable for frequent CI checks on small modules.' },
            { range:'15–20 min', label:'Standard',      color:'#dbeafe', border:'#93c5fd', desc:'Recommended for most evaluation sessions. Balances speed with meaningful coverage. Good for trend monitoring and regular test quality tracking.' },
            { range:'30–60 min', label:'Thorough',      color:'#dcfce7', border:'#86efac', desc:'High-confidence results for quality gates and release validation. Recommended when using the Exhaustive Baseline for ground-truth comparison.' },
            { range:'60+ min',   label:'Comprehensive', color:'#ede9fe', border:'#c4b5fd', desc:'Mission-critical applications requiring maximum coverage. Suitable for pre-release audits or when establishing baseline metrics for a project.' },
          ].map(r => (
            <div key={r.label} style={{ background:r.color, border:`1px solid ${r.border}`, borderRadius:8, padding:'12px 16px' }}>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                <strong style={{ fontSize:14 }}>{r.label}</strong>
                <span style={{ fontSize:13, fontFamily:'monospace', fontWeight:600 }}>{r.range}</span>
              </div>
              <div style={{ fontSize:13, color:'var(--gray-700)' }}>{r.desc}</div>
            </div>
          ))}
        </div>

        <H>Exhaustive Baseline</H>
        <P>Enabling the <strong>Exhaustive Baseline</strong> runs all mutants after your prioritized strategy completes. This provides a ground-truth mutation score and true correlation figure. The exhaustive run adds additional time on top of your selected budget — the Review step estimates the total duration before you start.</P>

        <H>Time Saved Calculation</H>
        <P>Time saved is computed as: <code>(1 − primary execution time / exhaustive execution time) × 100%</code>. When the exhaustive baseline is not run, an estimate is derived from the ratio of selected mutants to total mutants.</P>
      </>
    ),

    results: (
      <>
        <P>The Results page displays a comprehensive analysis of your mutation testing session. Here is what each metric means and how to interpret it.</P>

        <H>Mutation Score</H>
        <P>The percentage of executed mutants that were detected (killed) by your test suite. Calculated as: <code>Killed Mutants ÷ Total Executed Mutants × 100</code>.</P>
        <P>A higher score means your tests are more effective at catching code changes — and by extension, real bugs. Industry benchmarks vary by context:</P>
        <P>• <strong>Research / academic projects:</strong> 60–70%<br/>• <strong>Web applications:</strong> 70–80%<br/>• <strong>Mission-critical / financial systems:</strong> 85%+</P>

        <H>Mutants Tested</H>
        <P>Shows how many mutants IMPT selected and executed out of the total generated. For example, <em>96 / 150</em> means IMPT generated 150 possible mutants, and selected 96 high-priority ones to execute within your time budget. The reduction comes from two sources: subsumption analysis (removing redundant mutants) and the knapsack-based selection algorithm.</P>

        <H>Execution Time</H>
        <P>The actual wall-clock time taken to complete the prioritized mutation run, computed from the job start and completion timestamps. This differs from the time budget — if IMPT finishes before the budget expires, execution time will be shorter.</P>

        <H>Time Saved vs Exhaustive</H>
        <P>How much time IMPT saved compared to running all mutants exhaustively. When the Exhaustive Baseline was run, this is computed from actual timestamps. When it was not run, it is estimated as: <code>(1 − selected mutants / total mutants) × exhaustive estimate</code>. Displayed in both minutes/seconds and as a percentage.</P>

        <H>Exhaustive Score</H>
        <P>The mutation score from running all mutants (Ground Truth), or a statistical estimate using the Wilson score interval when the exhaustive baseline was not run. Ground Truth values are labeled in green; estimates are labeled in amber and include confidence interval bounds.</P>

        <H>Correlation</H>
        <P>Measures how closely IMPT's prioritized results represent the full exhaustive mutation score. Computed as: <code>1 − |IMPT score − Exhaustive score| / Exhaustive score</code>. A value close to 1.0 indicates IMPT's selection is highly representative of what exhaustive testing would find. When the exhaustive baseline was not run, this is estimated from the Wilson confidence interval.</P>

        <H>Prioritized Mutants Table</H>
        <P>Lists all executed mutants sorted by IMPT priority score (highest first). Each row shows the mutation operator used, the file and line number where the mutant was introduced, the priority score (0–10), and whether the mutant was killed or survived. Survived mutants represent specific locations in your code where your tests failed to detect a change — these are actionable test gaps.</P>

        <H>Exporting Results</H>
        <P>Use the Export buttons at the bottom of the Results page to download your results in three formats:</P>
        <P>• <strong>CSV</strong> — spreadsheet-compatible, suitable for further analysis<br/>• <strong>HTML Report</strong> — styled standalone report viewable in any browser<br/>• <strong>JSON</strong> — structured data for developers or integration with other tools</P>
      </>
    ),

    faq: (
      <>
        <QA q="Why is my mutation score lower than expected?"
          a="A low mutation score means your tests don't detect many of the code changes IMPT introduced. Review the Prioritized Mutants table on the Results page — survived mutants show exactly where your test suite has gaps. Focus on writing tests that assert specific return values and conditional branches." />
        <QA q="Can I run multiple sessions at once?"
          a="Yes. Each session is dispatched as a background job. The system supports concurrent jobs — however, running many sessions simultaneously on the same server may slow individual job execution due to shared CPU and memory resources." />
        <QA q="How accurate is IMPT's score compared to exhaustive testing?"
          a="Accuracy depends on your time budget, project size, and operator selection. IMPT's correlation with exhaustive testing is measured per session and shown on the Results page. Enable the Exhaustive Baseline for a ground-truth comparison on your specific project." />
        <QA q="My project upload fails — what should I check?"
          a="Ensure your ZIP includes pom.xml or build.gradle (Java) or package.json (JavaScript) at the root level. Exclude node_modules, build/, and target/ directories to reduce file size. Maximum upload size is 50MB. Also verify that your project compiles and tests pass locally before uploading." />
        <QA q="What does a 'Survived' mutant mean?"
          a="A survived mutant means none of your existing tests caught that specific code change. This is a concrete indicator of a test gap — a real bug of that kind could go undetected by your current test suite. The Prioritized Mutants table shows the exact file, line, operator, and code change for each survived mutant." />
        <QA q="What is the difference between IMPT Intelligent Prioritization and Random Sampling?"
          a="IMPT Intelligent Prioritization uses an algorithm that scores mutants based on operator effectiveness, code complexity, and historical kill rates to select the most valuable subset. Random Sampling selects mutants randomly within the time budget. IMPT typically achieves higher mutation scores per unit of time compared to random selection." />
        <QA q="What is the Exhaustive Baseline?"
          a="The Exhaustive Baseline runs all generated mutants after your prioritized strategy completes. It produces a ground-truth mutation score and enables true correlation measurement between IMPT's prioritized results and full mutation testing. It significantly increases total run time but provides the most accurate comparison data." />
        <QA q="Why are some mutation operators not available for my project?"
          a="Operators are filtered by your selected programming language. Java-specific operators (like ABS) use PIT and are unavailable for JavaScript projects. JavaScript-specific operators (like LCR and CRP) use Stryker and are unavailable for Java projects. Operators marked as Both are available for all projects." />
      </>
    ),
  };

  return (
    <AppShell>
      <PageHeader icon="❓" title="Help & Documentation" />
      <div className="page-content">
        <div className="flex" style={{ gap:24 }}>
          <div style={{ width:200, flexShrink:0 }}>
            {sections.map(s => (
              <button key={s.id} onClick={() => setActive(s.id)}
                style={{ display:'block', width:'100%', textAlign:'left', padding:'8px 12px',
                  borderRadius:6, border:'none', cursor:'pointer', marginBottom:2,
                  background: active===s.id ? 'var(--purple-xlight)' : 'transparent',
                  color: active===s.id ? 'var(--purple-mid)' : 'var(--gray-600)',
                  fontWeight: active===s.id ? 600 : 400, fontSize:13.5 }}>
                {s.label}
              </button>
            ))}
          </div>
          <div style={{ flex:1, paddingLeft:24, borderLeft:'1px solid var(--gray-200)' }}>
            <h2 style={{ fontSize:20, fontWeight:700, marginBottom:16 }}>
              {sections.find(s => s.id === active)?.label}
            </h2>
            {content[active] || content.quickstart}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
