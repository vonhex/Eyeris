import { useEffect, useState } from "react"
import { getScanStatus, startScan, startGpuRescan, stopScan, pauseScan, resumeScan } from "../api"

export default function ScanProgress() {
  const [status, setStatus] = useState(null)
  const [actionPending, setActionPending] = useState(false)
  const [stopping, setStopping] = useState(false)

  useEffect(() => {
    const poll = () => getScanStatus().then(setStatus).catch(() => {})
    poll()
    const interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  }, [])

  // Support both old (flat job) and new (wrapped {job, paused, schedule}) shapes
  const job = status?.job !== undefined ? status.job : status
  const paused = status?.paused ?? false
  const schedule = status?.schedule ?? null

  const isListing = job?.status === "listing"
  const isDiscovering = job?.status === "running"
  const isAnalyzing = job?.status === "analyzing"
  const isGpuRescan = job?.status === "gpu_rescan"
  const isActive = isListing || isDiscovering || isAnalyzing || isGpuRescan

  useEffect(() => {
    if (!isActive) setStopping(false)
  }, [isActive])

  const doAction = async (action) => {
    setActionPending(true)
    try {
      await action()
      setTimeout(() => {
        getScanStatus().then(setStatus).catch(() => {})
        setActionPending(false)
      }, 1000)
    } catch (err) {
      console.error(err)
      setActionPending(false)
    }
  }

  if (!job) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-gray-300">No scans yet</h3>
          <button
            onClick={() => doAction(startScan)}
            disabled={actionPending}
            className="text-xs px-3 py-1 rounded transition disabled:opacity-50 bg-blue-600 hover:bg-blue-700 text-white"
          >
            {actionPending ? "..." : "Start Scan"}
          </button>
        </div>
      </div>
    )
  }

  const p1Pct = job.phase1_total > 0 ? Math.round((job.phase1_done / job.phase1_total) * 100) : 0
  const p1Active = isDiscovering || isGpuRescan
  const p1Indeterminate = p1Active && job.phase1_done === 0 && job.phase1_total > 0

  const handleStop = () => {
    setStopping(true)
    doAction(stopScan)
  }

  const statusLabel = stopping
    ? "Stopping..."
    : paused
    ? "Paused"
    : isListing
    ? "Checking NAS..."
    : isGpuRescan
    ? "Resyncing Library — All Images"
    : isActive
    ? "Syncing Images"
    : job.status === "completed"
    ? "Sync Complete"
    : job.status === "stopped"
    ? "Sync Stopped"
    : `Scanner ${job.status}`

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      {/* Schedule notice */}
      {schedule?.enabled && !schedule?.in_window && (
        <div className="text-xs text-amber-400 bg-amber-900/20 border border-amber-800/40 rounded px-2 py-1">
          Outside schedule window ({schedule.start}–{schedule.end}) — sync will start automatically when window opens
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <h3 className={`text-sm font-medium ${paused ? "text-amber-400" : "text-gray-300"}`}>{statusLabel}</h3>
        <div className="flex gap-2">
          {!isActive && (
            <button
              onClick={() => doAction(startGpuRescan)}
              disabled={actionPending}
              className="text-xs px-3 py-1 rounded transition disabled:opacity-50 bg-green-700 hover:bg-green-600 text-white"
            >
              {actionPending ? "..." : "Resync All Images"}
            </button>
          )}
          {isActive && !paused && (
            <button
              onClick={() => doAction(pauseScan)}
              disabled={actionPending}
              className="text-xs px-3 py-1 rounded transition disabled:opacity-50 bg-amber-600 hover:bg-amber-500 text-white"
            >
              Pause
            </button>
          )}
          {isActive && paused && (
            <button
              onClick={() => doAction(resumeScan)}
              disabled={actionPending}
              className="text-xs px-3 py-1 rounded transition disabled:opacity-50 bg-green-600 hover:bg-green-500 text-white"
            >
              Resume
            </button>
          )}
          <button
            onClick={isActive ? handleStop : () => doAction(startScan)}
            disabled={actionPending || stopping}
            className={`text-xs px-3 py-1 rounded transition disabled:opacity-50 ${
              isActive
                ? "bg-red-600 hover:bg-red-700 text-white"
                : "bg-blue-600 hover:bg-blue-700 text-white"
            }`}
          >
            {stopping ? "Stopping..." : actionPending ? "..." : isActive ? "Stop" : "Start Sync"}
          </button>
        </div>
      </div>

      {isListing && (
        <>
          <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
            <div className="bg-blue-600 h-2 rounded-full animate-pulse w-full opacity-50" />
          </div>
          <p className="text-xs text-gray-500">
            {job.total_images > 0
              ? `Found ${job.total_images.toLocaleString()} images so far...`
              : "Checking NAS shares for new images..."}
          </p>
        </>
      )}

      {/* Library Sync */}
      {(p1Active || (job.phase1_total > 0 && isActive)) && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-400 flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-green-500" style={{ opacity: p1Active ? 1 : 0.3 }} />
              Library Sync
            </span>
            <span className="text-xs text-gray-500">
              {job.phase1_done.toLocaleString()} / {job.phase1_total.toLocaleString()}
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
            {p1Indeterminate ? (
              <div className="bg-green-500 h-2 rounded-full animate-pulse w-full opacity-60" />
            ) : (
              <div
                className={`h-2 rounded-full transition-all duration-500 ${p1Active ? "bg-green-500" : "bg-green-500/50"}`}
                style={{ width: `${p1Pct}%` }}
              />
            )}
          </div>
          <p className="text-xs text-gray-600 mt-0.5">
            {p1Indeterminate ? "Scanning files..." : `Thumbnails + XMP Tags — ${p1Pct}%`}
          </p>
        </div>
      )}

      {!isActive && !isListing && job.phase1_total === 0 && job.total_images > 0 && (
        <p className="text-xs text-gray-500">
          Last scan: {job.processed_images.toLocaleString()} / {job.total_images.toLocaleString()} images
        </p>
      )}
    </div>
  )
}
