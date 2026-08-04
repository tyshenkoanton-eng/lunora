const BASE = ''

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Error')
  return data as T
}
