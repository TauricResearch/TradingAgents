<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NInput, NButton, NSpace, NText, NAlert, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { ApiError } from '../api/client'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const message = useMessage()

const email = ref('')
const code = ref('')
const sent = ref(false)
const busy = ref(false)

async function send() {
  if (!email.value) return
  busy.value = true
  try {
    await auth.requestOtp(email.value)
    sent.value = true
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : 'failed')
  } finally {
    busy.value = false
  }
}

async function verify() {
  busy.value = true
  try {
    await auth.verifyOtp(email.value, code.value)
    router.push({ name: 'analysis' })
  } catch (e) {
    message.error(e instanceof ApiError && e.status === 400 ? t('login.invalid') : 'failed')
  } finally {
    busy.value = false
  }
}

function useOther() {
  sent.value = false
  code.value = ''
}
</script>

<template>
  <div style="display: flex; align-items: center; justify-content: center; height: 100%; padding: 24px">
    <n-card style="max-width: 420px" :title="'🔒 ' + t('title')">
      <n-text depth="3">{{ t('login.caption') }}</n-text>
      <n-space vertical style="margin-top: 20px" :size="16">
        <template v-if="!sent">
          <n-input v-model:value="email" :placeholder="t('login.email')" @keyup.enter="send" />
          <n-button type="primary" block :loading="busy" @click="send">{{ t('login.sendCode') }}</n-button>
        </template>
        <template v-else>
          <n-alert type="info">{{ t('login.sent', { email }) }}</n-alert>
          <n-input v-model:value="code" :placeholder="t('login.code')" maxlength="6" @keyup.enter="verify" />
          <n-space>
            <n-button type="primary" :loading="busy" @click="verify">{{ t('login.verify') }}</n-button>
            <n-button quaternary @click="useOther">{{ t('login.useOther') }}</n-button>
          </n-space>
        </template>
      </n-space>
    </n-card>
  </div>
</template>
