import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'

import { keycloak } from '@/keycloak'
import { useAuthStore } from '@/stores'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { requiresGuest: true },
    },
    {
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/pages/DashboardPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/robots',
      name: 'robots',
      component: () => import('@/pages/RobotsPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/robots/:id',
      name: 'robot-detail',
      component: () => import('@/pages/RobotDetailPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/pairing',
      name: 'pairing',
      component: () => import('@/pages/PairingPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/orchestration',
      name: 'orchestration',
      component: () => import('@/pages/OrchestrationPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/journal',
      name: 'journal',
      component: () => import('@/pages/JournalPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/account',
      name: 'account',
      component: () => import('@/pages/AccountPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

let initialized = false

/** Путь для возврата после входа: path + query, без hash.
 * Keycloak при check-sso кладёт в hash `error=login_required` — его нельзя класть в redirect_uri. */
function safeRedirectForAuth(to: RouteLocationNormalized): string {
  return to.fullPath.split('#')[0] || '/dashboard'
}

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  if (!initialized) {
    await authStore.init()
    initialized = true
  }

  // После входа через Keycloak первая загрузка часто была на /login без токена:
  // тогда init() отработал с user=null и больше не вызывается. Нужно подтянуть профиль,
  // когда сессия Keycloak уже есть, а Pinia-пользователь ещё пустой.
  if (keycloak.authenticated && !authStore.user && !authStore.loading) {
    await authStore.fetchUser()
  }

  const loggedIn = keycloak.authenticated && !!authStore.user

  if (to.meta.requiresAuth && !loggedIn) {
    next({ name: 'login', query: { redirect: safeRedirectForAuth(to) } })
  } else if (to.meta.requiresGuest && loggedIn) {
    next({ name: 'dashboard' })
  } else {
    next()
  }
})

export default router
