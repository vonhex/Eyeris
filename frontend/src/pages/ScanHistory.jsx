import { useEffect, useState } from "react"
import { getScanHistory } from "../api"

const STATUS_COLORS = {
  completed: "text-green-400",
  failed: "text-red-400",
  running: "text-blue-400",
  analyzing: "text-blue-400",
  listing: "text-yellow-400",
  pending: "text-gray-400",
}

function fmt(dt) {
  if (!dt) return "—"
  return new Date(dt).toLocaleString()
}

function duration(job) {
  if (!job.started_at) return null
  const end = job.completed_at ? new Date(job.completed_at) : new Date()
  const secs = Math.round((end - new Date(job.started_at)) / 1000)
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}m ${s}s`
}

export default function ScanHistory() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getScanHistory()
      .then(setJobs)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-gray-500">Loading scan history...</div>

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h2 className="text-xl font-semibold text-white mb-6">Scan History</h2>

      {jobs.length === 0 ? (
        <div className="text-center py-16 text-gray-500">No scans run yet.</div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <div key={job.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium capitalize ${STATUS_COLORS[job.status] || "text-gray-400"}`}>
                      {job.status}
                    </span>
                    {job.source_folder && (
                      <span className="text-xs text-gray-500 font-mono">{job.source_folder}</span>
                    )}
                    <span className="text-xs text-gray-600">#{job.id}</span>
                  </div>
                  <div className="text-xs text-gray-500 space-y-0.5">
                    <div>Started: {fmt(job.started_at)}</div>
                    {job.completed_at && <div>Finished: {fmt(job.completed_at)}</div>}
                    {duration(job) && <div>Duration: {duration(job)}</div>}
                  </div>
                  {job.error_message && (
                    <p className="text-xs text-red-400 mt-1">{job.error_message}</p>
                  )}
                </div>

                <div className="text-right text-sm space-y-1">
                  <div className="text-gray-300 font-medium">
                    {job.processed_images} / {job.total_images} images
                  </div>
                  <div className="text-xs text-gray-500 space-y-0.5">
                    {(job.phase1_total > 0 || job.phase1_done > 0) && (
                      <div>Phase 1: {job.phase1_done}/{job.phase1_total}</div>
                    )}
                    {(job.phase2_total > 0 || job.phase2_done > 0) && (
                      <div>Phase 2: {job.phase2_done}/{job.phase2_total}</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Progress bar for completed jobs */}
              {job.total_images > 0 && (
                <div className="mt-3 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      job.status === "completed" ? "bg-green-500" :
                      job.status === "failed" ? "bg-red-500" : "bg-blue-500"
                    }`}
                    style={{ width: `${Math.min(100, (job.processed_images / job.total_images) * 100)}%` }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
