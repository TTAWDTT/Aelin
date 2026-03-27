import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (
            id.includes('/node_modules/react/')
            || id.includes('/node_modules/react-dom/')
            || id.includes('/node_modules/scheduler/')
          ) {
            return 'react-vendor'
          }

          if (
            id.includes('/node_modules/@langchain/')
            || id.includes('/node_modules/@langchain/langgraph-sdk/')
            || id.includes('/node_modules/langchain/')
            || id.includes('/node_modules/deepagents/')
            || id.includes('/node_modules/@cfworker/')
            || id.includes('/node_modules/eventsource-parser/')
          ) {
            return 'langchain-vendor'
          }

          if (
            id.includes('/node_modules/@radix-ui/')
            || id.includes('/node_modules/@floating-ui/')
          ) {
            return 'radix-vendor'
          }

          if (
            id.includes('/node_modules/react-markdown/')
            || id.includes('/node_modules/remark-gfm/')
            || id.includes('/node_modules/mdast-util-')
            || id.includes('/node_modules/micromark')
            || id.includes('/node_modules/unified/')
            || id.includes('/node_modules/remark-')
            || id.includes('/node_modules/rehype-')
          ) {
            return 'markdown-vendor'
          }

          if (
            id.includes('/node_modules/framer-motion/')
            || id.includes('/node_modules/motion-dom/')
            || id.includes('/node_modules/motion-utils/')
          ) {
            return 'motion-vendor'
          }

          if (
            id.includes('/node_modules/react-router/')
            || id.includes('/node_modules/react-router-dom/')
            || id.includes('/node_modules/@remix-run/')
          ) {
            return 'router-vendor'
          }

          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 10 * 60 * 1000,
        proxyTimeout: 10 * 60 * 1000,
      },
      '/media': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 10 * 60 * 1000,
        proxyTimeout: 10 * 60 * 1000,
      },
    },
  },
})
