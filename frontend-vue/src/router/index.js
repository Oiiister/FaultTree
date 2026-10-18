import { createRouter, createWebHistory } from 'vue-router'
import Workspace from '../pages/Workspace.vue'

const routes = [
  {
    path: '/',
    redirect: '/test-theme'
  },
  {
    path: '/test-theme',
    name: 'TestTheme',
    component: Workspace,
    meta: { title: '故障树生成工作台' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
