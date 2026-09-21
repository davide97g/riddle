import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from '@/App'
import { Toaster } from '@/components/ui/sonner'
import { RiddleProvider } from '@/state/RiddleProvider'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RiddleProvider>
      <App />
      <Toaster position="top-center" />
    </RiddleProvider>
  </StrictMode>,
)
