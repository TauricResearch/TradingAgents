// Render smoke tests: mount views with the API mocked. Catches template/script
// runtime errors that `vite build` misses (build never executes render fns).
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import { h } from 'vue'
import { NMessageProvider } from 'naive-ui'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/client', () => ({
  ApiError: class extends Error { constructor(public status: number, m: string) { super(m) } },
  api: {
    get: vi.fn(async (u: string) => {
      if (u.includes('/providers')) return { doubao: { models: ['a', 'b', 'c'], key_present: true, key_env: 'ARK_API_KEY' } }
      if (u.includes('/history')) return []
      if (u.includes('/prefs')) return { tickers: ['NVDA'], telegram_chat_id: '', daily_schedule_enabled: false }
      if (u.includes('/research')) return []
      return {}
    }),
    post: vi.fn(async () => ({ ok: true, run_id: 'r1' })),
    put: vi.fn(async () => ({})),
    del: vi.fn(async () => ({})),
    upload: vi.fn(async () => ({})),
  },
}))
vi.mock('../src/api/sse', () => ({ subscribeRun: () => () => {} }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: {} }, missingWarn: false, fallbackWarn: false })
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { render: () => null } }] })

async function renderInProvider(view: any) {
  const wrapper = mount(NMessageProvider, {
    global: { plugins: [createPinia(), i18n, router] },
    slots: { default: () => h(view) },
  })
  await new Promise((r) => setTimeout(r, 0)) // let onMounted async settle
  return wrapper
}

describe('view render smoke tests', () => {
  it('App shell renders the left sidebar nav', async () => {
    const { default: App } = await import('../src/App.vue')
    const w = mount(App, { global: { plugins: [createPinia(), i18n, router] } })
    await new Promise((r) => setTimeout(r, 0))
    // Sidebar menu items present (analysis/history/settings keys render).
    expect(w.html()).toContain('analysis')
  })

  it('LoginView renders the email input', async () => {
    const { default: LoginView } = await import('../src/views/LoginView.vue')
    const w = await renderInProvider(LoginView)
    expect(w.find('input').exists()).toBe(true)
  })

  it('AnalysisView mounts and loads providers without throwing', async () => {
    const { default: AnalysisView } = await import('../src/views/AnalysisView.vue')
    const w = await renderInProvider(AnalysisView)
    expect(w.html().length).toBeGreaterThan(0)
  })

  it('SettingsView mounts and loads prefs without throwing', async () => {
    const { default: SettingsView } = await import('../src/views/SettingsView.vue')
    const w = await renderInProvider(SettingsView)
    expect(w.html().length).toBeGreaterThan(0)
  })
})
