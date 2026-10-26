import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AvisoProvider } from './components/ui'
import { AuthProvider } from './store/auth'
import { PulsoProvider } from './store/PulsoStore'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <PulsoProvider>
          <AvisoProvider>
            <App />
          </AvisoProvider>
        </PulsoProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
