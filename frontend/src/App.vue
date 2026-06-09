<script setup lang="ts">
import { computed, h } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import {
  NConfigProvider, NMessageProvider, NLayout, NLayoutHeader, NLayoutContent,
  NMenu, NSpace, NButton, NSelect, NText, darkTheme,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { setLocale } from './i18n'
import { useAuthStore } from './stores/auth'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const showChrome = computed(() => route.name !== 'login')

const menuOptions = computed(() => [
  { label: t('nav.analysis'), key: 'analysis' },
  { label: t('nav.history'), key: 'history' },
  { label: t('nav.settings'), key: 'settings' },
])

function onMenu(key: string) {
  router.push({ name: key })
}

const langValue = computed({
  get: () => locale.value,
  set: (v: string) => setLocale(v as 'en' | 'zh'),
})

const langOptions = [
  { label: 'English', value: 'en' },
  { label: '中文', value: 'zh' },
]

async function signOut() {
  await auth.logout()
  router.push({ name: 'login' })
}

const themeOverrides = {
  common: {
    primaryColor: '#2563eb',
    primaryColorHover: '#3b82f6',
    borderRadius: '8px',
  },
}
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-layout style="height: 100vh">
        <n-layout-header v-if="showChrome" bordered style="padding: 0 20px; height: 56px; display: flex; align-items: center; gap: 24px">
          <n-text strong style="font-size: 18px">📈 {{ t('title') }}</n-text>
          <n-menu
            mode="horizontal"
            :options="menuOptions"
            :value="(route.name as string)"
            @update:value="onMenu"
            style="flex: 1"
          />
          <n-space align="center">
            <n-select v-model:value="langValue" :options="langOptions" size="small" style="width: 110px" />
            <n-text depth="3" v-if="auth.email">👤 {{ auth.email }}</n-text>
            <n-button size="small" tertiary @click="signOut">{{ t('nav.signOut') }}</n-button>
          </n-space>
        </n-layout-header>
        <n-layout-content :content-style="showChrome ? 'padding: 24px' : ''" style="height: calc(100vh - 56px)">
          <router-view />
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>
