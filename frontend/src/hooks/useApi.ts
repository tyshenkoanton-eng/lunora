const BASE = ''

// Авторизация Telegram Mini App: на каждый запрос кладём подписанную initData в заголовок
// `Authorization: tma <initData>`. Сервер проверяет подпись и достаёт telegram_id — это
// единственный доверенный владелец (защита от IDOR). user_id в пути/теле больше не даёт доступ.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const initData = window.Telegram?.WebApp?.initData || ''
  const headers = new Headers(init?.headers)
  if (initData) headers.set('Authorization', `tma ${initData}`)
  const res = await fetch(BASE + path, { ...init, headers })
  const data = await res.json()
  if (!res.ok) {
    const detail = (data && data.detail) || {}
    const msg = (typeof detail === 'object' && detail.message) || detail || 'Error'
    throw new Error(typeof msg === 'string' ? msg : 'Error')
  }
  return data as T
}
