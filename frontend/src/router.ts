import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/analysis' },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue') },
    { path: '/analysis', name: 'analysis', component: () => import('./views/AnalysisView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    {
      path: '/history/:ticker/:date',
      name: 'history-run',
      component: () => import('./views/HistoryView.vue'),
    },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
  ],
})

// Auth guard: anything but /login requires a valid session.
router.beforeEach(async (to) => {
  if (to.name === 'login') return true
  const auth = useAuthStore()
  if (auth.email) return true
  const ok = await auth.fetchMe()
  return ok ? true : { name: 'login' }
})

export default router
