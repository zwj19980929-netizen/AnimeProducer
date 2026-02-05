import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'

import './style.css'

import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('./views/ProjectList.vue')
    },
    {
      path: '/projects/:id',
      name: 'project-detail',
      component: () => import('./views/ProjectDetail.vue')
    },
    {
      path: '/api-test',
      name: 'api-test',
      component: () => import('./views/ApiTest.vue')
    }
  ]
})

const pinia = createPinia()
const app = createApp(App)

app.use(pinia)
app.use(router)
app.mount('#app')
