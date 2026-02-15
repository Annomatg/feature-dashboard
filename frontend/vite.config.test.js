import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Test-specific Vite configuration
// This config is used during E2E tests and proxies API requests to port 8001 (test backend)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',  // Test backend port
        changeOrigin: true,
      }
    }
  }
})
