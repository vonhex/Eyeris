import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { getStats, getScanStatus, startScan, stopScan, startPhashScan, getAeyeStatus } from "../api"
import ScanProgress from "../components/ScanProgress"
import HardwareStats from "../components/HardwareStats"

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [scanJob, setScanJob] = useState(null)
  const [aeye, setAeye] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    getStats().then(setStats).catch(() => null).finally(() => setLoading(false))
    getScanStatus().then(setScanJob).catch(() => {})
    getAeyeStatus().then(setAeye).catch(() => {})

    const interval = setInterval(() => {
      getStats().then(setStats).catch(() => {})
      getScanStatus().then(setScanJob).catch(() => {})
      getAeyeStatus().then(setAeye).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="p-6 text-gray-500">Loading dashboard...</div>

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold text-white">Dashboard</h2>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Images" value={stats.total_images} />
          <StatCard label="Analyzed" value={stats.analyzed_images} />
          <StatCard label="Tags" value={stats.total_tags} />
          {stats.duplicate_groups > 0 && (
            <StatCard label="Duplicate Groups" value={stats.duplicate_groups} accent="yellow" />
          )}
        </div>
      )}

      {/* Scan status — reuse the shared component */}
      <ScanProgress />

      {/* Duplicate scan status */}
      <DuplicateScanCard scanJob={scanJob} stats={stats} onNavigate={() => navigate("/duplicates")} />

      {/* A-EYE status */}
      {aeye && aeye.configured && <AeyeCard aeye={aeye} />}

      {/* Live hardware stats */}
      <HardwareStats />

      {/* Images by folder */}
      {stats && Object.keys(stats.images_by_folder).length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h3 className="text-lg font-medium text-white mb-3">Images by Folder</h3>
          <div className="space-y-2">
            {Object.entries(stats.images_by_folder).map(([folder, count]) => (
              <div key={folder} className="flex items-center gap-3">
                <span className="text-sm text-gray-400 w-48 truncate">{folder}</span>
                <div className="flex-1 bg-gray-800 rounded-full h-2">
                  <div
                    className="bg-green-600 h-2 rounded-full"
                    style={{ width: `${(count / stats.total_images) * 100}%` }}
                  />
                </div>
                <span className="text-sm text-gray-500 w-12 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top tags */}
      {stats && stats.top_tags.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h3 className="text-lg font-medium text-white mb-3">Top Tags</h3>
          <div className="flex flex-wrap gap-2">
            {stats.top_tags.map((t) => (
              <span
                key={t.name}
                className="text-sm px-3 py-1 bg-gray-800 text-gray-300 rounded-full"
              >
                {t.name} <span className="text-gray-600">{t.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Categories */}
      {stats && stats.images_by_category.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h3 className="text-lg font-medium text-white mb-3">Categories</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {stats.images_by_category.map((c) => (
              <div key={c.name} className="flex justify-between bg-gray-800 rounded px-3 py-2">
                <span className="text-sm text-gray-300">{c.name}</span>
                <span className="text-sm text-gray-500">{c.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function DuplicateScanCard({ scanJob, stats, onNavigate }) {
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)

  const isPhash = scanJob?.status === "phash"
  const ACTIVE = ["listing", "running", "analyzing", "gpu_rescan", "phash"]
  const anyScanRunning = ACTIVE.includes(scanJob?.status)

  const hashed = stats?.phash_count ?? null
  const total = stats?.total_images ?? 0
  const pct = total > 0 && hashed !== null ? Math.round((hashed / total) * 100) : 0

  const handleStart = async () => {
    setStarting(true)
    setError(null)
    try {
      await startPhashScan()
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not start scan")
    }
    setStarting(false)
  }

  const done = isPhash && scanJob.phase1_done
  const scanTotal = isPhash && scanJob.phase1_total

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-gray-300">Visual Duplicate Detection</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            {hashed !== null
              ? `${hashed?.toLocaleString()} / ${total?.toLocaleString()} images hashed (${pct}%)`
              : "No hashes computed yet"}
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={onNavigate}
            className="text-xs px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition"
          >
            View Duplicates
          </button>
          {!isPhash && (
            <button
              onClick={handleStart}
              disabled={starting || anyScanRunning}
              title={anyScanRunning && !isPhash ? "Another scan is running" : undefined}
              className="text-xs px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white transition"
            >
              {starting ? "…" : hashed ? "Re-scan" : "Start Scan"}
            </button>
          )}
        </div>
      </div>

      {isPhash && (
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Scanning…</span>
            <span>{scanTotal > 0 ? `${done?.toLocaleString()} / ${scanTotal?.toLocaleString()}` : "Starting…"}</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all duration-500 bg-blue-500 ${scanTotal === 0 ? "animate-pulse w-full opacity-50" : ""}`}
              style={scanTotal > 0 ? { width: `${Math.round((done / scanTotal) * 100)}%` } : undefined}
            />
          </div>
        </div>
      )}

      {hashed !== null && hashed < total && !isPhash && (
        <div>
          <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
            <div className="bg-blue-600/60 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className="text-2xl font-bold text-white">{value?.toLocaleString()}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  )
}

function AeyeCard({ aeye }) {
  const connected = aeye.connected !== false
  const pct = aeye.progress_pct != null ? Math.min(100, Math.round(aeye.progress_pct)) : null
  const workerBusy = aeye.worker_state && aeye.worker_state !== "idle" && aeye.worker_state !== "stopped"

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">A-EYE</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          !connected ? "bg-red-900/50 text-red-400" :
          aeye.ollama_connected === false ? "bg-yellow-900/50 text-yellow-400" :
          "bg-green-900/50 text-green-400"
        }`}>
          {!connected ? "Unreachable" : aeye.ollama_connected === false ? "Ollama offline" : "Online"}
        </span>
      </div>

      {!connected && aeye.error && (
        <p className="text-xs text-red-400">{aeye.error}</p>
      )}

      {connected && (
        <div className="space-y-2">
          {/* Models */}
          <div className="flex gap-4 text-xs text-gray-500">
            {aeye.vision_model && <span>Vision: <span className="text-gray-300">{aeye.vision_model}</span></span>}
            {aeye.llm_model && <span>LLM: <span className="text-gray-300">{aeye.llm_model}</span></span>}
          </div>

          {!aeye.auth_configured && (
            <p className="text-xs text-yellow-600">Add A-EYE username &amp; password in Settings to see processing stats.</p>
          )}

          {/* Counts */}
          {(aeye.total_images != null || aeye.processed != null) && (
            <div className="grid grid-cols-3 gap-2">
              {aeye.total_images != null && (
                <div className="bg-gray-800 rounded px-2 py-1.5 text-center">
                  <p className="text-sm font-semibold text-white">{aeye.total_images?.toLocaleString()}</p>
                  <p className="text-xs text-gray-500">Total</p>
                </div>
              )}
              {aeye.processed != null && (
                <div className="bg-gray-800 rounded px-2 py-1.5 text-center">
                  <p className="text-sm font-semibold text-green-400">{aeye.processed?.toLocaleString()}</p>
                  <p className="text-xs text-gray-500">Processed</p>
                </div>
              )}
              {aeye.pending != null && (
                <div className="bg-gray-800 rounded px-2 py-1.5 text-center">
                  <p className="text-sm font-semibold text-yellow-400">{aeye.pending?.toLocaleString()}</p>
                  <p className="text-xs text-gray-500">Pending</p>
                </div>
              )}
            </div>
          )}

          {/* Progress bar */}
          {pct != null && (
            <div>
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{workerBusy ? `Processing · ${aeye.worker_state}` : "Idle"}</span>
                <span>{pct}%</span>
              </div>
              <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-1.5 rounded-full transition-all duration-500 ${workerBusy ? "bg-blue-500" : "bg-green-600"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          {/* Queue depth */}
          {aeye.queue_depth != null && aeye.queue_depth > 0 && (
            <p className="text-xs text-gray-500">Queue: <span className="text-gray-300">{aeye.queue_depth} items</span></p>
          )}

          {aeye.errors != null && aeye.errors > 0 && (
            <p className="text-xs text-red-400">{aeye.errors} error{aeye.errors !== 1 ? "s" : ""}</p>
          )}
        </div>
      )}
    </div>
  )
}
