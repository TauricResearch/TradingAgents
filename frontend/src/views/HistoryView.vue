<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NDataTable, NTag, NButton, NEmpty, NSpace } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { useAnalysisStore } from '../stores/analysis'
import ReportTabs from '../components/ReportTabs.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useAnalysisStore()

type Entry = { ticker: string; trade_date: string; decision?: string; rating?: string; pending?: boolean }
const entries = ref<Entry[]>([])
const viewing = ref(false)

const tagType = (r: string) =>
  ({ BUY: 'success', SELL: 'error', HOLD: 'warning' } as const)[(r || '').toUpperCase()] ?? 'default'

const columns = [
  { title: 'Ticker', key: 'ticker' },
  { title: 'Date', key: 'trade_date' },
  {
    title: 'Decision',
    key: 'rating',
    render: (row: Entry) =>
      h(NTag, { type: tagType(row.rating || row.decision || ''), size: 'small' }, () => row.rating || row.decision || '—'),
  },
  {
    title: '',
    key: 'open',
    render: (row: Entry) =>
      h(NButton, { size: 'small', onClick: () => open(row) }, () => t('history.open')),
  },
]

async function open(row: Entry) {
  router.push({ name: 'history-run', params: { ticker: row.ticker, date: row.trade_date } })
}

async function loadRun(ticker: string, date: string) {
  try {
    const fs = await api.get<Record<string, any>>(
      `/api/history/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}`,
    )
    store.loadFullState(fs)
    viewing.value = true
  } catch {
    viewing.value = false
  }
}

onMounted(async () => {
  entries.value = await api.get<Entry[]>('/api/history')
  if (route.params.ticker) await loadRun(route.params.ticker as string, route.params.date as string)
})
</script>

<template>
  <n-space vertical :size="16">
    <n-card v-if="viewing" size="small" :title="(route.params.ticker as string) + ' · ' + (route.params.date as string)">
      <report-tabs :reports="store.reports" />
    </n-card>
    <n-card :title="t('history.title')" size="small">
      <n-data-table v-if="entries.length" :columns="columns" :data="entries" :pagination="{ pageSize: 15 }" />
      <n-empty v-else :description="t('history.empty')" />
    </n-card>
  </n-space>
</template>
