import { useMemo } from 'react'

export function StarField({ count = 80 }: { count?: number }) {
  const stars = useMemo(() =>
    Array.from({ length: count }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() > 0.7 ? 3 : 2,
      delay: Math.random() * 4,
      duration: 2.5 + Math.random() * 3,
    })),
    [count]
  )

  return (
    <div style={{
      position: 'fixed', inset: 0,
      pointerEvents: 'none', zIndex: 0, overflow: 'hidden',
    }}>
      {stars.map(s => (
        <div
          key={s.id}
          style={{
            position: 'absolute',
            left: `${s.x}%`,
            top: `${s.y}%`,
            width: s.size,
            height: s.size,
            background: 'var(--gold-dim)',
            borderRadius: '50%',
            animation: `twinkle ${s.duration}s ease-in-out ${s.delay}s infinite alternate`,
          }}
        />
      ))}
      <style>{`
        @keyframes twinkle {
          0% { opacity: 0.15; transform: scale(1); }
          100% { opacity: 0.7; transform: scale(1.5); }
        }
      `}</style>
    </div>
  )
}
