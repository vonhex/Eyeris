import { useEffect, useState, useMemo, useCallback, useRef } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import { getImage, getImages, fullImageUrl, updateImageCategory, getCategories, deleteImage, setImageFavorite } from "../api"
import TagEditor from "../components/TagEditor"

const SENTIMENT_COLORS = {
  happy: "bg-yellow-500", excited: "bg-orange-500", funny: "bg-amber-500",
  peaceful: "bg-green-500", romantic: "bg-pink-500", nostalgic: "bg-purple-500",
  neutral: "bg-gray-500", energetic: "bg-red-500", dramatic: "bg-indigo-500",
  sad: "bg-blue-500", tense: "bg-red-700", lonely: "bg-slate-500",
}

const IMAGES_KEY = "gallery_images"
const FILTERS_KEY = "gallery_filters"
const TOTAL_KEY = "gallery_total"

export default function ImageDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [image, setImage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [categories, setCategories] = useState([])
  const [togglingFav, setTogglingFav] = useState(false)
  const fetchingMore = useRef(false)

  // Pinch-to-zoom state
  const imgRef = useRef(null)
  const containerRef = useRef(null)
  const [scale, setScale] = useState(1)
  const lastDist = useRef(null)
  const lastTap = useRef(0)

  const getCachedImages = () => {
    try {
      const raw = sessionStorage.getItem(IMAGES_KEY)
      return raw ? JSON.parse(raw) : []
    } catch { return [] }
  }

  const getCachedTotal = () => {
    try {
      return parseInt(sessionStorage.getItem(TOTAL_KEY), 10) || 0
    } catch { return 0 }
  }

  const fetchMoreImages = useCallback(async () => {
    if (fetchingMore.current) return null
    fetchingMore.current = true
    try {
      const imgs = getCachedImages()
      const cachedTotal = getCachedTotal()
      if (imgs.length >= cachedTotal) return null

      const nextPage = Math.floor(imgs.length / 48) + 1
      let filters = {}
      try {
        const raw = sessionStorage.getItem(FILTERS_KEY)
        if (raw) filters = JSON.parse(raw)
      } catch {}

      const params = { page: nextPage, page_size: 48, ...filters }
      const data = await getImages(params)
      if (data.images.length > 0) {
        const updated = [...imgs, ...data.images]
        sessionStorage.setItem(IMAGES_KEY, JSON.stringify(updated))
        sessionStorage.setItem(TOTAL_KEY, String(data.total))
        return updated
      }
    } catch (err) {
      console.error("Failed to fetch more images:", err)
    } finally {
      fetchingMore.current = false
    }
    return null
  }, [])

  const { prevId, nextId, position, total, atEnd } = useMemo(() => {
    const imgs = getCachedImages()
    const cachedTotal = getCachedTotal()
    if (imgs.length > 0) {
      const idx = imgs.findIndex((img) => String(img.id) === String(id))
      if (idx !== -1) {
        return {
          prevId: idx > 0 ? imgs[idx - 1].id : null,
          nextId: idx < imgs.length - 1 ? imgs[idx + 1].id : null,
          position: idx + 1,
          total: cachedTotal || imgs.length,
          atEnd: idx === imgs.length - 1 && imgs.length < cachedTotal,
        }
      }
    }
    return { prevId: null, nextId: null, position: null, total: null, atEnd: false }
  }, [id])

  const goNext = useCallback(async () => {
    if (nextId) {
      navigate(`/image/${nextId}`, { replace: true })
    } else if (atEnd) {
      const updated = await fetchMoreImages()
      if (updated) {
        const idx = updated.findIndex((img) => String(img.id) === String(id))
        if (idx !== -1 && idx < updated.length - 1) {
          navigate(`/image/${updated[idx + 1].id}`, { replace: true })
        }
      }
    }
  }, [nextId, atEnd, id, navigate, fetchMoreImages])

  const goPrev = useCallback(() => {
    if (prevId) navigate(`/image/${prevId}`, { replace: true })
  }, [prevId, navigate])

  useEffect(() => {
    const handleKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return
      if (e.key === "ArrowLeft") goPrev()
      else if (e.key === "ArrowRight") goNext()
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [goNext, goPrev])

  // Pinch-to-zoom touch events (non-passive so we can preventDefault)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onTouchStart = (e) => {
      if (e.touches.length === 2) {
        lastDist.current = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
      }
    }

    const onTouchMove = (e) => {
      if (e.touches.length === 2 && lastDist.current !== null) {
        e.preventDefault()
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
        const ratio = dist / lastDist.current
        setScale((s) => Math.min(Math.max(s * ratio, 1), 5))
        lastDist.current = dist
      }
    }

    const onTouchEnd = (e) => {
      if (e.touches.length < 2) lastDist.current = null
      // Snap back if barely zoomed
      setScale((s) => (s < 1.05 ? 1 : s))

      // Double-tap to reset zoom
      const now = Date.now()
      if (now - lastTap.current < 300) {
        setScale(1)
      }
      lastTap.current = now
    }

    el.addEventListener("touchstart", onTouchStart, { passive: true })
    el.addEventListener("touchmove", onTouchMove, { passive: false })
    el.addEventListener("touchend", onTouchEnd, { passive: true })
    return () => {
      el.removeEventListener("touchstart", onTouchStart)
      el.removeEventListener("touchmove", onTouchMove)
      el.removeEventListener("touchend", onTouchEnd)
    }
  }, [])

  const fetchImage = async () => {
    setLoading(true)
    try {
      const data = await getImage(id)
      setImage(data)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchImage()
    setScale(1)
  }, [id])
  useEffect(() => { getCategories().then(setCategories).catch(() => {}) }, [])

  const handleToggleFavorite = async () => {
    if (!image) return
    setTogglingFav(true)
    try {
      const result = await setImageFavorite(id, !image.favorite)
      setImage((prev) => ({ ...prev, favorite: result.favorite }))
    } catch (err) {
      console.error(err)
    }
    setTogglingFav(false)
  }

  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    if (!window.confirm(`Permanently delete "${image?.filename}" from the NAS? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await deleteImage(id)
      try {
        const raw = sessionStorage.getItem(IMAGES_KEY)
        if (raw) {
          const imgs = JSON.parse(raw)
          const filtered = imgs.filter((img) => String(img.id) !== String(id))
          sessionStorage.setItem(IMAGES_KEY, JSON.stringify(filtered))
          const cachedTotal = parseInt(sessionStorage.getItem(TOTAL_KEY), 10) || 0
          if (cachedTotal > 0) sessionStorage.setItem(TOTAL_KEY, String(cachedTotal - 1))
        }
      } catch {}
      if (nextId) navigate(`/image/${nextId}`, { replace: true })
      else if (prevId) navigate(`/image/${prevId}`, { replace: true })
      else navigate("/", { replace: true })
    } catch (err) {
      console.error(err)
      alert("Failed to delete image")
    }
    setDeleting(false)
  }

  const handleCategoryChange = async (cat) => {
    try {
      await updateImageCategory(id, cat)
      await fetchImage()
    } catch (err) {
      console.error(err)
    }
  }

  if (loading) return <div className="p-6 text-gray-500">Loading...</div>
  if (!image) return <div className="p-6 text-gray-500">Image not found</div>

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => navigate(-1)}
          className="text-blue-500 hover:text-blue-400 text-sm"
        >
          &larr; Back
        </button>

        <div className="flex items-center gap-2">
          {position && total && (
            <span className="text-xs text-gray-500 mr-2">{position} / {total}</span>
          )}
          <button
            onClick={goPrev}
            disabled={!prevId}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-gray-800 text-gray-300 rounded-lg transition text-sm"
          >
            &larr; Prev
          </button>
          <button
            onClick={goNext}
            disabled={!nextId && !atEnd}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-gray-800 text-gray-300 rounded-lg transition text-sm"
          >
            Next &rarr;
          </button>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="lg:flex-1 relative" ref={containerRef}>
          <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800">
            <img
              ref={imgRef}
              src={fullImageUrl(image.id)}
              alt={image.filename}
              className="w-full h-auto max-h-[75vh] object-contain transition-transform duration-100"
              style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}
            />
          </div>
          {scale > 1 && (
            <div className="absolute bottom-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
              {Math.round(scale * 100)}% · double-tap to reset
            </div>
          )}
          {prevId && (
            <button
              onClick={goPrev}
              className="absolute left-0 top-0 w-1/4 h-full opacity-0 hover:opacity-100 flex items-center justify-start pl-2 cursor-pointer"
              title="Previous (Left Arrow)"
            >
              <span className="bg-black/50 text-white rounded-full w-10 h-10 flex items-center justify-center text-lg">&larr;</span>
            </button>
          )}
          {(nextId || atEnd) && (
            <button
              onClick={goNext}
              className="absolute right-0 top-0 w-1/4 h-full opacity-0 hover:opacity-100 flex items-center justify-end pr-2 cursor-pointer"
              title="Next (Right Arrow)"
            >
              <span className="bg-black/50 text-white rounded-full w-10 h-10 flex items-center justify-center text-lg">&rarr;</span>
            </button>
          )}
        </div>

        <div className="lg:w-80 space-y-4">
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 space-y-4">
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-lg font-medium text-white break-all flex-1">{image.filename}</h2>
              <button
                onClick={handleToggleFavorite}
                disabled={togglingFav}
                title={image.favorite ? "Remove from favorites" : "Add to favorites"}
                className={`text-2xl shrink-0 transition ${image.favorite ? "text-yellow-400" : "text-gray-600 hover:text-yellow-400"}`}
              >
                {image.favorite ? "★" : "☆"}
              </button>
            </div>

            {image.ai_description && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Description</h3>
                <p className="text-sm text-gray-300">{image.ai_description}</p>
              </div>
            )}

            {image.faces && image.faces.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  People Detected ({image.faces.length})
                </h3>
                <div className="space-y-2">
                  {image.faces.map((face, i) => (
                    <div key={face.id || i} className="bg-gray-800 rounded p-2 text-xs space-y-1">
                      {face.person_name && (
                        <p className="text-blue-400 font-medium">{face.person_name}</p>
                      )}
                      <p className="text-gray-300">{face.description}</p>
                      <div className="flex gap-3 text-gray-500">
                        {face.estimated_age && <span>Age: {face.estimated_age}</span>}
                        {face.gender && <span className="capitalize">{face.gender}</span>}
                        {face.position && <span className="capitalize">{face.position}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {image.album && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Album</h3>
                <Link to={`/albums/${encodeURIComponent(image.album)}`} className="text-sm text-blue-400 hover:text-blue-300">
                  {image.album}
                </Link>
              </div>
            )}

            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Tags</h3>
              <TagEditor imageId={image.id} tags={image.tags} onUpdate={fetchImage} />
            </div>

            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Category</h3>
              <div className="flex flex-wrap gap-1.5">
                {categories.map((cat) => {
                  const isActive = image.categories.some((c) => c.category_name === cat.name)
                  return (
                    <button
                      key={cat.name}
                      onClick={() => handleCategoryChange(cat.name)}
                      className={`text-xs px-2 py-1 rounded-full transition ${
                        isActive ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                      }`}
                    >
                      {cat.name}
                    </button>
                  )
                })}
              </div>
            </div>

            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Details</h3>
              <dl className="text-xs space-y-1">
                <div className="flex justify-between">
                  <dt className="text-gray-500">Source</dt>
                  <dd className="text-gray-300">{image.source_folder}</dd>
                </div>
                {image.width && image.height && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Dimensions</dt>
                    <dd className="text-gray-300">{image.width} x {image.height}</dd>
                  </div>
                )}
                {image.file_size && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Size</dt>
                    <dd className="text-gray-300">{(image.file_size / 1024 / 1024).toFixed(1)} MB</dd>
                  </div>
                )}
                {image.date_taken && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Date Taken</dt>
                    <dd className="text-gray-300">{new Date(image.date_taken).toLocaleDateString()}</dd>
                  </div>
                )}
                {image.location_name && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Location</dt>
                    <dd className="text-gray-300">{image.location_name}</dd>
                  </div>
                )}
                {image.camera_model && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">Camera</dt>
                    <dd className="text-gray-300 text-right max-w-[60%]">{image.camera_model}</dd>
                  </div>
                )}
                {image.gps_lat != null && image.gps_lon != null && (
                  <div className="flex justify-between">
                    <dt className="text-gray-500">GPS</dt>
                    <dd className="text-gray-300">
                      <a
                        href={`https://www.openstreetmap.org/?mlat=${image.gps_lat}&mlon=${image.gps_lon}&zoom=15`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300"
                      >
                        {image.gps_lat.toFixed(4)}, {image.gps_lon.toFixed(4)}
                      </a>
                    </dd>
                  </div>
                )}
                {image.quality_flags && (() => {
                  try {
                    const qf = JSON.parse(image.quality_flags)
                    const issues = []
                    if (qf.blur) issues.push("Blurry")
                    if (qf.overexposed) issues.push("Overexposed")
                    if (qf.underexposed) issues.push("Underexposed")
                    if (issues.length === 0) return null
                    return (
                      <div className="flex justify-between">
                        <dt className="text-gray-500">Quality</dt>
                        <dd className="text-amber-400 text-right">{issues.join(", ")}</dd>
                      </div>
                    )
                  } catch { return null }
                })()}
                <div className="flex justify-between">
                  <dt className="text-gray-500">Orientation Fixed</dt>
                  <dd className="text-gray-300">{image.orientation_corrected ? "Yes" : "No"}</dd>
                </div>
              </dl>
            </div>

            <a
              href={fullImageUrl(image.id)}
              download={image.filename}
              className="block w-full text-center text-sm px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition"
            >
              Download
            </a>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="w-full text-sm px-4 py-2 bg-red-900/50 hover:bg-red-800 text-red-400 hover:text-red-300 rounded-lg transition disabled:opacity-50"
            >
              {deleting ? "Deleting..." : "Delete Image"}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
