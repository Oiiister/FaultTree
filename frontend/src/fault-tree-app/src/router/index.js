import { createMemoryHistory, createRouter, createWebHashHistory } from 'vue-router'
import Workspace from '../pages/Workspace.vue'

const routes = [
  {
    path: '/',
    redirect: '/workspace'
  },
  {
    path: '/workspace',
    name: 'FaultTreeWorkspace',
    component: Workspace,
    meta: { title: '故障树生成工作台' }
  }
]

export function createFaultTreeRouter({ embedded = false } = {}) {
  const router = createRouter({
    history: embedded ? createMemoryHistory() : createWebHashHistory(),
    routes
  })

  router.afterEach((to) => {
    if (typeof document !== 'undefined' && to.meta?.title) {
      document.title = to.meta.title
    }
  })

  return router
}

export default createFaultTreeRouter
