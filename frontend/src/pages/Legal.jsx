// src/pages/Legal.jsx — Privacy Policy and Terms of Service (NFR072-073)
import { useNavigate } from 'react-router-dom';

const Wrap = ({ title, children }) => {
  const nav = useNavigate();
  return (
    <div style={{ minHeight:'100vh', background:'var(--gray-50)', padding:'40px 20px' }}>
      <div style={{ maxWidth:800, margin:'0 auto', background:'#fff', borderRadius:12,
        padding:'40px 48px', boxShadow:'0 2px 16px rgba(0,0,0,.06)' }}>
        <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:32,
          paddingBottom:20, borderBottom:'1px solid var(--gray-200)' }}>
          <img src="/logo.png" alt="IMPT" style={{ width:36, height:36, objectFit:'contain' }} />
          <div>
            <div style={{ fontSize:22, fontWeight:800, color:'var(--purple-mid)' }}>IMPT</div>
            <div style={{ fontSize:12, color:'var(--gray-400)' }}>NovaSoft · FEU Institute of Technology</div>
          </div>
        </div>
        <h1 style={{ fontSize:26, fontWeight:800, marginBottom:8, color:'var(--gray-900)' }}>{title}</h1>
        <p style={{ fontSize:13, color:'var(--gray-400)', marginBottom:32 }}>
          Last updated: May 2026 · Effective date: May 2026
        </p>
        {children}
        <div style={{ marginTop:40, paddingTop:20, borderTop:'1px solid var(--gray-200)',
          display:'flex', gap:16 }}>
          <button className="btn btn-secondary btn-sm" onClick={()=>nav(-1)}>← Go Back</button>
          <button className="btn btn-secondary btn-sm" onClick={()=>nav('/login')}>Login</button>
        </div>
      </div>
    </div>
  );
};

const H = ({children}) => <h2 style={{fontSize:16,fontWeight:700,marginTop:28,marginBottom:8,color:'var(--gray-800)'}}>{children}</h2>;
const P = ({children}) => <p style={{fontSize:14,color:'var(--gray-600)',lineHeight:1.75,marginBottom:12}}>{children}</p>;
const Li = ({children}) => <li style={{fontSize:14,color:'var(--gray-600)',lineHeight:1.75,marginBottom:4}}>{children}</li>;

export function PrivacyPolicy() {
  return (
    <Wrap title="Privacy Policy">
      <P>This Privacy Policy describes how IMPT (Intelligent Mutation Prioritization Tool), developed by NovaSoft at FEU Institute of Technology, collects, uses, and protects your personal information in accordance with the Republic Act No. 10173, also known as the Data Privacy Act of 2012 of the Philippines.</P>

      <H>1. Data We Collect</H>
      <P>We collect the following information when you register and use IMPT:</P>
      <ul style={{paddingLeft:20,marginBottom:12}}>
        <Li>Registration data: first name, last name, email address, organization name (optional)</Li>
        <Li>Account credentials: password (stored as a one-way bcrypt hash — never in plain text)</Li>
        <Li>Usage data: test session configurations, uploaded project files (temporary), mutation testing results</Li>
        <Li>Technical data: IP address (for security logging), browser type, access timestamps</Li>
      </ul>
      <P>We do not collect payment information, government ID numbers, or sensitive personal information beyond what is listed above.</P>

      <H>2. Purpose of Collection</H>
      <P>Your data is collected solely for the following purposes:</P>
      <ul style={{paddingLeft:20,marginBottom:12}}>
        <Li>Providing access to the IMPT mutation testing service</Li>
        <Li>Conducting academic research on mutation testing practices in the Philippine IT-BPO industry (A.Y. 2025–2026 thesis)</Li>
        <Li>Ensuring system security and preventing unauthorized access</Li>
        <Li>Improving the system based on aggregated, anonymized usage patterns</Li>
      </ul>

      <H>3. Research Data and Anonymization</H>
      <P>For research purposes, evaluation data is pseudonymized using coded identifiers (e.g., P001, P002) that are stored separately from your personal information. Your name and email are never included in research analysis or publications. Only aggregated statistics are reported.</P>

      <H>4. Data Storage and Security</H>
      <P>Your data is stored on a DigitalOcean managed PostgreSQL database hosted in Singapore. We implement the following security measures:</P>
      <ul style={{paddingLeft:20,marginBottom:12}}>
        <Li>All connections use HTTPS/TLS 1.2+ encryption</Li>
        <Li>Passwords are hashed using bcrypt with a work factor of 12</Li>
        <Li>Uploaded project files are stored in isolated, session-specific directories and deleted after 90 days</Li>
        <Li>Access tokens expire after 30 minutes of inactivity</Li>
        <Li>All security-relevant events are logged with timestamps and IP addresses</Li>
      </ul>

      <H>5. Data Sharing</H>
      <P>We do not share, sell, rent, or transfer your personal data to any third party. Your data is used exclusively for the operation of IMPT and the NovaSoft thesis research at FEU Institute of Technology. Data may be disclosed only if required by Philippine law or a valid court order.</P>

      <H>6. Data Retention</H>
      <P>In accordance with the Data Privacy Act of 2012, personal data is retained for a maximum of five (5) years from the date of collection or until you request deletion, whichever comes first. Uploaded project files are automatically deleted after 90 days. Research publications derived from your anonymized data may be retained indefinitely.</P>

      <H>7. Your Rights</H>
      <P>Under RA 10173, you have the right to:</P>
      <ul style={{paddingLeft:20,marginBottom:12}}>
        <Li><strong>Access</strong> — request a copy of your personal data held by us</Li>
        <Li><strong>Correction</strong> — update your profile information at any time via your account settings</Li>
        <Li><strong>Deletion ("Right to be Forgotten")</strong> — permanently delete your account and all associated data via Settings → Delete Account</Li>
        <Li><strong>Object</strong> — withdraw consent for research use of your data by contacting us below</Li>
        <Li><strong>Portability</strong> — request your data in a machine-readable format</Li>
      </ul>

      <H>8. Cookies</H>
      <P>IMPT does not use advertising or tracking cookies. We use only technically necessary authentication tokens (JWTs stored in memory) to maintain your login session. No third-party analytics or advertising scripts are loaded.</P>

      <H>9. Contact</H>
      <P>For privacy-related inquiries, data access requests, or complaints, contact the NovaSoft research team at FEU Institute of Technology, Nicanor Reyes St., Sampaloc, Manila, Philippines. Adviser: Dr. Angelo C. Arguson.</P>

      <H>10. Changes to This Policy</H>
      <P>We may update this Privacy Policy to reflect changes in the system or applicable law. Significant changes will be communicated via a notice on the login page. Continued use of IMPT after changes constitutes acceptance of the updated policy.</P>
    </Wrap>
  );
}

export function TermsOfService() {
  return (
    <Wrap title="Terms of Service">
      <P>By registering for and using IMPT (Intelligent Mutation Prioritization Tool), you agree to the following terms and conditions. Please read them carefully. If you do not agree, do not use the system.</P>

      <H>1. Acceptance of Terms</H>
      <P>These Terms of Service constitute a legally binding agreement between you and NovaSoft / FEU Institute of Technology governing your use of IMPT. Use of this system also constitutes consent to the data processing practices described in our Privacy Policy.</P>

      <H>2. Permitted Use</H>
      <P>IMPT is provided exclusively for:</P>
      <ul style={{paddingLeft:20,marginBottom:12}}>
        <Li>Academic research and evaluation as part of the NovaSoft thesis project (A.Y. 2025–2026)</Li>
        <Li>Software quality assessment and mutation testing of legitimate software projects</Li>
        <Li>Educational exploration of mutation testing concepts</Li>
      </ul>

      <H>3. Prohibited Use</H>
      <P>You agree not to use IMPT to:</P>
      <ul style={{paddingLeft:20,marginBottom:12}}>
        <Li>Upload malicious code, malware, exploits, or any software designed to cause harm</Li>
        <Li>Attempt to circumvent authentication, authorization, or rate limiting mechanisms</Li>
        <Li>Conduct denial-of-service attacks or deliberately overload the system</Li>
        <Li>Access, modify, or delete data belonging to other users</Li>
        <Li>Upload projects containing personally identifiable information of third parties without consent</Li>
        <Li>Use the system for commercial purposes without explicit written permission</Li>
      </ul>

      <H>4. Account Responsibilities</H>
      <P>You are responsible for maintaining the confidentiality of your account credentials. You agree to notify us immediately of any unauthorized access to your account. You are responsible for all activity that occurs under your account.</P>

      <H>5. Uploaded Content</H>
      <P>You retain ownership of all code and files you upload. By uploading to IMPT, you grant NovaSoft a limited license to process your files for the purpose of performing mutation testing. Project files are automatically deleted after 90 days. We do not inspect, share, or reproduce your uploaded code beyond what is necessary to run the mutation testing pipeline.</P>

      <H>6. Research Participation</H>
      <P>Your use of IMPT during the evaluation period (May 2026) constitutes voluntary participation in academic research. Aggregated, anonymized results may be included in thesis publications, academic papers, or conference presentations. You may withdraw from research participation at any time by deleting your account.</P>

      <H>7. System Availability</H>
      <P>IMPT is provided on a best-effort basis for the duration of the evaluation period. We target 95% uptime but do not guarantee uninterrupted availability. Long-running mutation testing jobs are executed as background processes and will continue even if you lose your connection.</P>

      <H>8. Limitation of Liability</H>
      <P>IMPT is an academic prototype system. NovaSoft and FEU Institute of Technology provide the system "as is" without warranties of any kind. We are not liable for any loss, damage, or missed deadlines resulting from system unavailability, incorrect results, or data loss. Do not use IMPT as the sole quality gate for production software releases.</P>

      <H>9. Account Termination</H>
      <P>We reserve the right to suspend or terminate accounts that violate these terms, abuse system resources, or engage in prohibited activities. You may delete your account at any time via Settings → Delete Account.</P>

      <H>10. Governing Law</H>
      <P>These Terms are governed by the laws of the Republic of the Philippines. Any disputes shall be subject to the jurisdiction of Philippine courts.</P>

      <H>11. Contact</H>
      <P>Questions about these Terms should be directed to the NovaSoft team at FEU Institute of Technology, Nicanor Reyes St., Sampaloc, Manila.</P>
    </Wrap>
  );
}

// NFR085 — Maintenance mode page
export function MaintenancePage() {
  return (
    <div style={{ minHeight:'100vh', background:'var(--purple-mid)', display:'grid', placeItems:'center', padding:20 }}>
      <div style={{ textAlign:'center', color:'#fff' }}>
        <img src="/logo.png" alt="IMPT" style={{ width:64, height:64, objectFit:'contain', marginBottom:24, opacity:.9 }} />
        <h1 style={{ fontSize:32, fontWeight:800, marginBottom:12 }}>Under Maintenance</h1>
        <p style={{ fontSize:16, opacity:.85, maxWidth:420, margin:'0 auto 24px', lineHeight:1.65 }}>
          IMPT is temporarily unavailable for scheduled maintenance. We'll be back shortly.
        </p>
        <div style={{ background:'rgba(255,255,255,.12)', borderRadius:10, padding:'16px 24px',
          display:'inline-block', fontSize:14, opacity:.9 }}>
          If you need urgent assistance, contact the NovaSoft team at FEU Institute of Technology.
        </div>
      </div>
    </div>
  );
}
