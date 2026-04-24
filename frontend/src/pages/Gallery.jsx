import { useEffect, useState, useCallback, useRef } from "react"
import { useSearchParams } from "react-router-dom"
import { getImages, getImageIds, bulkDeleteImages, bulkDownloadImages, bulkUpdateTags, getTags } from "../api"
import ImageGrid from "../components/ImageGrid"
import FilterSidebar from "../components/FilterSidebar"
import SearchBar from "../components/SearchBar"
import ScanProgress from "../components/ScanProgress"

const SCROLL_KEY = "gallery_scroll"
const IMAGES_KEY = "gallery_images"
const TOTAL_KEY = "gallery_total"

export default function Gallery() {
  const [searchParams, setSearchParams] = useSearchParams()

  const folder = searchParams.get("folder") || null
  const tag = searchParams.get("tag") || null
  const category = searchParams.get("category") || null
  const search = searchParams.get("search") || ""
  const sort = searchParams.get("sort") || "date_taken_desc"
  const clusterIdParam = searchParams.get("cluster_id")
  const cluster_id = clusterIdParam !== null ? parseInt(clusterIdParam, 10) : null
  const favoriteParam = searchParams.get("favorite")
  const favorite = favoriteParam === "true" ? true : null
  const date_from = searchParams.get("date_from") || null
  const date_to = searchParams.get("date_to") || null
  const location = searchParams.get("location") || null
  const camera = searchParams.get("camera") || null
  const quality_issue = searchParams.get("quality_issue") || null
  const has_gps = searchParams.get("has_gps") === "true" ? true : null
  const untagged = searchParams.get("untagged") === "true" ? true : null

  const filters = { folder, tag, category, search, cluster_id, favorite, date_from, date_to, location, camera, quality_issue, has_gps, untagged }
  const filtersKey = JSON.stringify({ folder, tag, category, search, sort, cluster_id, favorite, date_from, date_to, location, camera, quality_issue, has_gps, untagged })

  const [images, setImages] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [deleting, setDeleting] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [bulkTagOpen, setBulkTagOpen] = useState(false)
  const prevFiltersKey = useRef(filtersKey)

  useEffect(() => {
    const savedScroll = sessionStorage.getItem(SCROLL_KEY)
    const savedImages = sessionStorage.getItem(IMAGES_KEY)
    const savedTotal = sessionStorage.getItem(TOTAL_KEY)
    if (savedScroll && savedImages) {
      try {
        const imgs = JSON.parse(savedImages)
        if (imgs.length > 0) {
          setImages(imgs)
          setTotal(parseInt(savedTotal, 10) || imgs.length)
          setPage(Math.ceil(imgs.length / 48))
          setLoading(false)
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              window.scrollTo(0, parseInt(savedScroll, 10))
            })
          })
        }
      } catch {}
    }
    sessionStorage.removeItem(SCROLL_KEY)
    sessionStorage.removeItem(IMAGES_KEY)
    sessionStorage.removeItem(TOTAL_KEY)
  }, [])

  useEffect(() => {
    if (prevFiltersKey.current !== filtersKey) {
      prevFiltersKey.current = filtersKey
      setPage(1)
      setImages([])
      setTotal(0)
    }
  }, [filtersKey])

  useEffect(() => {
    const handleClick = (e) => {
      const link = e.target.closest("a[href^='/image/']")
      if (link) {
        sessionStorage.setItem(SCROLL_KEY, String(window.scrollY))
        sessionStorage.setItem(IMAGES_KEY, JSON.stringify(images))
        sessionStorage.setItem(TOTAL_KEY, String(total))
        const activeFilters = { sort }
        if (folder) activeFilters.folder = folder
        if (tag) activeFilters.tag = tag
        if (category) activeFilters.category = category
        if (search) activeFilters.search = search
        if (cluster_id !== null) activeFilters.cluster_id = cluster_id
        if (favorite) activeFilters.favorite = favorite
        if (date_from) activeFilters.date_from = date_from
        if (date_to) activeFilters.date_to = date_to
        if (location) activeFilters.location = location
        if (camera) activeFilters.camera = camera
        if (quality_issue) activeFilters.quality_issue = quality_issue
        if (has_gps !== null) activeFilters.has_gps = has_gps
        sessionStorage.setItem("gallery_filters", JSON.stringify(activeFilters))
      }
    }
    document.addEventListener("click", handleClick)
    return () => document.removeEventListener("click", handleClick)
  }, [images, total, folder, tag, category, search, sort, cluster_id, favorite, date_from, date_to])

  const fetchRef = useRef(0)
  useEffect(() => {
    const id = ++fetchRef.current
    const doFetch = async () => {
      setLoading(true)
      try {
        const params = { page, page_size: 48, sort }
        if (folder) params.folder = folder
        if (tag) params.tag = tag
        if (category) params.category = category
        if (search) params.search = search
        if (cluster_id !== null) params.cluster_id = cluster_id
        if (favorite) params.favorite = true
        if (date_from) params.date_from = date_from
        if (date_to) params.date_to = date_to
        if (location) params.location = location
        if (camera) params.camera = camera
        if (quality_issue) params.quality_issue = quality_issue
        if (has_gps !== null) params.has_gps = has_gps
        if (untagged) params.untagged = true

        const data = await getImages(params)
        if (id !== fetchRef.current) return

        if (page === 1) {
          setImages(data.images)
        } else {
          setImages((prev) => [...prev, ...data.images])
        }
        setTotal(data.total)
      } catch (err) {
        console.error("Failed to fetch images:", err)
      }
      if (id === fetchRef.current) setLoading(false)
    }
    doFetch()
  }, [page, filtersKey])

  const updateParams = useCallback((updates) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === "" || value === undefined || value === false) {
          next.delete(key)
        } else {
          next.set(key, String(value))
        }
      }
      if (next.get("sort") === "date_taken_desc") next.delete("sort")
      return next
    }, { replace: true })
  }, [setSearchParams])

  const handleFilterChange = useCallback((newFilters) => {
    updateParams({
      folder: newFilters.folder,
      tag: newFilters.tag,
      category: newFilters.category,
      search: newFilters.search,
      favorite: newFilters.favorite || null,
      date_from: newFilters.date_from || null,
      date_to: newFilters.date_to || null,
      location: newFilters.location,
      camera: newFilters.camera,
      has_gps: newFilters.has_gps,
    })
  }, [updateParams])

  const handleSearch = useCallback((value) => {
    updateParams({ search: value })
  }, [updateParams])

  const handleSortChange = useCallback((value) => {
    updateParams({ sort: value })
  }, [updateParams])

  const lastSelectedIndex = useRef(null)

  const toggleSelect = useCallback((id, shiftKey) => {
    const currentIndex = images.findIndex((img) => img.id === id)
    if (shiftKey && lastSelectedIndex.current !== null && currentIndex !== -1) {
      const start = Math.min(lastSelectedIndex.current, currentIndex)
      const end = Math.max(lastSelectedIndex.current, currentIndex)
      setSelected((prev) => {
        const next = new Set(prev)
        for (let i = start; i <= end; i++) next.add(images[i].id)
        return next
      })
    } else {
      setSelected((prev) => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
    }
    if (currentIndex !== -1) lastSelectedIndex.current = currentIndex
  }, [images])

  const handleLongPress = useCallback((id) => {
    if (!selectMode) {
      setSelectMode(true)
    }
    setSelected((prev) => {
      const next = new Set(prev)
      next.add(id)
      return next
    })
  }, [selectMode])

  const selectAll = async () => {
    const params = { sort }
    if (folder) params.folder = folder
    if (tag) params.tag = tag
    if (category) params.category = category
    if (search) params.search = search
    if (cluster_id !== null) params.cluster_id = cluster_id
    if (favorite) params.favorite = true
    if (date_from) params.date_from = date_from
    if (date_to) params.date_to = date_to
    if (untagged) params.untagged = true

    const data = await getImageIds(params)
    setSelected(new Set(data.ids))
  }
  const selectNone = () => setSelected(new Set())

  const handleBulkDownload = async () => {
    if (!selected.size) return
    setDownloading(true)
    try {
      const blob = await bulkDownloadImages([...selected])
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "images.zip"
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      alert("Failed to download images")
    }
    setDownloading(false)
  }

  const handleBulkDelete = async () => {
    if (!selected.size) return
    if (!window.confirm(`Permanently delete ${selected.size} image${selected.size > 1 ? "s" : ""} from the NAS? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await bulkDeleteImages([...selected])
      setImages((prev) => prev.filter((img) => !selected.has(img.id)))
      setTotal((prev) => prev - selected.size)
      setSelected(new Set())
    } catch (err) {
      console.error(err)
      alert("Failed to delete some images")
    }
    setDeleting(false)
  }

  const exitSelectMode = () => {
    setSelectMode(false)
    setSelected(new Set())
  }

  const hasMore = images.length < total
  const sentinelRef = useRef(null)

  useEffect(() => {
    if (!sentinelRef.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          setPage((p) => p + 1)
        }
      },
      { rootMargin: "400px" }
    )
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [hasMore, loading])

  return (
    <div className="flex gap-4 p-3 sm:gap-6 sm:p-6">
      <FilterSidebar filters={filters} onFilterChange={handleFilterChange} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 min-w-0 space-y-3 sm:space-y-4">
        <div className="flex gap-2 sm:gap-4 items-start flex-wrap">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden px-2.5 py-2 bg-gray-800 text-gray-400 hover:text-white rounded-lg"
            aria-label="Filters"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          </button>
          <div className="flex-1 min-w-[120px]">
            <SearchBar value={search} onSearch={handleSearch} />
          </div>
          <select
            value={sort}
            onChange={(e) => handleSortChange(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded-lg px-2 sm:px-3 py-1.5 text-sm text-gray-300 focus:outline-none focus:border-blue-500"
          >
            <option value="date_taken_desc">Date Taken (newest)</option>
            <option value="date_taken_asc">Date Taken (oldest)</option>
            <option value="date_added_desc">Date Added (newest)</option>
            <option value="date_added_asc">Date Added (oldest)</option>
            <option value="filename_asc">Filename (A-Z)</option>
            <option value="filename_desc">Filename (Z-A)</option>
            <option value="random">Random</option>
          </select>
          <button
            onClick={() => selectMode ? exitSelectMode() : setSelectMode(true)}
            className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-sm transition whitespace-nowrap ${
              selectMode
                ? "bg-gray-700 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300"
            }`}
          >
            {selectMode ? "Cancel" : "Select"}
          </button>
          {favorite && (
            <span className="text-yellow-400 text-sm pt-2">★ Favorites</span>
          )}
          <div className="text-sm text-gray-500 whitespace-nowrap pt-2 hidden sm:block">
            {total} images
          </div>
        </div>

        {selectMode && (
          <div className="flex items-center gap-2 sm:gap-3 bg-gray-900 border border-gray-800 rounded-lg px-3 sm:px-4 py-2 flex-wrap">
            <span className="text-sm text-gray-300 font-medium">
              {selected.size} selected
            </span>
            <button onClick={selectAll} className="text-xs text-blue-400 hover:text-blue-300">
              All ({total})
            </button>
            {selected.size > 0 && (
              <button onClick={selectNone} className="text-xs text-gray-400 hover:text-gray-300">
                None
              </button>
            )}
            <div className="flex-1" />
            {selected.size > 0 && (
              <button
                onClick={() => setBulkTagOpen(true)}
                className="px-3 sm:px-4 py-1.5 bg-purple-900/50 hover:bg-purple-800 text-purple-400 hover:text-purple-300 rounded-lg text-sm transition"
              >
                Tags ({selected.size})
              </button>
            )}
            <button
              onClick={handleBulkDownload}
              disabled={!selected.size || downloading}
              className="px-3 sm:px-4 py-1.5 bg-blue-900/50 hover:bg-blue-800 text-blue-400 hover:text-blue-300 rounded-lg text-sm transition disabled:opacity-30"
            >
              {downloading ? "..." : `Download${selected.size > 0 ? ` (${selected.size})` : ""}`}
            </button>
            <button
              onClick={handleBulkDelete}
              disabled={!selected.size || deleting}
              className="px-3 sm:px-4 py-1.5 bg-red-900/50 hover:bg-red-800 text-red-400 hover:text-red-300 rounded-lg text-sm transition disabled:opacity-30"
            >
              {deleting ? "..." : `Delete${selected.size > 0 ? ` (${selected.size})` : ""}`}
            </button>
          </div>
        )}

        <ScanProgress />
        <ImageGrid
          images={images}
          loading={loading && page === 1}
          selectMode={selectMode}
          selected={selected}
          onToggleSelect={toggleSelect}
          onLongPress={handleLongPress}
        />

        <div ref={sentinelRef} className="h-1" />
        {hasMore && loading && (
          <div className="text-center py-4 text-gray-500 text-sm">Loading more...</div>
        )}
      </div>

      {bulkTagOpen && (
        <BulkTagModal
          selectedIds={[...selected]}
          onClose={() => setBulkTagOpen(false)}
          onDone={() => {
            setBulkTagOpen(false)
            // Refresh images to show updated tags
            setPage(1)
            setImages([])
          }}
        />
      )}
    </div>
  )
}

function BulkTagModal({ selectedIds, onClose, onDone }) {
  const [allTags, setAllTags] = useState([])
  const [addInput, setAddInput] = useState("")
  const [toAdd, setToAdd] = useState([])
  const [toRemove, setToRemove] = useState([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getTags().then(setAllTags).catch(() => {})
  }, [])

  const addTag = (name) => {
    const t = name.trim().toLowerCase()
    if (t && !toAdd.includes(t)) setToAdd((p) => [...p, t])
    setAddInput("")
  }

  const removeToAdd = (t) => setToAdd((p) => p.filter((x) => x !== t))
  const toggleRemove = (name) => setToRemove((p) => p.includes(name) ? p.filter((x) => x !== name) : [...p, name])

  const handleSave = async () => {
    setSaving(true)
    try {
      await bulkUpdateTags(selectedIds, toAdd, toRemove)
      onDone()
    } catch (err) {
      console.error(err)
      alert("Failed to update tags")
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-5 w-full max-w-md space-y-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-white font-semibold">Bulk Edit Tags — {selectedIds.length} images</h3>

        {/* Add tags */}
        <div>
          <label className="text-xs text-gray-400 block mb-1">Add tags</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={addInput}
              onChange={(e) => setAddInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addTag(addInput) }}
              placeholder="Type a tag and press Enter"
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={() => addTag(addInput)}
              className="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white rounded text-sm"
            >Add</button>
          </div>
          {toAdd.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {toAdd.map((t) => (
                <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 bg-blue-700 text-white rounded-full">
                  +{t}
                  <button onClick={() => removeToAdd(t)} className="hover:text-blue-200">×</button>
                </span>
              ))}
            </div>
          )}
          {/* Quick-add from existing tags */}
          {allTags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2 max-h-28 overflow-y-auto">
              {allTags.filter(t => !toAdd.includes(t.name)).slice(0, 40).map((t) => (
                <button key={t.id} onClick={() => setToAdd(p => p.includes(t.name) ? p : [...p, t.name])}
                  className="text-xs px-2 py-0.5 bg-gray-800 text-gray-400 hover:bg-gray-700 rounded-full">
                  {t.name}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Remove tags */}
        {allTags.length > 0 && (
          <div>
            <label className="text-xs text-gray-400 block mb-1">Remove tags</label>
            <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto">
              {allTags.slice(0, 40).map((t) => (
                <button
                  key={t.id}
                  onClick={() => toggleRemove(t.name)}
                  className={`text-xs px-2 py-0.5 rounded-full transition ${
                    toRemove.includes(t.name)
                      ? "bg-red-700 text-white"
                      : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                  }`}
                >
                  {toRemove.includes(t.name) ? `–${t.name}` : t.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onClose} className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving || (!toAdd.length && !toRemove.length)}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm disabled:opacity-40"
          >
            {saving ? "Saving..." : "Apply"}
          </button>
        </div>
      </div>
    </div>
  )
}
