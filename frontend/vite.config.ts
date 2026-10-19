import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // In development the web app and the API are separate servers; this makes /api reach the backend.
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
