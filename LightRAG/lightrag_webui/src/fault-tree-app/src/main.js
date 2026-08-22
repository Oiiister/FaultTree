import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '../../index.css'
import App from './App.vue'
import { createFaultTreeRouter } from './router'

let errorHandlerInstalled = false

const installGlobalErrorHandler = () => {
  if (errorHandlerInstalled || typeof window === 'undefined') {
    return
  }

  errorHandlerInstalled = true

  window.addEventListener('error', (event) => {
    if (
      event.message?.includes('getRangeAt') ||
      event.message?.includes('Selection') ||
      event.message?.includes('IndexSizeError') ||
      event.filename?.includes('content.js') ||
      event.filename?.includes('extension') ||
      event.filename?.includes('chrome-extension://') ||
      event.filename?.includes('edge-extension://')
    ) {
      console.warn('忽略浏览器扩展错误:', event.message)
      return
    }

    console.error('全局错误:', event)
  })
}

const resolveTarget = (target) => {
  if (typeof target === 'string') {
    return document.querySelector(target)
  }

  return target
}

export function mountFaultTreeApp(target, { embedded = false } = {}) {
  const mountTarget = resolveTarget(target)
  if (!mountTarget) {
    throw new Error('Fault tree mount target not found')
  }

  installGlobalErrorHandler()

  const app = createApp(App)
  const pinia = createPinia()
  const router = createFaultTreeRouter({ embedded })

  mountTarget.classList.add('fault-tree-mount-host')
  mountTarget.innerHTML = ''
  mountTarget.style.width = '100%'
  mountTarget.style.height = '100%'

  app.use(pinia)
  app.use(router)
  app.use(ElementPlus)

  app.mount(mountTarget)

  if (embedded) {
    router.replace('/workspace')
  }

  return {
    app,
    router,
    unmount() {
      app.unmount()
      mountTarget.innerHTML = ''
    }
  }
}