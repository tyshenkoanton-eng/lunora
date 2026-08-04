import { motion } from 'framer-motion'

const signs = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓']

export function ZodiacWheel({ size = 200 }: { size?: number }) {
  const r = size / 2
  const innerR = r * 0.62
  const signR = r * 0.82

  return (
    <motion.svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      initial={{ opacity: 0, rotate: -30 }}
      animate={{ opacity: 1, rotate: 0 }}
      transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
    >
      {/* Outer ring */}
      <circle cx={r} cy={r} r={r - 2} fill="none" stroke="var(--gold-border)" strokeWidth="1" />
      <circle cx={r} cy={r} r={r - 8} fill="none" stroke="var(--gold-border)" strokeWidth="0.5" />

      {/* Inner ring */}
      <circle cx={r} cy={r} r={innerR} fill="none" stroke="var(--gold-border)" strokeWidth="0.5" />

      {/* Divider lines */}
      {signs.map((_, i) => {
        const angle = (i * 30 - 90) * (Math.PI / 180)
        return (
          <line
            key={`line-${i}`}
            x1={r + innerR * Math.cos(angle)}
            y1={r + innerR * Math.sin(angle)}
            x2={r + (r - 8) * Math.cos(angle)}
            y2={r + (r - 8) * Math.sin(angle)}
            stroke="var(--gold-border)"
            strokeWidth="0.5"
          />
        )
      })}

      {/* Signs */}
      {signs.map((sign, i) => {
        const angle = ((i * 30) + 15 - 90) * (Math.PI / 180)
        return (
          <text
            key={sign}
            x={r + signR * Math.cos(angle)}
            y={r + signR * Math.sin(angle)}
            textAnchor="middle"
            dominantBaseline="central"
            fill="var(--gold-dim)"
            fontSize={size * 0.07}
          >
            {sign}
          </text>
        )
      })}

      {/* Center sun/moon ornament */}
      <circle cx={r} cy={r} r={innerR * 0.45} fill="none" stroke="var(--gold)" strokeWidth="0.8" />
      <text
        x={r}
        y={r}
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--gold)"
        fontSize={size * 0.15}
        style={{ filter: 'drop-shadow(0 0 8px rgba(201, 168, 76, 0.4))' }}
      >
        ☽
      </text>

      {/* Decorative dots at cardinal points */}
      {[0, 90, 180, 270].map(deg => {
        const angle = (deg - 90) * (Math.PI / 180)
        return (
          <circle
            key={deg}
            cx={r + (r - 5) * Math.cos(angle)}
            cy={r + (r - 5) * Math.sin(angle)}
            r="2"
            fill="var(--gold)"
          />
        )
      })}
    </motion.svg>
  )
}
