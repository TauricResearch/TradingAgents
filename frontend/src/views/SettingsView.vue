<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NCard, NSpace, NForm, NFormItem, NSwitch, NInput, NButton, NUpload, NList,
  NListItem, NThing, NText, useMessage, type UploadCustomRequestOptions,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { usePrefsStore, type Prefs } from '../stores/prefs'

const { t } = useI18n()
const message = useMessage()
const prefsStore = usePrefsStore()

const prefs = ref<Prefs | null>(null)
const watchlistText = ref('')
const researchTicker = ref('NVDA')
const researchItems = ref<any[]>([])

async function loadResearch() {
  try {
    researchItems.value = await api.get<any[]>(`/api/research?ticker=${encodeURIComponent(researchTicker.value)}`)
  } catch {
    researchItems.value = []
  }
}

async function save() {
  if (!prefs.value) return
  prefs.value.tickers = watchlistText.value.split('\n').map((s) => s.trim()).filter(Boolean)
  await prefsStore.save(prefs.value)
  message.success(t('settings.saved'))
}

async function testPing() {
  if (!prefs.value?.telegram_chat_id) return
  const r = await api.post<{ ok: boolean; message: string }>('/api/telegram/test', {
    chat_id: prefs.value.telegram_chat_id,
  })
  r.ok ? message.success('ok') : message.error(r.message)
}

const uploadRequest = async ({ file, onFinish, onError }: UploadCustomRequestOptions) => {
  try {
    const form = new FormData()
    form.append('ticker', researchTicker.value)
    form.append('file', file.file as File)
    await api.upload('/api/research', form)
    await loadResearch()
    onFinish()
  } catch {
    onError()
  }
}

async function deleteResearch(digest: string) {
  await api.del(`/api/research/${encodeURIComponent(researchTicker.value)}/${encodeURIComponent(digest)}`)
  await loadResearch()
}

onMounted(async () => {
  prefs.value = await prefsStore.load()
  watchlistText.value = (prefs.value.tickers ?? []).join('\n')
  await loadResearch()
})
</script>

<template>
  <n-space vertical :size="16" style="max-width: 720px">
    <n-card :title="t('settings.schedule')" size="small" v-if="prefs">
      <n-form label-placement="top">
        <n-form-item :label="t('settings.enable')">
          <n-switch v-model:value="prefs.daily_schedule_enabled" />
        </n-form-item>
        <n-form-item :label="t('settings.watchlist')">
          <n-input v-model:value="watchlistText" type="textarea" :rows="4" placeholder="NVDA&#10;AAPL" />
        </n-form-item>
        <n-form-item :label="t('settings.chatId')">
          <n-space>
            <n-input v-model:value="prefs.telegram_chat_id" style="width: 240px" />
            <n-button @click="testPing">{{ t('settings.testPing') }}</n-button>
          </n-space>
        </n-form-item>
        <n-button type="primary" @click="save">{{ t('settings.save') }}</n-button>
      </n-form>
    </n-card>

    <n-card :title="t('settings.research')" size="small">
      <n-space vertical>
        <n-space align="center">
          <n-input v-model:value="researchTicker" style="width: 160px" @blur="loadResearch" />
          <n-upload :custom-request="uploadRequest" :show-file-list="false" accept=".pdf,.md,.txt,.markdown">
            <n-button>{{ t('settings.upload') }}</n-button>
          </n-upload>
        </n-space>
        <n-list bordered v-if="researchItems.length">
          <n-list-item v-for="m in researchItems" :key="m.hash || m.digest">
            <n-thing :title="m.filename">
              <template #description>
                <n-text depth="3" style="font-size: 12px">{{ (m.summary || '').slice(0, 160) }}</n-text>
              </template>
            </n-thing>
            <template #suffix>
              <n-button size="tiny" type="error" @click="deleteResearch(m.hash || m.digest)">✕</n-button>
            </template>
          </n-list-item>
        </n-list>
      </n-space>
    </n-card>
  </n-space>
</template>
