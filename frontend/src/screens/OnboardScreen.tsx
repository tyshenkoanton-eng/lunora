import { useState, useRef, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { OrnamentFrame } from '../components/OrnamentFrame'
import { Button } from '../components/Button'
import { FormField, Input, Select } from '../components/FormField'
import { ZodiacWheel } from '../components/ZodiacWheel'
import { api } from '../hooks/useApi'

const months = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']

interface OnboardResult {
  user_id: string
  chart: Record<string, unknown>
}

export function OnboardScreen({ onComplete }: { onComplete: (data: OnboardResult) => void }) {
  const [name, setName] = useState('')
  const [day, setDay] = useState('')
  const [month, setMonth] = useState('')
  const [year, setYear] = useState('')
  const [hour, setHour] = useState('')
  const [minute, setMinute] = useState('')
  const [precision, setPrecision] = useState('unknown')
  const [city, setCity] = useState('')
  const [lat, setLat] = useState<number | null>(null)
  const [lon, setLon] = useState<number | null>(null)
  const [tz, setTz] = useState('')
  const [suggestions, setSuggestions] = useState<Array<{ name: string; lat: number; lon: number; timezone: string }>>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null)

  const searchCity = useCallback((q: string) => {
    setCity(q)
    setLat(null)
    setLon(null)
    setTz('')
    if (timerRef.current) clearTimeout(timerRef.current)
    if (q.trim().length < 2) { setSuggestions([]); return }
    timerRef.current = setTimeout(async () => {
      try {
        const items = await api<Array<{ name: string; lat: number; lon: number; timezone: string }>>(`/api/geocode?q=${encodeURIComponent(q)}`)
        setSuggestions(items)
      } catch { setSuggestions([]) }
    }, 400)
  }, [])

  const pickCity = (item: { name: string; lat: number; lon: number; timezone: string }) => {
    setCity(item.name)
    setLat(item.lat)
    setLon(item.lon)
    setTz(item.timezone)
    setSuggestions([])
  }

  const submit = async () => {
    if (!name || !day || !month || !year || !lat) {
      setError('Заполни все поля')
      return
    }
    setLoading(true)
    setError('')

    const tg = window.Telegram?.WebApp
    const body = {
      telegram_id: tg?.initDataUnsafe?.user?.id || Date.now(),
      name,
      birth_date: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
      birth_time: hour !== '' ? `${String(hour).padStart(2, '0')}:${String(minute || '0').padStart(2, '0')}` : null,
      birth_time_precision: precision,
      birth_city: city,
      birth_lat: lat,
      birth_lon: lon,
      timezone: tz,
      init_data: tg?.initData || '',
    }

    try {
      const data = await api<OnboardResult>('/api/onboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      localStorage.setItem('lunora_user_id', data.user_id)
      localStorage.setItem('lunora_name', name)
      onComplete(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка')
      setLoading(false)
    }
  }

  const selectStyle = { flex: 1, minWidth: 0 }

  return (
    <div style={{
      minHeight: '100vh',
      position: 'relative',
      zIndex: 1,
      padding: '20px 20px 40px',
    }}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        style={{ textAlign: 'center', marginBottom: 24 }}
      >
        <ZodiacWheel size={120} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.15 }}
        style={{ textAlign: 'center', marginBottom: 28 }}
      >
        <h2 style={{
          fontFamily: 'var(--font-display)',
          fontSize: 22,
          fontWeight: 400,
          color: 'var(--gold-light)',
          letterSpacing: 3,
          textTransform: 'uppercase',
        }}>
          Данные рождения
        </h2>
        <p style={{
          fontFamily: 'var(--font-display)',
          fontSize: 13,
          color: 'var(--text2)',
          marginTop: 8,
          fontStyle: 'italic',
        }}>
          Чем точнее данные, тем глубже портрет
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
      >
        <OrnamentFrame>
          <FormField label="Твоё имя">
            <Input
              placeholder="Как к тебе обращаться"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </FormField>

          <FormField label="Дата рождения">
            <div style={{ display: 'flex', gap: 8 }}>
              <Select style={selectStyle} value={day} onChange={e => setDay(e.target.value)}>
                <option value="">День</option>
                {Array.from({ length: 31 }, (_, i) => (
                  <option key={i + 1} value={i + 1}>{i + 1}</option>
                ))}
              </Select>
              <Select style={selectStyle} value={month} onChange={e => setMonth(e.target.value)}>
                <option value="">Месяц</option>
                {months.map((m, i) => (
                  <option key={i} value={i + 1}>{m}</option>
                ))}
              </Select>
              <Select style={selectStyle} value={year} onChange={e => setYear(e.target.value)}>
                <option value="">Год</option>
                {Array.from({ length: new Date().getFullYear() - 1929 }, (_, i) => {
                  const y = new Date().getFullYear() - i
                  return <option key={y} value={y}>{y}</option>
                })}
              </Select>
            </div>
          </FormField>

          <FormField label="Время рождения">
            <div style={{ display: 'flex', gap: 8 }}>
              <Select style={selectStyle} value={hour} onChange={e => setHour(e.target.value)}>
                <option value="">Час</option>
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>{String(i).padStart(2, '0')}</option>
                ))}
              </Select>
              <Select style={selectStyle} value={minute} onChange={e => setMinute(e.target.value)}>
                <option value="">Мин</option>
                {Array.from({ length: 12 }, (_, i) => {
                  const v = i * 5
                  return <option key={v} value={v}>{String(v).padStart(2, '0')}</option>
                })}
              </Select>
            </div>
          </FormField>

          <FormField label="Точность времени">
            <Select value={precision} onChange={e => setPrecision(e.target.value)}>
              <option value="exact">Точное</option>
              <option value="approximate_30">±30 минут</option>
              <option value="approximate_60">±1 час</option>
              <option value="approximate">Примерно</option>
              <option value="unknown">Не знаю</option>
            </Select>
          </FormField>

          <FormField label="Город рождения">
            <div style={{ position: 'relative' }}>
              <Input
                placeholder="Начни вводить город..."
                value={city}
                onChange={e => searchCity(e.target.value)}
                autoComplete="off"
              />
              <AnimatePresence>
                {suggestions.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    style={{
                      position: 'absolute',
                      left: 0, right: 0, top: '100%',
                      background: 'var(--surface2)',
                      border: '1px solid var(--gold-border)',
                      borderRadius: '0 0 var(--radius-sm) var(--radius-sm)',
                      zIndex: 10,
                      maxHeight: 200,
                      overflowY: 'auto',
                    }}
                  >
                    {suggestions.map((s, i) => (
                      <div
                        key={i}
                        onClick={() => pickCity(s)}
                        style={{
                          padding: '12px 16px',
                          cursor: 'pointer',
                          fontSize: 14,
                          color: 'var(--text)',
                          borderBottom: '1px solid var(--surface3)',
                        }}
                      >
                        {s.name}
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </FormField>

          {error && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ color: '#c44', fontSize: 13, textAlign: 'center', marginBottom: 12 }}
            >
              {error}
            </motion.p>
          )}

          <Button onClick={submit} disabled={loading} style={{ marginTop: 8 }}>
            {loading ? 'Строим карту...' : 'Построить карту'}
          </Button>
        </OrnamentFrame>
      </motion.div>
    </div>
  )
}
