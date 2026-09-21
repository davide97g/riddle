import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The python server is the only backend, and in dev vite proxies to it so the
// browser sees one origin. That matters more here than it usually would:
// getUserMedia needs a secure context, and the only https origin we have is
// the tailnet name that `tailscale serve` puts in front of this dev server.
const API = process.env.RIDDLE_SERVER ?? 'http://127.0.0.1:8765'
const TAILNET = process.env.RIDDLE_TAILNET === '1'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: true,
    allowedHosts: ['.ts.net'],
    // tailscale terminates tls on 443 and proxies to 5173, so the hmr client
    // has to dial 443 over wss rather than the port it can see. That same
    // setting breaks plain http://localhost, hence the env gate.
    hmr: TAILNET ? { protocol: 'wss', clientPort: 443 } : undefined,
    proxy: {
      '/api': { target: API, changeOrigin: true },
      '/ws': { target: API, ws: true, changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
