import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError } from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const email = ref<string | null>(null)

  async function fetchMe(): Promise<boolean> {
    try {
      const me = await api.get<{ email: string }>('/api/auth/me')
      email.value = me.email
      return true
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) email.value = null
      return false
    }
  }

  async function requestOtp(addr: string) {
    return api.post<{ ok: boolean; message: string }>('/api/auth/request-otp', { email: addr })
  }

  async function verifyOtp(addr: string, code: string) {
    const me = await api.post<{ email: string }>('/api/auth/verify-otp', { email: addr, code })
    email.value = me.email
  }

  async function logout() {
    await api.post('/api/auth/logout')
    email.value = null
  }

  return { email, fetchMe, requestOtp, verifyOtp, logout }
})
