import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const ensureTailwindCdnLoaded = () => {
  if (typeof document === 'undefined') return Promise.resolve()
  if (document.querySelector('script[data-tailwindcdn="true"]')) return Promise.resolve()

  return new Promise((resolve) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.tailwindcss.com'
    script.async = true
    script.setAttribute('data-tailwindcdn', 'true')
    script.onload = () => resolve()
    script.onerror = () => resolve()
    document.head.appendChild(script)
  })
}

const bootstrap = async () => {
  // Always load Tailwind for the new Naive style
  await ensureTailwindCdnLoaded()

  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)
  app.use(router)
  app.use(ElementPlus)

  app.mount('#app')
}

bootstrap()

// 全局错误处理器 - 忽略浏览器扩展导致的错误
window.addEventListener('error', (event) => {
  // 如果是 content.js 或扩展相关的错误，直接忽略
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
  
  // 其他错误正常处理
  console.error('全局错误:', event)
})
