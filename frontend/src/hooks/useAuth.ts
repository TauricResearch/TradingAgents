import { useState, useCallback } from 'react'
import axios from 'axios'
import { notify } from '../utils/notify'

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

// Axios interceptor: auto-refresh on 401
let _refreshing = false
let _queue: Array<(token: string) => void> = []

axios.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    const status: number | undefined = err.response?.status

    // Show toast for 5xx server errors (skip 401 — handled by refresh logic below)
    if (status && status >= 500) {
      const detail = err.response?.data?.detail || err.message || 'Sunucu hatası'
      notify('error', detail, `HTTP ${status}`)
    }

    if (status !== 401 || original._retried) {
      return Promise.reject(err)
    }
    original._retried = true

    if (_refreshing) {
      return new Promise(resolve => {
        _queue.push((token: string) => {
          original.headers.Authorization = `Bearer ${token}`
          resolve(axios(original))
        })
      })
    }

    _refreshing = true
    try {
      const refreshToken = localStorage.getItem(REFRESH_KEY)
      if (!refreshToken) throw new Error('No refresh token')
      const res = await axios.post('/auth/refresh', { refresh_token: refreshToken })
      const newToken: string = res.data.access_token
      localStorage.setItem(TOKEN_KEY, newToken)
      _queue.forEach(cb => cb(newToken))
      _queue = []
      original.headers.Authorization = `Bearer ${newToken}`
      return axios(original)
    } catch {
      _queue = []
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
      window.location.href = '/login'
      return Promise.reject(err)
    } finally {
      _refreshing = false
    }
  }
)
