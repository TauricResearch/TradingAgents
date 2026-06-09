<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  NGrid, NGi, NCard, NForm, NFormItem, NInput, NDatePicker, NSelect, NCheckbox,
  NCheckboxGroup, NSpace, NButton, NInputNumber, NSwitch, NTag, NText, NStatistic,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { useAnalysisStore } from '../stores/analysis'
import ReportTabs from '../components/ReportTabs.vue'

const { t } = useI18n()
const store = useAnalysisStore()
const message = useMessage()

type ProviderTable = Record<string, { models: string[]; key_present: boolean; key_env: string | null }>
const providers = ref<ProviderTable>({})

const raw = ref('NVDA')
const resolved = ref('')
const resolveMsg = ref('')
const tradeDateTs = ref<number>(Date.now() - 86400000)
const provider = ref('doubao')
const deepModel = ref('')
const quickModel = ref('')
const analysts = ref<string[]>(['market'])
const debateRounds = ref(1)
const riskRounds = ref(1)
const outputLang = ref('中文')
const checkpoint = ref(false)

const providerOptions = computed(() =>
  Object.keys(providers.value).map((p) => ({ label: p, value: p })),
)
const modelOptions = computed(() =>
  (providers.value[provider.value]?.models ?? []).map((m) => ({ label: m, value: m })),
)
const keyInfo = computed(() => providers.value[provider.value])

const langOptions = [
  { label: '中文', value: '中文' },
  { label: 'English', value: 'English' },
]
const analystOptions = [
  { label: () => t('cfg.market'), value: 'market' },
  { label: () => t('cfg.social'), value: 'social' },
  { label: () => t('cfg.news'), value: 'news' },
  { label: () => t('cfg.fundamentals'), value: 'fundamentals' },
]

watch(provider, () => {
  const models = providers.value[provider.value]?.models ?? []
  quickModel.value = models[0] ?? ''
  deepModel.value = models[Math.min(2, models.length - 1)] ?? ''
})

let resolveTimer: number | undefined
watch(raw, (q) => {
  window.clearTimeout(resolveTimer)
  resolveTimer = window.setTimeout(async () => {
    if (!q.trim()) {
      resolved.value = ''
      return
    }
    try {
      const r = await api.get<{ ticker: string; message: string }>(
        `/api/resolve-ticker?q=${encodeURIComponent(q)}`,
      )
      resolved.value = r.ticker
      resolveMsg.value = r.message
    } catch {
      resolved.value = ''
    }
  }, 400)
})

const running = computed(() => store.status === 'pending' || store.status === 'running')
const decisionType = computed(() =>
  ({ BUY: 'success', SELL: 'error', HOLD: 'warning' } as const)[store.decisionLabel] ?? 'default',
)

const elapsed = ref(0)
let elapsedTimer: number | undefined
watch(
  () => store.status,
  (s) => {
    window.clearInterval(elapsedTimer)
    if (s === 'running' || s === 'pending') {
      const start = Date.now()
      elapsedTimer = window.setInterval(() => {
        elapsed.value = Math.floor((Date.now() - start) / 1000)
      }, 1000)
    }
  },
)

function fmtDate(ts: number): string {
  return new Date(ts).toISOString().slice(0, 10)
}

async function run() {
  if (analysts.value.length === 0) {
    message.warning('Select at least one analyst')
    return
  }
  if (keyInfo.value && !keyInfo.value.key_present) {
    message.error(t('cfg.keyMissing', { env: keyInfo.value.key_env }))
    return
  }
  try {
    await store.start({
      ticker: resolved.value || raw.value.toUpperCase(),
      trade_date: fmtDate(tradeDateTs.value),
      provider: provider.value,
      deep_model: deepModel.value,
      quick_model: quickModel.value,
      selected_analysts: analysts.value,
      max_debate_rounds: debateRounds.value,
      max_risk_discuss_rounds: riskRounds.value,
      output_language: outputLang.value,
      checkpoint_enabled: checkpoint.value,
    })
  } catch (e: any) {
    message.error(e?.message ?? 'failed to start')
  }
}

onMounted(async () => {
  providers.value = await api.get<ProviderTable>('/api/providers')
  const models = providers.value[provider.value]?.models ?? []
  quickModel.value = models[0] ?? ''
  deepModel.value = models[Math.min(2, models.length - 1)] ?? ''
})
onUnmounted(() => window.clearInterval(elapsedTimer))
</script>

<template>
  <n-grid :cols="24" :x-gap="20" responsive="screen">
    <!-- Config panel -->
    <n-gi :span="24" :m="8" :l="7">
      <n-card :title="t('nav.analysis')" size="small">
        <n-form label-placement="top" size="small">
          <n-form-item :label="t('cfg.ticker')">
            <n-input v-model:value="raw" placeholder="NVDA / 苹果 / 英伟达" />
          </n-form-item>
          <n-text v-if="resolved && resolved !== raw.toUpperCase()" depth="3" style="font-size: 12px">
            {{ t('cfg.resolvedAs') }} <n-tag size="small" type="info">{{ resolved }}</n-tag>
          </n-text>

          <n-form-item :label="t('cfg.date')">
            <n-date-picker v-model:value="tradeDateTs" type="date" style="width: 100%" />
          </n-form-item>

          <n-form-item :label="t('cfg.provider')">
            <n-select v-model:value="provider" :options="providerOptions" />
          </n-form-item>
          <n-text v-if="keyInfo?.key_env" :type="keyInfo.key_present ? 'success' : 'error'" style="font-size: 12px">
            {{ keyInfo.key_present ? t('cfg.keyLoaded', { env: keyInfo.key_env }) : t('cfg.keyMissing', { env: keyInfo.key_env }) }}
          </n-text>

          <n-form-item :label="t('cfg.deepModel')">
            <n-select v-model:value="deepModel" :options="modelOptions" />
          </n-form-item>
          <n-form-item :label="t('cfg.quickModel')">
            <n-select v-model:value="quickModel" :options="modelOptions" />
          </n-form-item>

          <n-form-item :label="t('cfg.analysts')">
            <n-checkbox-group v-model:value="analysts">
              <n-space vertical>
                <n-checkbox v-for="o in analystOptions" :key="o.value" :value="o.value" :label="o.label()" />
              </n-space>
            </n-checkbox-group>
          </n-form-item>

          <n-space>
            <n-form-item :label="t('cfg.debateRounds')">
              <n-input-number v-model:value="debateRounds" :min="1" :max="5" style="width: 90px" />
            </n-form-item>
            <n-form-item :label="t('cfg.riskRounds')">
              <n-input-number v-model:value="riskRounds" :min="1" :max="5" style="width: 90px" />
            </n-form-item>
          </n-space>

          <n-form-item :label="t('cfg.outputLang')">
            <n-select v-model:value="outputLang" :options="langOptions" />
          </n-form-item>
          <n-form-item :label="t('cfg.checkpoint')">
            <n-switch v-model:value="checkpoint" />
          </n-form-item>

          <n-button v-if="!running" type="primary" block @click="run">▶ {{ t('cfg.run') }}</n-button>
          <n-button v-else type="error" block @click="store.cancel()">■ {{ t('cfg.cancel') }}</n-button>
        </n-form>
      </n-card>
    </n-gi>

    <!-- Live report -->
    <n-gi :span="24" :m="16" :l="17">
      <n-card size="small">
        <n-space align="center" justify="space-between" style="margin-bottom: 12px">
          <n-space align="center">
            <n-tag :type="decisionType" size="large" round>{{ store.decisionLabel }}</n-tag>
            <n-text depth="3">{{ resolved || raw }}</n-text>
          </n-space>
          <n-statistic :label="t('elapsed')" :value="elapsed + 's'" />
        </n-space>
        <report-tabs :reports="store.reports" :log="store.log" />
      </n-card>
    </n-gi>
  </n-grid>
</template>
