import { createRouter, createWebHistory } from 'vue-router'

import { authState, initializeAuthState } from '@/state/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { guestOnly: true }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/pages/RegisterPage.vue'),
      meta: { guestOnly: true }
    },
    {
      path: '/',
      name: 'project-list',
      component: () => import('@/pages/ProjectListPage.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/projects/:id',
      component: () => import('@/layouts/ProjectWorkbenchLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: { name: 'project-dashboard' }
        },
        {
          path: 'dashboard',
          name: 'project-dashboard',
          component: () => import('@/pages/ProjectDashboardPage.vue')
        },
        {
          path: 'source',
          name: 'source-chapters',
          component: () => import('@/pages/SourceChaptersPage.vue')
        },
        {
          path: 'characters',
          name: 'character-bible',
          component: () => import('@/pages/CharacterBiblePage.vue')
        },
        {
          path: 'episodes',
          name: 'episode-planning',
          component: () => import('@/pages/EpisodePlanningPage.vue')
        },
        {
          path: 'storyboard',
          name: 'storyboard-workbench',
          component: () => import('@/pages/StoryboardWorkbenchPage.vue')
        },
        {
          path: 'renders',
          name: 'render-center',
          component: () => import('@/pages/RenderCenterPage.vue')
        },
        {
          path: 'delivery',
          name: 'delivery-output',
          component: () => import('@/pages/DeliveryOutputPage.vue')
        }
      ]
    }
  ]
})

router.beforeEach(async (to) => {
  await initializeAuthState()

  const authDisabled = authState.bootstrap?.auth_disabled === true
  const needsAuth = to.matched.some((record) => record.meta.requiresAuth)
  const guestOnly = to.matched.some((record) => record.meta.guestOnly)

  if (needsAuth && !authDisabled && !authState.token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (guestOnly && (authDisabled || authState.token)) {
    return { name: 'project-list' }
  }

  return true
})

export default router
