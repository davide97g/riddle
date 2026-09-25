import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from '@/App'
import { LivePage } from '@/LivePage'
import { Toaster } from '@/components/ui/sonner'
import { RiddleProvider } from '@/state/RiddleProvider'
import './index.css'

// Two pages and no router. The server answers every path it does not know
// with the index, so `/live` survives a reload and a bookmark, and a link
// between the two is a plain navigation. The live page opens no events
// socket and no provider: it needs nothing but the screen.
const live = window.location.pathname.replace(/\/+$/, '') === '/live'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {live ? (
      <>
        <LivePage />
        {/* At the bottom: at the top it would sit over the snapshot button,
            and the second snapshot is taken seconds after the first. */}
        <Toaster position="bottom-center" />
      </>
    ) : (
      <RiddleProvider>
        <App />
        <Toaster position="top-center" />
      </RiddleProvider>
    )}
  </StrictMode>,
)
