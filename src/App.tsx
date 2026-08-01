import './App.css'
import { AuthProvider } from './auth'
import Router from './router'

export default function App() {
  return (
    <AuthProvider>
      <div className="min-h-screen overflow-x-hidden bg-hype-white">
        <Router />
      </div>
    </AuthProvider>
  )
}
