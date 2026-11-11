import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, the dashboard runs on :5173 and talks to the API on :8000.
// In production it is built into dist/ and served by FastAPI at /dashboard/.
export default defineConfig({
  plugins: [react()],
  base: '/dashboard/',
  server: { port: 5173 },
})
