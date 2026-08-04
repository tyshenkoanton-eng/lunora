import type { CSSProperties } from 'react'

export function Divider({ text, onClick, open }: { text: string; onClick?: () => void; open?: boolean }) {
  const line: CSSProperties = {
    flex: 1,
    height: 1,
    background: 'linear-gradient(90deg, transparent, var(--gold-border), transparent)',
  }

  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '20px 0 12px',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div style={line} />
      <span style={{
        fontSize: 11,
        letterSpacing: 2.5,
        textTransform: 'uppercase',
        color: 'var(--gold-dim)',
        whiteSpace: 'nowrap',
        fontFamily: 'var(--font-display)',
        fontWeight: 500,
      }}>
        {text}
      </span>
      {onClick && (
        <span style={{
          fontSize: 9,
          color: 'var(--gold-dim)',
          transition: 'transform 0.3s var(--ease-out)',
          transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
        }}>▼</span>
      )}
      <div style={line} />
    </div>
  )
}
