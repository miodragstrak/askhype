import './App.css'
import { AuthProvider } from './auth'
import { UsageProvider } from './usage'
import Router from './router'

export default function App() {
  return (
    <AuthProvider>
      <UsageProvider>
        <div className="min-h-screen overflow-x-hidden bg-hype-white">
          <Router />
        </div>
      </UsageProvider>
    </AuthProvider>
  )
}
