import type { CSSProperties, ReactNode } from 'react'

const cornerSize = 20
const stroke = 'var(--gold-border)'

function Corner({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) {
  const flip: CSSProperties = {
    position: 'absolute',
    width: cornerSize,
    height: cornerSize,
    ...(position.includes('t') ? { top: 0 } : { bottom: 0 }),
    ...(position.includes('l') ? { left: 0 } : { right: 0 }),
  }

  const scaleX = position.includes('r') ? -1 : 1
  const scaleY = position.includes('b') ? -1 : 1

  return (
    <svg style={{ ...flip, transform: `scale(${scaleX}, ${scaleY})` }} viewBox="0 0 20 20" fill="none">
      <path d="M0 0 L20 0" stroke={stroke} strokeWidth="1" />
      <path d="M0 0 L0 20" stroke={stroke} strokeWidth="1" />
      <circle cx="0" cy="0" r="2.5" fill={stroke} />
    </svg>
  )
}

export function OrnamentFrame({
  children,
  className,
  style,
}: {
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  return (
    <div
      className={className}
      style={{
        position: 'relative',
        border: `1px solid var(--gold-border)`,
        borderRadius: 'var(--radius)',
        padding: 24,
        background: 'var(--surface)',
        ...style,
      }}
    >
      <Corner position="tl" />
      <Corner position="tr" />
      <Corner position="bl" />
      <Corner position="br" />
      {children}
    </div>
  )
}
