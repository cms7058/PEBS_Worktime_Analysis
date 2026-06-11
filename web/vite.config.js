import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发模式下把 API 请求代理到 FastAPI（8000 端口）
const apiProxy = { target: 'http://localhost:8000', changeOrigin: true }

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/processes': apiProxy,
      '/batches': apiProxy,
      '/pmts': apiProxy,
      '/llm': apiProxy,
      '/chat': apiProxy,
    },
  },
})
