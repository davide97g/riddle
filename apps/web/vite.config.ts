import { fileURLToPath, URL } from 'node:url'
import type { ServerResponse } from 'node:http'
import type { Socket } from 'node:net'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The python server is the only backend, and in dev vite proxies to it so the
// browser sees one origin. That matters more here than it usually would:
// getUserMedia needs a secure context, and the only https origin we have is
// the tailnet name that `tailscale serve` puts in front of this dev server.
const API = process.env.RIDDLE_SERVER ?? 'http://127.0.0.1:8765'
const TAILNET = process.env.RIDDLE_TAILNET === '1'

/** Enough of http-proxy's emitter to take vite's loggers off it again. */
interface ProxyLike {
  removeAllListeners(event: string): unknown
  on(
    event: 'error',
    fn: (err: Error, req: unknown, res: ServerResponse | Socket) => void,
  ): unknown
  on(
    event: 'proxyReqWs',
    fn: (proxyReq: unknown, req: unknown, socket: Socket) => void,
  ): unknown
}

/** `riddle dev` takes the python server out from under an open websocket every
 *  time it reloads, and vite answers that with two ten-line node stacks -- one
 *  for the proxy and one for the socket -- for something the page recovers
 *  from by itself in under a second. The stacks are all node internals and say
 *  nothing the first line does not.
 *
 *  Vite attaches those loggers immediately *after* calling `configure`, so
 *  they can only be replaced a tick later. Two things go with them and both
 *  have to be put back: the 502 a dead http target should still answer with,
 *  and the socket's own error handler -- an 'error' with nothing listening
 *  takes the dev server down rather than logging anything. `rewriteWsOrigin`
 *  rides on the same listener and is removed too; it is not set here, and
 *  setting it would mean dropping this. */
function quieten(proxy: ProxyLike, what: string) {
  const say = (err: Error) =>
    console.log(`${what} proxy: ${err.message} -- the page will redial`)
  setTimeout(() => {
    proxy.removeAllListeners('error')
    proxy.removeAllListeners('proxyReqWs')
    proxy.on('error', (err, _req, res) => {
      say(err)
      if (res && 'req' in res) {
        if (!res.headersSent && !res.writableEnded) {
          res.writeHead(502, { 'Content-Type': 'text/plain' }).end()
        }
      } else {
        res?.end()
      }
    })
    proxy.on('proxyReqWs', (_proxyReq, _req, socket) => socket.on('error', say))
  }, 0)
}

const hush = (what: string) => (proxy: unknown) =>
  quieten(proxy as ProxyLike, what)

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
      '/api': { target: API, changeOrigin: true, configure: hush('api') },
      '/ws': { target: API, ws: true, changeOrigin: true, configure: hush('ws') },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
