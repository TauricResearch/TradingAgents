<script setup lang="ts">
import { h, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NDataTable, NTag, NButton, NEmpty, NSpace, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { api, ApiError } from '../api/client'
import { useAnalysisStore } from '../stores/analysis'
import ReportTabs from '../components/ReportTabs.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useAnalysisStore()
const message = useMessage()

// Memory-log entries: keys are date/ticker/rating/pending (see TradingMemoryLog).
type Entry = { ticker: string; date: string; rating?: string; pending?: boolean }
const entries = ref<Entry[]>([])
const viewing = ref(false)
const current = ref<{ ticker: string; date: string } | null>(null)

const tagType = (r: string) =>
  ({ BUY: 'success', SELL: 'error', HOLD: 'warning' } as const)[(r || '').toUpperCase()] ?? 'default'

const columns = [
  { title: 'Ticker', key: 'ticker' },
  { title: 'Date', key: 'date' },
  {
    title: 'Decision',
    key: 'rating',
    render: (row: Entry) =>
      h(NTag, { type: tagType(row.rating || ''), size: 'small' }, () => row.rating || '—'),
  },
  {
    title: '',
    key: 'open',
    render: (row: Entry) =>
      h(
        NButton,
        { size: 'small', type: 'primary', secondary: true, onClick: () => open(row) },
        () => t('history.open'),
      ),
  },
]

// Open directly (don't rely on route-reuse re-mounting the component) and keep
// the URL in sync for shareable deep links.
async function open(row: Entry) {
  await loadRun(row.ticker, row.date)
  if (route.params.ticker !== row.ticker || route.params.date !== row.date) {
    router.replace({ name: 'history-run', params: { ticker: row.ticker, date: row.date } })
  }
}

async function loadRun(ticker: string, date: string) {
  try {
    const fs = await api.get<Record<string, any>>(
      `/api/history/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}`,
    )
    store.loadFullState(fs)
    current.value = { ticker, date }
    viewing.value = true
  } catch (e) {
    viewing.value = false
    message.error(
      e instanceof ApiError && e.status === 404
        ? `No saved report for ${ticker} · ${date}`
        : 'Failed to open run',
    )
  }
}

// Deep link: /history/:ticker/:date should load even on direct navigation.
watch(
  () => [route.params.ticker, route.params.date],
  ([tk, dt]) => {
    if (tk && dt && (!current.value || current.value.ticker !== tk || current.value.date !== dt)) {
      loadRun(tk as string, dt as string)
    }
  },
)

onMounted(async () => {
  entries.value = await api.get<Entry[]>('/api/history')
  if (route.params.ticker && route.params.date) {
    await loadRun(route.params.ticker as string, route.params.date as string)
  }
})
</script>

<template>
  <n-space vertical :size="16">
    <n-card v-if="viewing && current" size="small" :title="current.ticker + ' · ' + current.date">
      <report-tabs :reports="store.reports" />
    </n-card>
    <n-card :title="t('history.title')" size="small">
      <n-data-table v-if="entries.length" :columns="columns" :data="entries" :pagination="{ pageSize: 15 }" />
      <n-empty v-else :description="t('history.empty')" />
    </n-card>
  </n-space>
</template>
