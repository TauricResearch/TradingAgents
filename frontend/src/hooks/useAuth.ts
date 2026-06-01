import { useState, useCallback } from 'react'
import axios from 'axios'

const TOKEN_KEY = 'ta_access'
const REFRESH_KEY = 'ta_refresh'

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function useAuth() {
  const [user, setUser] = useState<string | null>(() => {
    const t = localStorage.getItem(TOKEN_KEY)
    if (!t) return null
    try {
      return JSON.parse(atob(t.split('.')[1])).sub as string
    } catch { return null }
  })

  const login = useCallback(async (username: string, password: string) => {
    const res = await axios.post('/auth/login', { username, password })
    localStorage.setItem(TOKEN_KEY, res.data.access_token)
    localStorage.setItem(REFRESH_KEY, res.data.refresh_token)
    setUser(username)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setUser(null)
  }, [])

  return { user, login, logout, isAuthenticated: !!user }
}

// Axios interceptor: attach Bearer token automatically
axios.interceptors.request.use(cfg => {
  const token = getAccessToken()
  if (token && cfg.headers) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})
