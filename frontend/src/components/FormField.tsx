import type { CSSProperties, ReactNode } from 'react'

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: 11,
  letterSpacing: 2,
  textTransform: 'uppercase',
  color: 'var(--gold-dim)',
  marginBottom: 8,
  fontFamily: 'var(--font-display)',
  fontWeight: 500,
}

const inputStyle: CSSProperties = {
  width: '100%',
  padding: '14px 16px',
  background: 'var(--surface2)',
  border: '1px solid var(--gold-border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text)',
  fontSize: 15,
  outline: 'none',
  transition: 'border-color 0.2s',
}

export function FormField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  )
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} style={{ ...inputStyle, ...props.style }} />
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      style={{
        ...inputStyle,
        WebkitAppearance: 'none',
        appearance: 'none',
        ...props.style,
      }}
    />
  )
}
