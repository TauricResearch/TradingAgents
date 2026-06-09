<script setup lang="ts">
import { computed, h } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import {
  NConfigProvider, NMessageProvider, NLayout, NLayoutSider, NLayoutContent,
  NMenu, NSpace, NButton, NSelect, NText, NIcon, darkTheme, type MenuOption,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { setLocale } from './i18n'
import { useAuthStore } from './stores/auth'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const showChrome = computed(() => route.name !== 'login')

function emoji(e: string) {
  return () => h('span', { style: 'font-size:18px' }, e)
}

const menuOptions = computed<MenuOption[]>(() => [
  { label: t('nav.analysis'), key: 'analysis', icon: emoji('📈') },
  { label: t('nav.history'), key: 'history', icon: emoji('🕘') },
  { label: t('nav.settings'), key: 'settings', icon: emoji('⚙️') },
])

const activeKey = computed(() => {
  const n = route.name as string
  return n === 'history-run' ? 'history' : n
})

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
  common: { primaryColor: '#2563eb', primaryColorHover: '#3b82f6', borderRadius: '8px' },
}
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <!-- App shell: left sidebar + right content (classic desktop split) -->
      <n-layout v-if="showChrome" has-sider style="height: 100vh">
        <n-layout-sider
          bordered
          :width="220"
          :collapsed-width="64"
          collapse-mode="width"
          show-trigger="arrow-circle"
          :native-scrollbar="false"
          content-style="display:flex; flex-direction:column; height:100%"
        >
          <div style="padding: 18px 16px 8px; display: flex; align-items: center; gap: 8px">
            <span style="font-size: 22px">📈</span>
            <n-text strong style="font-size: 17px; white-space: nowrap">{{ t('title') }}</n-text>
          </div>

          <n-menu
            :options="menuOptions"
            :value="activeKey"
            :collapsed-width="64"
            :collapsed-icon-size="20"
            @update:value="onMenu"
            style="flex: 1"
          />

          <!-- Sidebar footer: language + user + sign out -->
          <div style="padding: 12px; border-top: 1px solid rgba(255,255,255,0.08)">
            <n-space vertical :size="10">
              <n-select v-model:value="langValue" :options="langOptions" size="small" />
              <n-text v-if="auth.email" depth="3" style="font-size: 12px; word-break: break-all">
                👤 {{ auth.email }}
              </n-text>
              <n-button size="small" block quaternary @click="signOut">{{ t('nav.signOut') }}</n-button>
            </n-space>
          </div>
        </n-layout-sider>

        <n-layout-content content-style="padding: 24px" :native-scrollbar="false">
          <router-view />
        </n-layout-content>
      </n-layout>

      <!-- Login: no chrome, full screen -->
      <n-layout v-else style="height: 100vh">
        <n-layout-content>
          <router-view />
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>
