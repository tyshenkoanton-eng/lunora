import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Divider } from '../components/Divider'
import { OrnamentFrame } from '../components/OrnamentFrame'
import { api } from '../hooks/useApi'

interface Block {
  planet: string; planet_ru: string; sign: string; sign_ru: string
  symbol: string; house: number | null; degree: number; text: string
}

interface PortraitData {
  blocks: Block[]
  portrait: string
}

interface BottomNavProps {
  active: string
  onNav: (tab: string) => void
}

const signLabels: Record<string, string> = {
  Aries:'Овен', Taurus:'Телец', Gemini:'Близнецы', Cancer:'Рак',
  Leo:'Лев', Virgo:'Дева', Libra:'Весы', Scorpio:'Скорпион',
  Sagittarius:'Стрелец', Capricorn:'Козерог', Aquarius:'Водолей', Pisces:'Рыбы',
}

const signSymbols: Record<string, string> = {
  Aries:'♈', Taurus:'♉', Gemini:'♊', Cancer:'♋',
  Leo:'♌', Virgo:'♍', Libra:'♎', Scorpio:'♏',
  Sagittarius:'♐', Capricorn:'♑', Aquarius:'♒', Pisces:'♓',
}

const planetLabels: Record<string, string> = {
  Sun:'Солнце', Moon:'Луна', Mercury:'Меркурий', Venus:'Венера',
  Mars:'Марс', Jupiter:'Юпитер', Saturn:'Сатурн',
  Uranus:'Уран', Neptune:'Нептун', Pluto:'Плутон',
}

function BottomNav({ active, onNav }: BottomNavProps) {
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
            color: active === item.id ? 'var(--gold)' : 'var(--text3)',
            cursor: 'pointer', background: 'none', border: 'none',
            fontFamily: 'var(--font-display)',
            transition: 'color 0.2s',
          }}
        >
          <span style={{ fontSize: 20 }}>{item.icon}</span>
          {item.label}
        </button>
      ))}
    </div>
  )
}

function Shimmer() {
  return (
    <div>
      {[100, 80, 60].map((w, i) => (
        <div key={i} style={{
          width: `${w}%`, height: 16, marginBottom: 10,
          borderRadius: 8,
          background: 'linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%)',
          backgroundSize: '200% 100%',
          animation: 'shimmer 1.5s infinite',
        }} />
      ))}
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  )
}

function PlanetCard({ block, index }: { block: Block; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, ease: [0.16, 1, 0.3, 1] }}
    >
      <OrnamentFrame style={{ marginBottom: 12, padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <span style={{ fontSize: 22, width: 32, textAlign: 'center' }}>{block.symbol}</span>
          <div>
            <div style={{
              fontSize: 14, fontWeight: 500, color: 'var(--gold-light)',
              fontFamily: 'var(--font-display)',
            }}>
              {block.planet_ru} в {block.sign_ru}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 1 }}>
              {block.degree}°{block.house ? ` · ${block.house} дом` : ''}
            </div>
          </div>
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text2)' }}>
          {block.text}
        </div>
      </OrnamentFrame>
    </motion.div>
  )
}

export function PortraitScreen({
  userId,
  chartData,
  onNav,
}: {
  userId: string
  chartData: Record<string, unknown>
  onNav: (tab: string) => void
}) {
  const [portrait, setPortrait] = useState<PortraitData | null>(null)
  const [interpOpen, setInterpOpen] = useState(false)
  const [techOpen, setTechOpen] = useState(false)
  const [loadingPortrait, setLoadingPortrait] = useState(true)

  useEffect(() => {
    api<PortraitData>(`/api/portrait/${userId}`)
      .then(setPortrait)
      .catch(() => {})
      .finally(() => setLoadingPortrait(false))
  }, [userId])

  const western = chartData?.western as { planets?: Array<{ name: string; sign: string; degree_in_sign: number; house?: number }>; aspects?: Array<{ planet1: string; planet2: string; aspect_type: string; orb: number }> } | undefined
  const sunPlanet = western?.planets?.find(p => p.name === 'Sun')
  const sunSign = sunPlanet?.sign || ''
  const name = localStorage.getItem('lunora_name') || 'Звёздный странник'

  return (
    <div style={{ position: 'relative', zIndex: 1, paddingBottom: 80 }}>
      {/* Portrait header */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        style={{
          padding: '28px 20px 24px',
          background: `linear-gradient(180deg, var(--bg2) 0%, var(--bg) 100%)`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 24 }}>
          <div style={{
            width: 52, height: 52, borderRadius: '50%',
            border: '1px solid var(--gold-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 24, background: 'var(--surface)',
          }}>
            {signSymbols[sunSign] || '☽'}
          </div>
          <div>
            <div style={{
              fontSize: 20, fontWeight: 400, color: 'var(--gold-light)',
              fontFamily: 'var(--font-display)',
            }}>
              {name}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>
              {sunSign ? `Солнце в ${signLabels[sunSign] || sunSign}` : ''}
            </div>
          </div>
        </div>

        {/* Portrait text */}
        {loadingPortrait ? (
          <Shimmer />
        ) : portrait?.portrait ? (
          <div style={{ fontSize: 14, lineHeight: 1.8, color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
            {portrait.portrait.split('\n\n').filter(Boolean).map((p, i) => (
              <motion.p
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                style={{ marginBottom: 16 }}
              >
                {p}
              </motion.p>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--text2)' }}>Портрет временно недоступен</p>
        )}
      </motion.div>

      {/* Interpretations */}
      <div style={{ padding: '0 20px' }}>
        <Divider text="Интерпретации" onClick={() => setInterpOpen(!interpOpen)} open={interpOpen} />
        <AnimatePresence>
          {interpOpen && portrait?.blocks && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: 'hidden' }}
            >
              {portrait.blocks.map((b, i) => (
                <PlanetCard key={i} block={b} index={i} />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Tech data */}
      <div style={{ padding: '0 20px' }}>
        <Divider text="Расчётные данные" onClick={() => setTechOpen(!techOpen)} open={techOpen} />
        <AnimatePresence>
          {techOpen && western?.planets && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: 'hidden' }}
            >
              <OrnamentFrame style={{ marginBottom: 16, padding: 16, overflowX: 'auto' }}>
                <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {['Планета','Знак','Градус','Дом'].map(h => (
                        <th key={h} style={{
                          textAlign: 'left', padding: '8px 10px',
                          color: 'var(--gold-dim)', fontWeight: 400,
                          letterSpacing: 1, textTransform: 'uppercase',
                          borderBottom: '1px solid var(--surface3)',
                          fontFamily: 'var(--font-display)',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {western.planets.map(p => (
                      <tr key={p.name}>
                        <td style={{ padding: '8px 10px', color: 'var(--text2)', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                          {planetLabels[p.name] || p.name}
                        </td>
                        <td style={{ padding: '8px 10px', color: 'var(--text2)', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                          {signLabels[p.sign] || p.sign}
                        </td>
                        <td style={{ padding: '8px 10px', color: 'var(--text2)', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                          {p.degree_in_sign.toFixed(1)}°
                        </td>
                        <td style={{ padding: '8px 10px', color: 'var(--text2)', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                          {p.house || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </OrnamentFrame>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <BottomNav active="portrait" onNav={onNav} />
    </div>
  )
}
