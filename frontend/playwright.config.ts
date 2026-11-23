import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://127.0.0.1:5197', channel: process.platform === 'win32' ? 'msedge' : undefined },
  webServer: { command: 'npm run dev -- --port 5197', url: 'http://127.0.0.1:5197' },
})
