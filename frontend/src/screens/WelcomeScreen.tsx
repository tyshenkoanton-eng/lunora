import { motion } from 'framer-motion'
import { ZodiacWheel } from '../components/ZodiacWheel'
import { Button } from '../components/Button'

export function WelcomeScreen({ onStart }: { onStart: () => void }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      padding: '40px 24px',
      textAlign: 'center',
      position: 'relative',
      zIndex: 1,
    }}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      >
        <ZodiacWheel size={220} />
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 36,
          fontWeight: 300,
          letterSpacing: 8,
          textTransform: 'uppercase',
          color: 'var(--gold-light)',
          marginTop: 32,
          marginBottom: 16,
        }}
      >
        Lunora
      </motion.h1>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.5 }}
        style={{
          fontSize: 14,
          color: 'var(--text2)',
          lineHeight: 1.7,
          maxWidth: 280,
          marginBottom: 48,
          fontFamily: 'var(--font-display)',
          fontWeight: 300,
          fontStyle: 'italic',
        }}
      >
        Твой персональный портрет через призму четырёх древних систем
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.7 }}
        style={{ width: '100%', maxWidth: 320 }}
      >
        <Button onClick={onStart}>Узнать себя</Button>
      </motion.div>

      {/* Decorative bottom ornament */}
      <motion.svg
        width="120"
        height="20"
        viewBox="0 0 120 20"
        style={{ marginTop: 48 }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.4 }}
        transition={{ delay: 1 }}
      >
        <line x1="0" y1="10" x2="50" y2="10" stroke="var(--gold-dim)" strokeWidth="0.5" />
        <circle cx="60" cy="10" r="3" fill="none" stroke="var(--gold-dim)" strokeWidth="0.5" />
        <circle cx="60" cy="10" r="1" fill="var(--gold-dim)" />
        <line x1="70" y1="10" x2="120" y2="10" stroke="var(--gold-dim)" strokeWidth="0.5" />
      </motion.svg>
    </div>
  )
}
