import { useEffect, useState, useCallback } from "react"
import { getImages, bulkDeleteImages, thumbnailUrl } from "../api"

const BLUR_TAGS = ["blurry", "blur", "blurred", "out-of-focus", "motion blur"]
const PAGE_SIZE = 100

export default function Blurry() {
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(new Set())
  const [deleting, setDeleting] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [activeTag, setActiveTag] = useState("blurry")
  const [tagCounts, setTagCounts] = useState({})

  const load = useCallback(async (tag, p = 1, replace = true) => {
    setLoading(true)
    try {
      const data = await getImages({ tag, page_size: PAGE_SIZE, page: p, sort: "date_added_desc" })
      const items = data.images ?? data
      if (replace) {
        setImages(items)
        setSelected(new Set())
      } else {
        setImages((prev) => [...prev, ...items])
      }
      setHasMore(items.length === PAGE_SIZE)
      setPage(p)
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }, [])

  // Load counts for all blur tags on mount
  useEffect(() => {
    Promise.all(
      BLUR_TAGS.map((tag) =>
        getImages({ tag, page_size: 1, page: 1 })
          .then((d) => [tag, d.total ?? (d.images ?? d).length])
          .catch(() => [tag, 0])
      )
    ).then((entries) => setTagCounts(Object.fromEntries(entries)))
  }, [])

  useEffect(() => { load(activeTag) }, [activeTag, load])

  const switchTag = (tag) => {
    if (tag === activeTag) return
    setActiveTag(tag)
  }

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const selectAll = () => setSelected(new Set(images.map((i) => i.id)))
  const selectNone = () => setSelected(new Set())

  const handleDeleteSelected = async () => {
    if (!selected.size) return
    if (!window.confirm(`Permanently delete ${selected.size} image${selected.size !== 1 ? "s" : ""} from the NAS?`)) return
    setDeleting(true)
    try {
      await bulkDeleteImages([...selected])
      const removed = new Set(selected)
      setImages((prev) => prev.filter((i) => !removed.has(i.id)))
      setTagCounts((prev) => ({ ...prev, [activeTag]: Math.max(0, (prev[activeTag] ?? 0) - removed.size) }))
      setSelected(new Set())
    } catch (e) {
      alert(e?.response?.data?.detail || "Delete failed")
    }
    setDeleting(false)
  }

  const totalBlurry = BLUR_TAGS.reduce((sum, t) => sum + (tagCounts[t] ?? 0), 0)

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-white">Blurry Photos</h2>
          <p className="text-xs text-gray-500 mt-0.5">{totalBlurry} images tagged by A-EYE across all blur categories</p>
        </div>
        {selected.size > 0 && (
          <button
            onClick={handleDeleteSelected}
            disabled={deleting}
            className="px-4 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white text-sm font-medium rounded-lg transition"
          >
            {deleting ? "Deleting…" : `Delete ${selected.size} selected`}
          </button>
        )}
      </div>

      {/* Tag tabs */}
      <div className="flex gap-2 flex-wrap">
        {BLUR_TAGS.map((tag) => (
          <button
            key={tag}
            onClick={() => switchTag(tag)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              activeTag === tag
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700"
            }`}
          >
            {tag}
            {tagCounts[tag] != null && (
              <span className={`ml-1.5 text-xs ${activeTag === tag ? "text-blue-200" : "text-gray-500"}`}>
                {tagCounts[tag]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Toolbar */}
      {images.length > 0 && (
        <div className="flex items-center gap-3 bg-gray-900 border border-gray-800 rounded-lg px-4 py-2">
          <button onClick={selectAll} className="text-xs text-blue-400 hover:text-blue-300">Select All</button>
          {selected.size > 0 && (
            <button onClick={selectNone} className="text-xs text-gray-400 hover:text-gray-300">None</button>
          )}
          <span className="text-sm text-gray-400">{selected.size} selected · {images.length} shown</span>
        </div>
      )}

      {/* Grid */}
      {loading && images.length === 0 ? (
        <div className="text-center py-16 text-gray-500 text-sm">Loading…</div>
      ) : images.length === 0 ? (
        <div className="text-center py-16 text-gray-500">No images tagged <span className="text-gray-300">"{activeTag}"</span></div>
      ) : (
        <>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-2">
            {images.map((img) => {
              const isSelected = selected.has(img.id)
              return (
                <div
                  key={img.id}
                  onClick={() => toggleSelect(img.id)}
                  className={`relative group cursor-pointer rounded-lg overflow-hidden border-2 transition ${
                    isSelected ? "border-red-500" : "border-transparent hover:border-gray-600"
                  }`}
                >
                  <div className="aspect-square bg-gray-800">
                    <img
                      src={thumbnailUrl(img.id)}
                      alt={img.filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  </div>
                  <div className={`absolute inset-0 transition ${isSelected ? "bg-red-500/25" : "bg-transparent group-hover:bg-white/5"}`} />
                  <div className={`absolute top-1.5 right-1.5 w-5 h-5 rounded-full border-2 flex items-center justify-center transition ${
                    isSelected ? "bg-red-500 border-red-500" : "bg-black/40 border-gray-500 opacity-0 group-hover:opacity-100"
                  }`}>
                    {isSelected && (
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {hasMore && (
            <div className="text-center pt-2">
              <button
                onClick={() => load(activeTag, page + 1, false)}
                disabled={loading}
                className="px-6 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition disabled:opacity-40"
              >
                {loading ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
