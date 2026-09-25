import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from '@/App'
import { LivePage } from '@/LivePage'
import { SharePage } from '@/SharePage'
import { Toaster } from '@/components/ui/sonner'
import { RiddleProvider } from '@/state/RiddleProvider'
import './index.css'

// Three pages and no router. The server answers every path it does not know
// with the index, so `/live` and `/share` survive a reload and a bookmark,
// and the menu between them is plain navigation. Only the diary has the
// provider: the live page needs nothing but the screen, and the share page
// opens a socket of its own for the strokes and nothing else.
const page = window.location.pathname.replace(/\/+$/, '')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {page === '/live' ? (
      <>
        <LivePage />
        {/* At the bottom: at the top it would sit over the snapshot button,
            and the second snapshot is taken seconds after the first. */}
        <Toaster position="bottom-center" />
      </>
    ) : page === '/share' ? (
      <>
        <SharePage />
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
