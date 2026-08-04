import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { api } from '../hooks/useApi'

interface Message {
  role: 'user' | 'assistant'
  text: string
}

export function ChatScreen({ userId }: { userId: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: q }])
    setLoading(true)

    try {
      const data = await api<{ thread_id: string; answer: string }>('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, thread_id: threadId, question: q }),
      })
      setThreadId(data.thread_id)
      setMessages(prev => [...prev, { role: 'assistant', text: data.answer }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', text: `Ошибка: ${e instanceof Error ? e.message : 'Unknown'}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      minHeight: '100vh', position: 'relative', zIndex: 1,
    }}>
      {/* Messages */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10, padding: '20px 20px 80px' }}>
        {messages.length === 0 && (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            color: 'var(--text3)', textAlign: 'center', padding: 40,
          }}>
            <span style={{ fontSize: 40, marginBottom: 16 }}>✦</span>
            <p style={{
              fontFamily: 'var(--font-display)',
              fontSize: 16,
              fontStyle: 'italic',
              color: 'var(--text2)',
            }}>
              Задай вопрос о своей карте...
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              maxWidth: '85%',
              padding: '12px 16px',
              borderRadius: 18,
              fontSize: 14,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              ...(msg.role === 'user' ? {
                background: 'linear-gradient(135deg, var(--gold), var(--gold-dim))',
                color: 'var(--bg)',
                borderBottomRightRadius: 4,
              } : {
                background: 'var(--surface)',
                border: '1px solid var(--gold-border)',
                borderBottomLeftRadius: 4,
                color: 'var(--text)',
              }),
            }}
          >
            {msg.text}
          </motion.div>
        ))}

        {loading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{
              alignSelf: 'flex-start',
              padding: '12px 16px',
              borderRadius: 18,
              background: 'var(--surface)',
              border: '1px solid var(--gold-border)',
              borderBottomLeftRadius: 4,
            }}
          >
            <div style={{
              width: 20, height: 20,
              border: '2px solid var(--surface3)',
              borderTopColor: 'var(--gold)',
              borderRadius: '50%',
              animation: 'spin 0.6s linear infinite',
            }} />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0,
        display: 'flex', gap: 8, padding: '12px 16px',
        background: 'var(--bg)',
        borderTop: '1px solid var(--gold-border)',
        zIndex: 10,
      }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Спроси о своей карте..."
          style={{
            flex: 1,
            padding: '14px 16px',
            background: 'var(--surface2)',
            border: '1px solid var(--gold-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--text)',
            fontSize: 15,
            outline: 'none',
          }}
        />
        <button
          onClick={send}
          style={{
            padding: '14px 18px',
            background: 'linear-gradient(135deg, var(--gold), var(--gold-dim))',
            color: 'var(--bg)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: 16,
            cursor: 'pointer',
          }}
        >
          →
        </button>
      </div>
    </div>
  )
}
