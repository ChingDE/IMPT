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
  const content = {
    quickstart: {
      title: 'Quick Start Guide',
      body: `Welcome to IMPT — Intelligent Mutation Prioritization Tool. Here's how to run your first mutation test in 5 steps:

1. Create a New Session — Click "New Test Session" from the dashboard. Give your session a name and select your programming language.

2. Upload Your Project — Upload a .zip file of your project. IMPT will automatically detect your build system (Maven/Gradle for Java, npm for JavaScript).

3. Configure Operators — Select which mutation operators to use. The default selection of high-effectiveness operators is recommended for most projects.

4. Set Time Budget — Choose how long IMPT should spend testing (5–120 minutes). A 20-minute budget achieves 75–85% time savings with ≥0.95 correlation.

5. Review & Start — Review your configuration and click "Start Mutation Testing". The test runs in the background — you'll be notified when complete.`,
    },
    operators: {
      title: 'Mutation Operators',
      body: `Mutation operators introduce small, systematic changes to your code to verify that your tests can detect them.

AOR (Arithmetic Operator Replacement): Replaces +, -, *, / with each other. 92% effectiveness.
ROR (Relational Operator Replacement): Changes <, >, ==, != comparisons. 88% effectiveness.
COR (Conditional Operator Replacement): Alters boolean conditions. 85% effectiveness.
SOR (Shift Operator Replacement): Replaces bitwise shift operators. 76% effectiveness.
LCR (Logical Connector Replacement): Swaps && and ||. 71% effectiveness.
UOI (Unary Operator Insertion): Adds/removes negation. 85% effectiveness.
SDL (Statement Deletion): Removes statements entirely. 75% effectiveness.
CRP (Constant Replacement): Replaces constants with different values. 65% effectiveness.

High-effectiveness operators (≥85%) are selected by default.`,
    },
    faq: {
      title: 'Frequently Asked Questions',
      body: `Q: Why is my mutation score lower than expected?
A: A low mutation score means your tests don't detect many code changes. Review the survived mutants on the Results page to identify test gaps.

Q: Can I run multiple sessions at once?
A: Yes. Each session runs as a background job. The system queues them and processes one at a time.

Q: How accurate is IMPT's score compared to exhaustive testing?
A: IMPT achieves ≥0.95 correlation with exhaustive testing at a 20-minute budget, meaning results are within ±2% of the full mutation score.

Q: My project upload fails — what should I check?
A: Ensure your ZIP includes pom.xml or build.gradle (Java) or package.json (JavaScript) at the root level. Maximum file size is 50MB.`,
    },
  };

  const current = content[active] || content.quickstart;

  return (
    <AppShell>
      <PageHeader icon="❓" title="Help & Documentation" />
      <div className="page-content">
        <div className="flex" style={{gap:24}}>
          <div style={{width:200,flexShrink:0}}>
            {sections.map(s=>(
              <button key={s.id} onClick={()=>setActive(s.id)}
                style={{display:'block',width:'100%',textAlign:'left',padding:'8px 12px',borderRadius:6,border:'none',cursor:'pointer',
                  background:active===s.id?'var(--purple-xlight)':'transparent',
                  color:active===s.id?'var(--purple-mid)':'var(--gray-600)',
                  fontWeight:active===s.id?600:400,fontSize:13.5,marginBottom:2}}>
                {s.label}
              </button>
            ))}
          </div>
          <div style={{flex:1,paddingLeft:24,borderLeft:'1px solid var(--gray-200)'}}>
            <h2 style={{fontSize:20,fontWeight:700,marginBottom:16}}>{current.title}</h2>
            {current.body.split('\n\n').map((para,i)=>(
              <p key={i} style={{fontSize:13.5,color:'var(--gray-600)',lineHeight:1.7,marginBottom:14}}>
                {para.split('\n').map((line,j)=><span key={j}>{line}<br/></span>)}
              </p>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
