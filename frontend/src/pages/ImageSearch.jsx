import { useState, useCallback, useRef, useEffect } from "react"
import { searxngSearch, searxngDownload, searxngProxyUrl, getSettings } from "../api"

export default function ImageSearch() {
  const [query, setQuery] = useState("")
  const [category, setCategory] = useState("images")
  const [results, setResults] = useState([])
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [shares, setShares] = useState([])
  const [destShare, setDestShare] = useState("")
  const [subfolder, setSubfolder] = useState("web-downloads")
  const [downloading, setDownloading] = useState(false)
  const [downloadResult, setDownloadResult] = useState(null)
  const [expandedIndex, setExpandedIndex] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => {
    getSettings()
      .then((s) => {
        const list = s.smb_shares || []
        setShares(list)
        if (list.length > 0) setDestShare(list[0])
      })
      .catch(() => {})
    inputRef.current?.focus()
  }, [])

  const doSearch = useCallback(async (q, p = 1, cat = category) => {
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    if (p === 1) {
      setResults([])
      setSelected(new Set())
      setDownloadResult(null)
    }
    try {
      const data = await searxngSearch(q.trim(), p, cat)
      setResults((prev) => p === 1 ? data.results : [...prev, ...data.results])
      setHasMore(data.results.length >= 10)
      setPage(p)
      if (p === 1) setExpandedIndex(null)
    } catch (e) {
      setError(e?.response?.data?.detail || "Search failed — is SearXNG reachable?")
    }
    setLoading(false)
  }, [category])

  const handleSubmit = (e) => {
    e.preventDefault()
    doSearch(query, 1)
  }

  const handleCategoryChange = (newCat) => {
    setCategory(newCat)
    if (query.trim()) {
      doSearch(query, 1, newCat)
    }
  }

  const loadMore = () => doSearch(query, page + 1)

  const toggleSelect = (url) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(url)) next.delete(url)
      else next.add(url)
      return next
    })
  }

  const selectAll = () => setSelected(new Set(results.filter(r => r.type === "image").map((r) => r.url)))
  const selectNone = () => setSelected(new Set())

  const handleDownload = async () => {
    if (!selected.size || !destShare) return
    setDownloading(true)
    setDownloadResult(null)
    try {
      const result = await searxngDownload([...selected], destShare, subfolder)
      setDownloadResult(result)
      setSelected(new Set())
    } catch (e) {
      setDownloadResult({ error: e?.response?.data?.detail || "Download failed" })
    }
    setDownloading(false)
  }

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Web Search</h2>
        <div className="flex items-center gap-4">
          <div className="flex bg-gray-900 rounded-lg p-1 border border-gray-800">
            <button
              onClick={() => handleCategoryChange("images")}
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                category === "images" ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Images
            </button>
            <button
              onClick={() => handleCategoryChange("videos")}
              className={`px-3 py-1 text-xs font-medium rounded-md transition ${
                category === "videos" ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Videos
            </button>
          </div>
          <span className="text-xs text-gray-500">via SearXNG</span>
        </div>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search for ${category}...`}
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition disabled:opacity-40"
        >
          {loading && page === 1 ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Selection toolbar */}
      {results.length > 0 && (
        <div className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2 flex-wrap">
          <span className="text-sm text-gray-400">{results.length} results</span>
          <div className="flex gap-2">
            <button onClick={selectAll} className="text-xs text-blue-400 hover:text-blue-300">
              All
            </button>
            {selected.size > 0 && (
              <button onClick={selectNone} className="text-xs text-gray-400 hover:text-gray-300">
                None
              </button>
            )}
          </div>
          <span className="text-sm text-gray-300 font-medium">{selected.size} selected</span>
          <div className="flex-1" />
          {/* Destination picker */}
          <select
            value={destShare}
            onChange={(e) => setDestShare(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300 focus:outline-none focus:border-blue-500"
          >
            {shares.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
            {shares.length === 0 && <option value="">No shares configured</option>}
          </select>
          <input
            type="text"
            value={subfolder}
            onChange={(e) => setSubfolder(e.target.value)}
            placeholder="subfolder"
            className="w-36 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-300 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleDownload}
            disabled={!selected.size || downloading || !destShare}
            className="px-4 py-1.5 bg-green-800 hover:bg-green-700 text-green-300 hover:text-white rounded-lg text-sm transition disabled:opacity-30"
          >
            {downloading ? "Saving…" : `Save to NAS${selected.size > 0 ? ` (${selected.size})` : ""}`}
          </button>
        </div>
      )}

      {/* Download result */}
      {downloadResult && (
        <div className={`rounded-lg px-4 py-3 text-sm border ${
          downloadResult.error
            ? "bg-red-900/40 border-red-700 text-red-300"
            : "bg-green-900/40 border-green-700 text-green-300"
        }`}>
          {downloadResult.error
            ? downloadResult.error
            : <>
                Saved {downloadResult.saved} image{downloadResult.saved !== 1 ? "s" : ""} to{" "}
                <span className="font-mono">{destShare}/{subfolder}</span>
                {downloadResult.errors?.length > 0 && (
                  <span className="text-yellow-400 ml-2">
                    ({downloadResult.errors.length} failed)
                  </span>
                )}
              </>
          }
        </div>
      )}

      {/* Results grid */}
      {results.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2">
          {results.map((r, i) => (
            <SearchResult
              key={`${r.url}-${i}`}
              result={r}
              selected={selected.has(r.url)}
              onToggle={toggleSelect}
              onExpand={() => setExpandedIndex(i)}
            />
          ))}
        </div>
      )}

      {/* Lightbox */}
      {expandedIndex !== null && results[expandedIndex] && (
        <Lightbox
          result={results[expandedIndex]}
          currentIndex={expandedIndex}
          total={results.length}
          results={results}
          selected={selected.has(results[expandedIndex].url)}
          onToggle={toggleSelect}
          onClose={() => setExpandedIndex(null)}
          onPrev={() => setExpandedIndex((i) => Math.max(0, i - 1))}
          onNext={() => setExpandedIndex((i) => Math.min(results.length - 1, i + 1))}
        />
      )}

      {/* Load more */}
      {hasMore && !loading && results.length > 0 && (
        <div className="text-center pt-2">
          <button
            onClick={loadMore}
            className="px-6 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition"
          >
            Load more
          </button>
        </div>
      )}

      {loading && page > 1 && (
        <div className="text-center py-4 text-gray-500 text-sm">Loading…</div>
      )}

      {!loading && results.length === 0 && query && !error && (
        <div className="text-center py-16 text-gray-600">No results found.</div>
      )}

      {results.length === 0 && !query && (
        <div className="text-center py-16 text-gray-700 text-sm">
          Enter a search query to find images.
        </div>
      )}
    </div>
  )
}

function SearchResult({ result, selected, onToggle, onExpand }) {
  const [imgError, setImgError] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const isVideo = result.type === "video"
  const proxyThumb = result.thumbnail ? searxngProxyUrl(result.thumbnail) : null

  return (
    <div
      className={`relative group cursor-pointer rounded-lg overflow-hidden bg-gray-900 border-2 transition ${
        selected ? "border-blue-500" : "border-transparent hover:border-gray-600"
      }`}
      onClick={() => onToggle(result.url)}
      title={result.title || result.source}
    >
      <div className="aspect-square w-full bg-gray-800 relative">
        {proxyThumb && !imgError ? (
          <>
            {!loaded && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-5 h-5 border-2 border-gray-700 border-t-gray-500 rounded-full animate-spin" />
              </div>
            )}
            <img
              src={proxyThumb}
              alt={result.title || ""}
              className={`w-full h-full object-cover transition-opacity ${loaded ? "opacity-100" : "opacity-0"}`}
              onLoad={() => setLoaded(true)}
              onError={() => setImgError(true)}
            />
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 gap-1 px-2">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={isVideo ? "M15 10l4.553-2.276A1 1 0 0121 8.618v7.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" : "M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"} />
            </svg>
            <span className="text-xs text-center truncate w-full">
              {isVideo ? "No preview" : "No preview"}
            </span>
          </div>
        )}

        {/* Video indicators */}
        {isVideo && (
          <>
            <div className="absolute inset-0 flex items-center justify-center bg-black/20">
              <div className="w-8 h-8 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center">
                <svg className="w-4 h-4 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
            </div>
            {result.length && (
              <div className="absolute bottom-1.5 right-1.5 px-1 py-0.5 bg-black/80 rounded text-[10px] text-white font-medium">
                {result.length}
              </div>
            )}
          </>
        )}
      </div>

      {/* Selection overlay */}
      <div className={`absolute inset-0 transition ${selected ? "bg-blue-500/20" : "bg-transparent group-hover:bg-white/5"}`} />

      {/* Expand button */}
      <button
        className="absolute top-1.5 left-1.5 w-6 h-6 bg-black/60 hover:bg-black/80 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition text-white"
        onClick={(e) => { e.stopPropagation(); onExpand() }}
        title="Expand"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
        </svg>
      </button>

      {/* Checkbox indicator */}
      <div className={`absolute top-1.5 right-1.5 w-5 h-5 rounded-full border-2 flex items-center justify-center transition ${
        selected
          ? "bg-blue-500 border-blue-500"
          : "bg-black/40 border-gray-500 opacity-0 group-hover:opacity-100"
      }`}>
        {selected && (
          <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
          </svg>
        )}
      </div>

      {/* Title on hover */}
      {result.title && (
        <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-1.5 py-1 text-xs text-gray-300 truncate opacity-0 group-hover:opacity-100 transition">
          {result.title}
        </div>
      )}
    </div>
  )
}

function Lightbox({ result, currentIndex, total, results, selected, onToggle, onClose, onPrev, onNext }) {
  const isVideo = result.type === "video"
  const proxyFull = result.url && !isVideo ? searxngProxyUrl(result.url) : null
  const [loaded, setLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)
  const touchStartX = useRef(null)
  const pinchDist = useRef(null)
  const lastTap = useRef(0)
  const [scale, setScale] = useState(1)
  const imgContainerRef = useRef(null)

  // Reset load + zoom when result changes
  useEffect(() => {
    setLoaded(false)
    setImgError(false)
    setScale(1)
  }, [result.url])

  // Preload adjacent images so navigation feels instant (skip for videos)
  useEffect(() => {
    if (isVideo) return
    const toPreload = []
    for (let offset = 1; offset <= 2; offset++) {
      if (results[currentIndex + offset] && results[currentIndex + offset].type === "image") toPreload.push(results[currentIndex + offset].url)
      if (results[currentIndex - offset] && results[currentIndex - offset].type === "image") toPreload.push(results[currentIndex - offset].url)
    }
    toPreload.forEach((url) => {
      const img = new window.Image()
      img.src = searxngProxyUrl(url)
    })
  }, [currentIndex, results, isVideo])

  // Keyboard navigation
  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") onClose()
      else if (e.key === "ArrowLeft") onPrev()
      else if (e.key === "ArrowRight") onNext()
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onClose, onPrev, onNext])

  // Pinch-to-zoom (non-passive touchmove)
  useEffect(() => {
    const el = imgContainerRef.current
    if (!el) return
    const onMove = (e) => {
      if (e.touches.length === 2 && pinchDist.current !== null) {
        e.preventDefault()
        const d = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
        setScale((s) => Math.min(Math.max(s * (d / pinchDist.current), 1), 5))
        pinchDist.current = d
      }
    }
    el.addEventListener("touchmove", onMove, { passive: false })
    return () => el.removeEventListener("touchmove", onMove)
  }, [])

  const handleTouchStart = (e) => {
    if (e.touches.length === 2) {
      pinchDist.current = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      )
    } else {
      touchStartX.current = e.touches[0].clientX
    }
  }

  const handleTouchEnd = (e) => {
    if (e.touches.length < 2) pinchDist.current = null
    setScale((s) => (s < 1.05 ? 1 : s))

    // Double-tap reset zoom
    const now = Date.now()
    if (now - lastTap.current < 300) setScale(1)
    lastTap.current = now

    // Swipe only when not zoomed
    if (scale <= 1.05 && touchStartX.current !== null && e.touches.length === 0) {
      const dx = e.changedTouches[0].clientX - touchStartX.current
      touchStartX.current = null
      if (Math.abs(dx) < 40) return
      if (dx < 0) onNext()
      else onPrev()
    } else {
      touchStartX.current = null
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-5xl max-h-[90vh] w-full flex flex-col items-center gap-3"
        onClick={(e) => e.stopPropagation()}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        ref={imgContainerRef}
      >
        {/* Image/Video Container */}
        <div className="relative flex items-center justify-center w-full max-h-[75vh] bg-gray-900 rounded-xl overflow-hidden min-h-[300px] aspect-video">
          {isVideo ? (
            result.iframe_src ? (
              <iframe
                src={result.iframe_src}
                className="w-full h-full border-0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                title={result.title}
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-6 p-12 text-center">
                <div className="w-20 h-20 bg-blue-600/20 text-blue-500 rounded-full flex items-center justify-center">
                  <svg className="w-10 h-10" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
                <div className="space-y-2">
                  <h3 className="text-xl font-medium text-white">{result.title}</h3>
                  <p className="text-gray-400 text-sm max-w-md">{result.source} {result.length ? `• ${result.length}` : ""}</p>
                </div>
                <a
                  href={result.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-full transition shadow-lg shadow-blue-900/20"
                >
                  Open Video on {result.source || "Web"}
                </a>
              </div>
            )
          ) : (
            <>
              {!loaded && !imgError && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-8 h-8 border-2 border-gray-600 border-t-gray-300 rounded-full animate-spin" />
                </div>
              )}
              {!imgError ? (
                <img
                  src={proxyFull}
                  alt={result.title || ""}
                  className={`max-w-full max-h-[75vh] object-contain transition-opacity ${loaded ? "opacity-100" : "opacity-0"}`}
                  style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}
                  onLoad={() => setLoaded(true)}
                  onError={() => setImgError(true)}
                />
              ) : (
                <div className="py-16 text-gray-500 text-sm">Failed to load full image</div>
              )}
            </>
          )}

          {/* Prev button */}
          {currentIndex > 0 && (
            <button
              onClick={(e) => { e.stopPropagation(); onPrev() }}
              className="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/60 hover:bg-black/90 rounded-full flex items-center justify-center text-white transition"
              title="Previous (←)"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}

          {/* Next button */}
          {currentIndex < total - 1 && (
            <button
              onClick={(e) => { e.stopPropagation(); onNext() }}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-black/60 hover:bg-black/90 rounded-full flex items-center justify-center text-white transition"
              title="Next (→)"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 w-full">
          {result.title && (
            <span className="flex-1 text-sm text-gray-300 truncate">{result.title}</span>
          )}
          <span className="text-xs text-gray-600">{currentIndex + 1} / {total}</span>
          {result.source && (
            <span className="text-xs text-gray-500 truncate">{result.source} {result.length ? `(${result.length})` : ""}</span>
          )}
          {!isVideo && (
            <button
              onClick={() => onToggle(result.url)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${
                selected
                  ? "bg-blue-600 hover:bg-blue-500 text-white"
                  : "bg-gray-700 hover:bg-gray-600 text-gray-200"
              }`}
            >
              {selected ? "Selected" : "Select"}
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
