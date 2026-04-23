import { useEffect, useState, useRef } from "react"
import { getDuplicates, deleteImage, bulkDeleteImages, thumbnailUrl, startPhashScan, getScanStatus } from "../api"

export default function Duplicates() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(new Set())
  const [threshold, setThreshold] = useState(8)
  const [scanning, setScanning] = useState(false)
  const scanningRef = useRef(false)

  // Selection state
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const load = (t = threshold) => {
    setLoading(true)
    getDuplicates(t)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const [anyScanRunning, setAnyScanRunning] = useState(false)

  useEffect(() => {
    const ACTIVE = ["listing", "running", "analyzing", "gpu_rescan", "phash"]
    const interval = setInterval(async () => {
      try {
        const status = await getScanStatus()
        const active = ACTIVE.includes(status?.status)
        setAnyScanRunning(active)
        if (status?.status === "phash") {
          scanningRef.current = true
          setScanning(true)
        } else if (scanningRef.current) {
          scanningRef.current = false
          setScanning(false)
          load()
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  const handleStartScan = async () => {
    try {
      await startPhashScan()
      setScanning(true)
      scanningRef.current = true
    } catch (err) {
      alert(err?.response?.data?.message || "Could not start scan")
    }
  }

  const handleDelete = async (imageId, filename) => {
    if (!window.confirm(`Permanently delete "${filename}" from the NAS?`)) return
    setDeleting((prev) => new Set([...prev, imageId]))
    try {
      await deleteImage(imageId)
      removeFromGroups([imageId])
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to delete image")
    }
    setDeleting((prev) => { const n = new Set(prev); n.delete(imageId); return n })
  }

  const removeFromGroups = (ids) => {
    const idSet = new Set(ids)
    setData((prev) => ({
      ...prev,
      groups: prev.groups
        .map((g) => ({ ...g, images: g.images.filter((img) => !idSet.has(img.id)) }))
        .filter((g) => g.images.length > 1),
    }))
    setSelected((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => next.delete(id))
      return next
    })
  }

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // All non-keep (idx > 0) image ids across all groups
  const allDuplicateIds = () => {
    const groups = data?.groups || []
    return groups.flatMap((g) => g.images.slice(1).map((img) => img.id))
  }

  const selectAllDuplicates = () => setSelected(new Set(allDuplicateIds()))
  const selectNone = () => setSelected(new Set())

  const exitSelectMode = () => {
    setSelectMode(false)
    setSelected(new Set())
  }

  const handleBulkDelete = async () => {
    if (!selected.size) return
    if (!window.confirm(`Permanently delete ${selected.size} image${selected.size !== 1 ? "s" : ""} from the NAS? This cannot be undone.`)) return
    setBulkDeleting(true)
    try {
      await bulkDeleteImages([...selected])
      removeFromGroups([...selected])
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to delete images")
    }
    setBulkDeleting(false)
  }

  const groups = data?.groups || []
  const mode = data?.mode
  const hasPhash = mode === "phash"

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-start justify-between mb-6 flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold text-white">Duplicate Images</h2>
          {hasPhash && (
            <p className="text-xs text-gray-500 mt-0.5">Visual similarity · perceptual hash</p>
          )}
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {hasPhash && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-400 whitespace-nowrap">Sensitivity</label>
              <input
                type="range" min={0} max={20} value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                onMouseUp={() => load(threshold)}
                onTouchEnd={() => load(threshold)}
                className="w-24 accent-blue-500"
              />
              <span className="text-xs text-gray-400 w-4">{threshold}</span>
            </div>
          )}
          {groups.length > 0 && (
            <button
              onClick={() => selectMode ? exitSelectMode() : setSelectMode(true)}
              className={`text-sm px-3 py-1.5 rounded-lg transition ${
                selectMode
                  ? "bg-gray-700 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300"
              }`}
            >
              {selectMode ? "Cancel" : "Select"}
            </button>
          )}
          {scanning ? (
            <div className="text-sm text-blue-400 animate-pulse">Scanning… (progress bar above)</div>
          ) : (
            <div className="flex flex-col items-end gap-1">
              <button
                onClick={handleStartScan}
                disabled={anyScanRunning}
                className="text-sm px-3 py-1.5 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg"
                title={anyScanRunning ? "Another scan is running — stop it first" : undefined}
              >
                {hasPhash ? "Re-scan" : "Scan for Visual Duplicates"}
              </button>
              {anyScanRunning && !scanning && (
                <span className="text-xs text-yellow-400">Another scan is running</span>
              )}
            </div>
          )}
          <button
            onClick={() => load()}
            disabled={loading || scanning}
            className="text-sm px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg disabled:opacity-40"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Selection toolbar */}
      {selectMode && (
        <div className="flex items-center gap-2 sm:gap-3 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 mb-4 flex-wrap">
          <span className="text-sm text-gray-300 font-medium">{selected.size} selected</span>
          <button onClick={selectAllDuplicates} className="text-xs text-blue-400 hover:text-blue-300">
            All duplicates ({allDuplicateIds().length})
          </button>
          {selected.size > 0 && (
            <button onClick={selectNone} className="text-xs text-gray-400 hover:text-gray-300">
              None
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={handleBulkDelete}
            disabled={!selected.size || bulkDeleting}
            className="px-4 py-1.5 bg-red-900/50 hover:bg-red-800 text-red-400 hover:text-red-300 rounded-lg text-sm transition disabled:opacity-30"
          >
            {bulkDeleting ? "Deleting..." : `Delete${selected.size > 0 ? ` (${selected.size})` : ""}`}
          </button>
        </div>
      )}

      {!hasPhash && !loading && (
        <div className="mb-6 px-4 py-3 bg-yellow-900/20 border border-yellow-800/40 rounded-lg text-sm text-yellow-300">
          No perceptual hashes yet. Click <strong>Scan for Visual Duplicates</strong> to analyse your images.
        </div>
      )}

      {loading ? (
        <div className="text-center py-16 text-gray-500">Searching for duplicates...</div>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <p className="text-lg">No duplicates found.</p>
          {hasPhash && <p className="text-sm mt-1 text-gray-600">Try increasing the sensitivity slider.</p>}
        </div>
      ) : (
        <div className="space-y-8">
          <p className="text-sm text-gray-400">{groups.length} duplicate group{groups.length !== 1 ? "s" : ""}</p>
          {groups.map((group) => (
            <div key={group.hash} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-mono text-gray-600">{group.hash.slice(0, 16)}…</span>
                <span className="text-xs text-gray-500">{group.images.length} copies</span>
                {selectMode && (
                  <button
                    onClick={() => {
                      const dupeIds = group.images.slice(1).map((img) => img.id)
                      const allSelected = dupeIds.every((id) => selected.has(id))
                      setSelected((prev) => {
                        const next = new Set(prev)
                        if (allSelected) dupeIds.forEach((id) => next.delete(id))
                        else dupeIds.forEach((id) => next.add(id))
                        return next
                      })
                    }}
                    className="text-xs text-blue-400 hover:text-blue-300 ml-2"
                  >
                    {group.images.slice(1).every((img) => selected.has(img.id)) ? "Deselect group" : "Select group"}
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {group.images.map((img, idx) => {
                  const isKeep = idx === 0
                  const isSelected = selected.has(img.id)
                  return (
                    <div
                      key={img.id}
                      className={`relative bg-gray-800 rounded-lg overflow-hidden border transition-all ${
                        isSelected
                          ? "border-red-500 ring-2 ring-red-500/50"
                          : isKeep
                          ? "border-green-600"
                          : "border-gray-700"
                      }`}
                    >
                      {isKeep && (
                        <div className="absolute top-1 left-1 z-10 px-1.5 py-0.5 bg-green-700 text-white text-[10px] rounded font-medium">
                          Keep
                        </div>
                      )}

                      {/* Checkbox for non-keep images in select mode */}
                      {selectMode && !isKeep && (
                        <div
                          className="absolute top-1 right-1 z-10 cursor-pointer"
                          onClick={() => toggleSelect(img.id)}
                        >
                          <div className={`w-5 h-5 rounded border-2 flex items-center justify-center transition ${
                            isSelected
                              ? "bg-red-500 border-red-500"
                              : "bg-black/50 border-gray-400 hover:border-white"
                          }`}>
                            {isSelected && (
                              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            )}
                          </div>
                        </div>
                      )}

                      <div
                        className={`aspect-square overflow-hidden ${selectMode && !isKeep ? "cursor-pointer" : ""}`}
                        onClick={() => selectMode && !isKeep && toggleSelect(img.id)}
                      >
                        <img
                          src={thumbnailUrl(img.id)}
                          alt={img.filename}
                          className={`w-full h-full object-cover transition-opacity ${isSelected ? "opacity-60" : ""}`}
                          loading="lazy"
                        />
                      </div>
                      <div className="p-2 space-y-1">
                        <p className="text-xs text-gray-300 truncate" title={img.filename}>{img.filename}</p>
                        <p className="text-xs text-gray-600 truncate">{img.source_folder}</p>
                        {img.file_size && (
                          <p className="text-xs text-gray-600">{(img.file_size / 1024).toFixed(0)} KB</p>
                        )}
                      </div>
                      {!selectMode && !isKeep && (
                        <div className="p-2 pt-0">
                          <button
                            onClick={() => handleDelete(img.id, img.filename)}
                            disabled={deleting.has(img.id)}
                            className="w-full text-xs px-2 py-1 bg-red-900/50 hover:bg-red-800 text-red-400 hover:text-red-300 rounded transition disabled:opacity-40"
                          >
                            {deleting.has(img.id) ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
