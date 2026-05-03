import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { getSettings, getStats, getScanStatus, startScan, stopScan, startPhashScan, startXmpResync, aeyeAnalyzeUntagged } from "../api"
import ScanProgress from "../components/ScanProgress"

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [scanJob, setScanJob] = useState(null)
  const [aeyeUrl, setAeyeUrl] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    getStats().then(setStats).catch(() => null).finally(() => setLoading(false))
    getScanStatus().then(setScanJob).catch(() => {})
    getSettings().then((s) => setAeyeUrl(s.aeye_url || "")).catch(() => {})

    const interval = setInterval(() => {
      getStats().then(setStats).catch(() => {})
      getScanStatus().then(setScanJob).catch(() => {})
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
          {stats.total_videos > 0 && (
            <StatCard label="Videos" value={stats.total_videos} />
          )}
          <StatCard label="Tagged" value={stats.tagged_images ?? stats.analyzed_images} />
          <StatCard label="With Description" value={stats.described_images ?? 0} />
          <StatCard label="Tag Vocabulary" value={stats.total_tags} />
          {stats.untagged_images > 0 && (
            <StatCard label="Untagged" value={stats.untagged_images} accent="orange" />
          )}
          {stats.duplicate_groups > 0 && (
            <StatCard label="Duplicate Groups" value={stats.duplicate_groups} accent="yellow" />
          )}
        </div>
      )}

      {/* Scan status — reuse the shared component */}
      <ScanProgress />

      {/* Duplicate scan status */}
      <DuplicateScanCard scanJob={scanJob} stats={stats} onNavigate={() => navigate("/duplicates")} />

      {/* XMP tag re-import */}
      <XmpResyncCard scanJob={scanJob} stats={stats} />

      {/* A-Eye integration */}
      {aeyeUrl && <AeyeCard stats={stats} scanJob={scanJob} />}

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
                    style={{ width: `${(count / (stats.total_images + (stats.total_videos ?? 0))) * 100}%` }}
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

function XmpResyncCard({ scanJob, stats }) {
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState(null)

  const ACTIVE = ["listing", "running", "analyzing", "gpu_rescan", "phash"]
  const anyScanRunning = ACTIVE.includes(scanJob?.status)
  const untagged = stats?.untagged_images ?? null

  const handleStart = async () => {
    setStarting(true)
    setError(null)
    try {
      await startXmpResync()
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not start XMP re-sync")
    }
    setStarting(false)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-gray-300">Re-import XMP Tags</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Re-reads sidecar files from disk for images that have no tags yet
            {untagged !== null && untagged > 0 && ` (${untagged.toLocaleString()} untagged)`}
          </p>
        </div>
        <button
          onClick={handleStart}
          disabled={starting || anyScanRunning}
          title={anyScanRunning ? "Another scan is running" : undefined}
          className="text-xs px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white transition shrink-0"
        >
          {starting ? "…" : "Re-import XMP"}
        </button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

function AeyeCard({ stats, scanJob }) {
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const ACTIVE = ["listing", "running", "analyzing", "gpu_rescan", "phash"]
  const anyScanRunning = ACTIVE.includes(scanJob?.status)
  const untagged = stats?.untagged_images ?? 0

  const handleSend = async () => {
    setSending(true)
    setResult(null)
    setError(null)
    try {
      const r = await aeyeAnalyzeUntagged()
      setResult(r)
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to send to A-Eye")
    }
    setSending(false)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-gray-300">Analyze with A-Eye</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Send untagged images to your A-Eye instance for AI analysis.
            {untagged > 0 && ` ${untagged.toLocaleString()} untagged image${untagged !== 1 ? "s" : ""} will be sent.`}
            {untagged === 0 && " No untagged images — all caught up."}
          </p>
        </div>
        <button
          onClick={handleSend}
          disabled={sending || anyScanRunning || untagged === 0}
          title={anyScanRunning ? "A scan is running" : untagged === 0 ? "No untagged images" : undefined}
          className="text-xs px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white transition shrink-0"
        >
          {sending ? "Sending…" : "Send to A-Eye"}
        </button>
      </div>
      {result && result.sent > 0 && (
        <p className="text-xs text-green-400">
          Sent {result.sent} image{result.sent !== 1 ? "s" : ""} to A-Eye.
          {result.errors?.length > 0 && ` ${result.errors.length} failed.`}
          {" "}Use "Re-import XMP Tags" after A-Eye finishes to pull tags back in.
        </p>
      )}
      {result && result.sent === 0 && result.errors?.length > 0 && (
        <div className="text-xs text-red-400 space-y-1">
          <p>All {result.errors.length} failed. First error: {result.errors[0]?.error}</p>
          <p className="text-gray-600">Check that the A-Eye URL is reachable and that both apps share the same photos volume.</p>
        </div>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

function StatCard({ label, value, accent }) {
  const valueColor = accent === "orange" ? "text-orange-400" : accent === "yellow" ? "text-yellow-400" : "text-white"
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className={`text-2xl font-bold ${valueColor}`}>{value?.toLocaleString()}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  )
}
