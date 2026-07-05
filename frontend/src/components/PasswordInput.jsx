// src/components/PasswordInput.jsx
import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

/**
 * Drop-in replacement for <input type="password"> with a show/hide toggle.
 * Forwards all props (className, value, onChange, onBlur, placeholder, required, …)
 * to the underlying input, so existing form wiring keeps working unchanged.
 */
export default function PasswordInput({ style, ...props }) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <input
        {...props}
        type={show ? 'text' : 'password'}
        style={{ paddingRight: 42, ...(style || {}) }}
      />
      <button
        type="button"
        onClick={() => setShow(s => !s)}
        tabIndex={-1}
        aria-label={show ? 'Hide password' : 'Show password'}
        title={show ? 'Hide password' : 'Show password'}
        style={{
          position: 'absolute', right: 6, top: 0, bottom: 0,
          display: 'flex', alignItems: 'center',
          background: 'none', border: 'none', cursor: 'pointer',
          padding: '0 6px', color: 'var(--gray-500)', lineHeight: 1,
        }}
      >
        {show ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
