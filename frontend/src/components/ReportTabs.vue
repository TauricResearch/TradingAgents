<script setup lang="ts">
import { NTabs, NTabPane, NEmpty, NLog } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import Markdown from './Markdown.vue'
import type { Reports } from '../stores/analysis'

defineProps<{ reports: Reports; log?: string[] }>()
const { t } = useI18n()

const tabs: { key: keyof Reports; label: string }[] = [
  { key: 'market_report', label: 'tabs.market' },
  { key: 'sentiment_report', label: 'tabs.sentiment' },
  { key: 'news_report', label: 'tabs.news' },
  { key: 'fundamentals_report', label: 'tabs.fundamentals' },
  { key: 'investment_plan', label: 'tabs.invest' },
  { key: 'trader_investment_plan', label: 'tabs.trader' },
  { key: 'final_trade_decision', label: 'tabs.risk' },
]
</script>

<template>
  <n-tabs type="line" animated>
    <n-tab-pane v-for="tab in tabs" :key="tab.key" :name="tab.key" :tab="t(tab.label)">
      <markdown v-if="reports[tab.key]" :source="reports[tab.key]" />
      <n-empty v-else :description="t('waiting')" style="margin-top: 40px" />
    </n-tab-pane>
    <n-tab-pane v-if="log" name="log" :tab="t('tabs.log')">
      <n-log :log="log.join('\n')" :rows="20" />
    </n-tab-pane>
  </n-tabs>
</template>
