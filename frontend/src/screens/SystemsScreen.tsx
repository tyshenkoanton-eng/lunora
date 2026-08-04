import { useState } from 'react'
import { motion } from 'framer-motion'
import { OrnamentFrame } from '../components/OrnamentFrame'

const tabs = [
  { id: 'western', icon: '♈', label: 'Западная' },
  { id: 'vedic', icon: '☸', label: 'Ведическая' },
  { id: 'chinese', icon: '☯', label: 'Китайская' },
  { id: 'numerology', icon: '✡', label: 'Нумерология' },
]

function BottomNav({ onNav }: { onNav: (tab: string) => void }) {
  const items = [
    { id: 'portrait', icon: '☽', label: 'Портрет' },
    { id: 'systems', icon: '◎', label: 'Системы' },
    { id: 'chat', icon: '✦', label: 'Оракул' },
  ]

  return (
    <div style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      display: 'flex', justifyContent: 'space-around',
      padding: '12px 0 20px',
      background: 'var(--bg2)',
      borderTop: '1px solid var(--gold-border)',
      zIndex: 10,
    }}>
      {items.map(item => (
        <button
          key={item.id}
          onClick={() => onNav(item.id)}
          style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: 4, fontSize: 10, letterSpacing: 1,
            textTransform: 'uppercase',
            color: item.id === 'systems' ? 'var(--gold)' : 'var(--text3)',
            cursor: 'pointer', background: 'none', border: 'none',
            fontFamily: 'var(--font-display)',
          }}
        >
          <span style={{ fontSize: 20 }}>{item.icon}</span>
          {item.label}
        </button>
      ))}
    </div>
  )
}

export function SystemsScreen({
  chartData,
  onNav,
}: {
  chartData: Record<string, unknown>
  onNav: (tab: string) => void
}) {
  const [active, setActive] = useState('western')
  const data = (chartData as Record<string, unknown>)?.[active]

  return (
    <div style={{
      position: 'relative', zIndex: 1,
      padding: '20px 20px 80px',
    }}>
      {/* Tabs */}
      <div style={{
        display: 'flex', gap: 6,
        overflowX: 'auto',
        marginBottom: 20,
        WebkitOverflowScrolling: 'touch',
      }}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            style={{
              padding: '10px 16px',
              borderRadius: 24,
              fontSize: 12,
              letterSpacing: 0.5,
              whiteSpace: 'nowrap',
              cursor: 'pointer',
              fontFamily: 'var(--font-display)',
              transition: 'all 0.2s',
              border: active === tab.id ? '1px solid var(--gold)' : '1px solid var(--gold-border)',
              background: active === tab.id ? 'linear-gradient(135deg, var(--gold), var(--gold-dim))' : 'transparent',
              color: active === tab.id ? 'var(--bg)' : 'var(--text2)',
            }}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <motion.div
        key={active}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <OrnamentFrame style={{ overflowX: 'auto' }}>
          {data ? (
            <pre style={{
              fontSize: 12,
              lineHeight: 1.6,
              color: 'var(--text2)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {JSON.stringify(data, null, 2)}
            </pre>
          ) : (
            <p style={{ color: 'var(--text2)' }}>Нет данных</p>
          )}
        </OrnamentFrame>
      </motion.div>

      <BottomNav onNav={onNav} />
    </div>
  )
}
