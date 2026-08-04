import { motion } from 'framer-motion'
import type { CSSProperties, ReactNode } from 'react'

export function Button({
  children,
  onClick,
  disabled,
  variant = 'primary',
  style,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  variant?: 'primary' | 'outline'
  style?: CSSProperties
}) {
  const base: CSSProperties = {
    display: 'block',
    width: '100%',
    padding: '16px 24px',
    border: 'none',
    borderRadius: 'var(--radius)',
    fontSize: 14,
    fontWeight: 600,
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.4 : 1,
    fontFamily: 'var(--font-display)',
    ...style,
  }

  const variants: Record<string, CSSProperties> = {
    primary: {
      background: 'linear-gradient(135deg, var(--gold), var(--gold-dim))',
      color: 'var(--bg)',
    },
    outline: {
      background: 'transparent',
      border: '1px solid var(--gold-border)',
      color: 'var(--gold)',
    },
  }

  return (
    <motion.button
      style={{ ...base, ...variants[variant] }}
      onClick={onClick}
      disabled={disabled}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      whileHover={disabled ? undefined : { filter: 'brightness(1.1)' }}
    >
      {children}
    </motion.button>
  )
}
