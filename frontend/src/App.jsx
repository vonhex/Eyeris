import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom"
import { useEffect, useState } from "react"
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
import { getScanStatus, stopScan } from "./api"

const navItems = [
  { to: "/", label: "Gallery", end: true },
  { to: "/?favorite=true", label: "Favorites", end: false, exact: false },
  { to: "/people", label: "People" },
  { to: "/tags", label: "Tags" },
  { to: "/folders", label: "Folders" },
  { to: "/duplicates", label: "Duplicates" },
  { to: "/blurry", label: "Blurry" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/search", label: "Web Search" },
  { to: "/settings", label: "Settings" },
]

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

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-1 overflow-x-auto">
          <div className="flex items-center gap-2 mr-4 shrink-0">
            <img src="/eyeris-logo-icon.png" alt="Eyeris" className="h-7 w-7 rounded bg-white p-0.5 object-contain" />
            <span className="text-xl font-bold text-white tracking-wide">eyeris</span>
          </div>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end !== false}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded text-sm font-medium transition whitespace-nowrap ${
                  isActive ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <PhashStatusBar />
        <main className="flex-1">
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
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
