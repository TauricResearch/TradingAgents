import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'

export type Prefs = {
  daily_schedule_enabled: boolean
  tickers: string[]
  telegram_chat_id: string
  selected_analysts: string[]
  provider: string
  deep_model: string
  quick_model: string
  output_language: string
  max_debate_rounds: number
  max_risk_discuss_rounds: number
}

export const usePrefsStore = defineStore('prefs', () => {
  const prefs = ref<Prefs | null>(null)

  async function load() {
    prefs.value = await api.get<Prefs>('/api/prefs')
    return prefs.value
  }

  async function save(p: Prefs) {
    prefs.value = await api.put<Prefs>('/api/prefs', p)
    return prefs.value
  }

  return { prefs, load, save }
})
