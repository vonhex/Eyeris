import { BrowserRouter, Routes, Route, NavLink, Link, useLocation } from "react-router-dom"
import { Component, useEffect, useState, Suspense } from "react"
import Gallery from "./pages/Gallery"
import ImageDetail from "./pages/ImageDetail"
import Dashboard from "./pages/Dashboard"
import PeopleList from "./pages/People"
import Tags from "./pages/Tags"
import Folders from "./pages/Folders"
import Settings from "./pages/Settings"
import ImageSearch from "./pages/ImageSearch"
import Duplicates from "./pages/Duplicates"
import Blurry from "./pages/Blurry"
import Login from "./pages/Login"

const navItems = [
  { to: "/", label: "Gallery", end: true },
  { to: "/?favorite=true", label: "Favorites", end: false, exact: false },
  { to: "/?is_video=true", label: "Videos", end: false },
  { to: "/?untagged=true", label: "Untagged", end: false },
  { to: "/people", label: "People" },
  { to: "/tags", label: "Tags" },
  { to: "/folders", label: "Folders" },
  { to: "/duplicates", label: "Duplicates" },
  { to: "/blurry", label: "Blurry" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/search", label: "Web Search" },
  { to: "/settings", label: "Settings" },
]

function isAuthenticated() {
  const token = localStorage.getItem("eyeris_auth_token")
  if (!token || token === "ready") return false
  // JWT tokens are three dot-separated base64 segments, minimum length ~30
  return typeof token === "string" && token.includes(".") && token.length > 30
}

import { getScanStatus, stopScan } from "./api"

function LoadingScreen() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-gray-400 text-lg animate-pulse">Loading…</div>
    </div>
  )
}

function ErrorFallback({ error, reset }) {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-8">
      <div className="max-w-md text-center space-y-4">
        <h2 className="text-xl font-bold text-white">Something went wrong</h2>
        <pre className="text-red-400 text-sm bg-gray-900 rounded p-4 overflow-auto max-h-60">{String(error)}</pre>
        <button onClick={reset} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition">
          Retry
        </button>
        <button
          onClick={() => {
            localStorage.removeItem("eyeris_auth_token")
            window.location.href = "/login"
          }}
          className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition block ml-auto"
        >
          Log out
        </button>
      </div>
    </div>
  )
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      const Fallback = this.props.fallback
      return <Fallback error={this.state.error} reset={() => this.setState({ error: null })} />
    }
    return this.props.children
  }
}

function PhashStatusBar() {
  const [job, setJob] = useState(null)

  useEffect(() => {
    const poll = () => getScanStatus().then(setJob).catch(() => {})
    poll()
    const interval = setInterval(poll, 2000)
    return () => clearInterval(interval)
  }, [])

  if (!job || job.status !== "phash") return null

  const total = job.phase1_total || 0
  const done = job.phase1_done || 0
  const pct = total > 0 ? Math.round((done / total) * 100) : 0

  return (
    <div className="bg-blue-950 border-b border-blue-800 px-4 py-2 flex items-center gap-3">
      <span className="text-xs text-blue-300 font-medium shrink-0">Visual Duplicate Scan</span>
      <div className="flex-1 bg-blue-900 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${total === 0 ? "bg-blue-500 animate-pulse w-full" : "bg-blue-400"}`}
          style={total > 0 ? { width: `${pct}%` } : undefined}
        />
      </div>
      <span className="text-xs text-blue-400 shrink-0">
        {total > 0 ? `${done.toLocaleString()} / ${total.toLocaleString()} (${pct}%)` : "Starting…"}
      </span>
      <button
        onClick={stopScan}
        className="text-xs text-blue-400 hover:text-white transition shrink-0"
      >
        Stop
      </button>
    </div>
  )
}

function AppNavLink({ to, label }) {
  const location = useLocation()
  const target = new URL(to, "http://x")
  const samePath = location.pathname === target.pathname

  let isActive
  if (target.search) {
    // Tab has query params (e.g. ?favorite=true) — must match exactly
    isActive = samePath && location.search === target.search
  } else if (target.pathname === "/") {
    // Gallery root — only active when no special single-tab params are set
    const sp = new URLSearchParams(location.search)
    isActive = samePath && !sp.get("favorite") && !sp.get("untagged") && !sp.get("is_video")
  } else {
    // Regular path-based tab
    isActive = samePath
  }

  return (
    <Link
      to={to}
      className={`px-3 py-1.5 rounded text-sm font-medium transition whitespace-nowrap ${
        isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"
      }`}
    >
      {label}
    </Link>
  )
}

function MainApp() {
  return (
    <div className="min-h-screen flex flex-col">
      <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-1 overflow-x-auto">
        <div className="flex items-center gap-2 mr-4 shrink-0">
          <img src="/eyeris-logo-icon.png" alt="Eyeris" className="h-7 w-7 rounded bg-white p-0.5 object-contain" />
          <span className="text-xl font-bold text-white tracking-wide">eyeris</span>
        </div>
        {navItems.map((item) => (
          <AppNavLink key={item.to} to={item.to} label={item.label} />
        ))}
        <div className="ml-auto shrink-0">
          <button
            onClick={() => {
              localStorage.removeItem("eyeris_auth_token")
              window.location.href = "/login"
            }}
            className="px-3 py-1.5 rounded text-sm font-medium text-gray-400 hover:text-white transition whitespace-nowrap"
          >
            Logout
          </button>
        </div>
      </nav>
      <PhashStatusBar />
      <main className="flex-1">
        <Suspense fallback={<LoadingScreen />} key={location.pathname}>
          <Routes>
            <Route path="/" element={<Gallery />} />
            <Route path="/image/:id" element={<ImageDetail />} />
            <Route path="/people" element={<PeopleList />} />
            <Route path="/tags" element={<Tags />} />
            <Route path="/folders" element={<Folders />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/search" element={<ImageSearch />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/duplicates" element={<Duplicates />} />
            <Route path="/blurry" element={<Blurry />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}

function ProtectedRoute() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated())
  if (!authenticated) return <Login onLogin={() => setAuthenticated(true)} />
  return (
    <ErrorBoundary fallback={ErrorFallback}>
      <MainApp />
    </ErrorBoundary>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<ProtectedRoute />} />
      </Routes>
    </BrowserRouter>
  )
}
