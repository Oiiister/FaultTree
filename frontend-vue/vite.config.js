import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// 自定义日志插件
const customLogPlugin = {
  name: 'custom-log-plugin',
  configureServer(server) {
    const originalPrint = server.printUrls
    
    // 重写 URL 打印函数
    server.printUrls = () => {
      const port = server.config.server.port || 3001
      console.log('')
      console.log('  ➜  Vite 服务已启动')
      console.log(`  ➜  Local:   http://localhost:${port}/test-theme`)
      console.log(`  ➜  Network: use --host to expose`)
    }
  }
}

export default defineConfig({
  plugins: [vue(), customLogPlugin],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  esbuild: {
    sourcemap: false
  },
  optimizeDeps: {
    esbuildOptions: {
      sourcemap: false
    }
  },
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false
  }
})
