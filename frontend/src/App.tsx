import { useState, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { StarField } from './components/StarField'
import { WelcomeScreen } from './screens/WelcomeScreen'
import { OnboardScreen } from './screens/OnboardScreen'
import { PortraitScreen } from './screens/PortraitScreen'
import { SystemsScreen } from './screens/SystemsScreen'
import { ChatScreen } from './screens/ChatScreen'
import { api } from './hooks/useApi'

type Screen = 'welcome' | 'onboard' | 'portrait' | 'systems' | 'chat'

export default function App() {
  const [screen, setScreen] = useState<Screen>('welcome')
  const [userId, setUserId] = useState<string | null>(localStorage.getItem('lunora_user_id'))
  const [chartData, setChartData] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (tg) { tg.ready(); tg.expand() }
  }, [])

  useEffect(() => {
    if (!userId) return
    api<Record<string, unknown>>(`/api/chart/${userId}`)
      .then(data => {
        setChartData(data)
        setScreen('portrait')
      })
      .catch(() => {
        localStorage.removeItem('lunora_user_id')
        setUserId(null)
        setScreen('welcome')
      })
  }, [userId])

  const handleOnboardComplete = (data: { user_id: string; chart: Record<string, unknown> }) => {
    setUserId(data.user_id)
    setChartData(data.chart)
    setScreen('portrait')
  }

  const handleNav = (tab: string) => {
    setScreen(tab as Screen)
  }

  return (
    <>
      <StarField />
      <AnimatePresence mode="wait">
        <motion.div
          key={screen}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          {screen === 'welcome' && (
            <WelcomeScreen onStart={() => setScreen('onboard')} />
          )}
          {screen === 'onboard' && (
            <OnboardScreen onComplete={handleOnboardComplete} />
          )}
          {screen === 'portrait' && userId && chartData && (
            <PortraitScreen userId={userId} chartData={chartData} onNav={handleNav} />
          )}
          {screen === 'systems' && chartData && (
            <SystemsScreen chartData={chartData} onNav={handleNav} />
          )}
          {screen === 'chat' && userId && (
            <ChatScreen userId={userId} />
          )}
        </motion.div>
      </AnimatePresence>
    </>
  )
}
