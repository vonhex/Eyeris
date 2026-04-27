import { useEffect, useLayoutEffect, useState, useMemo, useCallback, useRef } from "react"
import { useParams, Link, useNavigate } from "react-router-dom"
import {
  getImage, getImages, fullImageUrl, updateImageCategory,
  getCategories, deleteImage, setImageFavorite,
} from "../api"
import TagEditor from "../components/TagEditor"

const IMAGES_KEY = "gallery_images"
const FILTERS_KEY = "gallery_filters"
const TOTAL_KEY = "gallery_total"
const VIDEO_EXTENSIONS = new Set(["mp4", "mkv", "avi", "mov", "wmv", "webm", "m4v"])
const PEEK_PX = 80 // pixels of sheet visible when peeked

// ── Shared detail panel content ──────────────────────────────────────────────
function DetailContent({ image, categories, fetchImage, togglingFav, onToggleFavorite, deleting, onDelete, onCategoryChange }) {
  return (
    <div className="space-y-4">
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
                {face.person_name && <p className="text-blue-400 font-medium">{face.person_name}</p>}
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
          <Link to={`/?album=${encodeURIComponent(image.album)}`} className="text-sm text-blue-400 hover:text-blue-300">
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
                onClick={() => onCategoryChange(cat.name)}
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
              <dd className="text-gray-300">{image.width} × {image.height}</dd>
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
          {image.lens_model && (
            <div className="flex justify-between">
              <dt className="text-gray-500">Lens</dt>
              <dd className="text-gray-300 text-right max-w-[60%]">{image.lens_model}</dd>
            </div>
          )}
          {(image.aperture != null || image.shutter_speed || image.iso != null || image.focal_length != null) && (
            <div className="flex justify-between">
              <dt className="text-gray-500">Exposure</dt>
              <dd className="text-gray-300 text-right font-mono text-xs">
                {[
                  image.aperture != null ? `f/${image.aperture}` : null,
                  image.shutter_speed || null,
                  image.iso != null ? `ISO ${image.iso}` : null,
                  image.focal_length != null ? `${image.focal_length}mm` : null,
                ].filter(Boolean).join(" · ")}
              </dd>
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
        onClick={onDelete}
        disabled={deleting}
        className="w-full text-sm px-4 py-2 bg-red-900/50 hover:bg-red-800 text-red-400 hover:text-red-300 rounded-lg transition disabled:opacity-50"
      >
        {deleting ? "Deleting..." : "Delete Image"}
      </button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ImageDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [image, setImage] = useState(null)
  const [loading, setLoading] = useState(true)
  const [categories, setCategories] = useState([])
  const [togglingFav, setTogglingFav] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const fetchingMore = useRef(false)

  // ── Zoom + pan ────────────────────────────────────────────────────────────
  const desktopContainerRef = useRef(null)
  const mobileImgContainerRef = useRef(null)
  const imgRef = useRef(null)
  const [scale, setScale] = useState(1)
  const [translate, setTranslate] = useState({ x: 0, y: 0 })
  const lastPinchDist = useRef(null)
  const lastTap = useRef(0)
  const isDragging = useRef(false)
  const dragAnchor = useRef({ x: 0, y: 0, tx: 0, ty: 0 })

  // ── Mobile bottom sheet ───────────────────────────────────────────────────
  const sheetRef = useRef(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [sheetDragY, setSheetDragY] = useState(null)
  const [sheetHeight, setSheetHeight] = useState(0)
  const sheetDrag = useRef({ active: false, startTouchY: 0, startOffset: 0 })

  // ── Navigation helpers ────────────────────────────────────────────────────
  const getCachedImages = () => {
    try { return JSON.parse(sessionStorage.getItem(IMAGES_KEY) || "[]") } catch { return [] }
  }
  const getCachedTotal = () => {
    try { return parseInt(sessionStorage.getItem(TOTAL_KEY), 10) || 0 } catch { return 0 }
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
      try { const raw = sessionStorage.getItem(FILTERS_KEY); if (raw) filters = JSON.parse(raw) } catch {}
      const data = await getImages({ page: nextPage, page_size: 48, ...filters })
      if (data.images.length > 0) {
        const updated = [...imgs, ...data.images]
        sessionStorage.setItem(IMAGES_KEY, JSON.stringify(updated))
        sessionStorage.setItem(TOTAL_KEY, String(data.total))
        return updated
      }
    } catch (err) { console.error("Failed to fetch more images:", err) } finally { fetchingMore.current = false }
    return null
  }, [])

  const { prevId, nextId, position, total, atEnd } = useMemo(() => {
    const imgs = getCachedImages()
    const cachedTotal = getCachedTotal()
    if (imgs.length > 0) {
      const idx = imgs.findIndex((img) => String(img.id) === String(id))
      if (idx !== -1) return {
        prevId: idx > 0 ? imgs[idx - 1].id : null,
        nextId: idx < imgs.length - 1 ? imgs[idx + 1].id : null,
        position: idx + 1,
        total: cachedTotal || imgs.length,
        atEnd: idx === imgs.length - 1 && imgs.length < cachedTotal,
      }
    }
    return { prevId: null, nextId: null, position: null, total: null, atEnd: false }
  }, [id])

  const goNext = useCallback(async () => {
    if (nextId) { navigate(`/image/${nextId}`, { replace: true }); return }
    if (atEnd) {
      const updated = await fetchMoreImages()
      if (updated) {
        const idx = updated.findIndex((img) => String(img.id) === String(id))
        if (idx !== -1 && idx < updated.length - 1) navigate(`/image/${updated[idx + 1].id}`, { replace: true })
      }
    }
  }, [nextId, atEnd, id, navigate, fetchMoreImages])

  const goPrev = useCallback(() => {
    if (prevId) navigate(`/image/${prevId}`, { replace: true })
  }, [prevId, navigate])

  // ── Keyboard navigation ───────────────────────────────────────────────────
  useEffect(() => {
    const handleKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return
      if (e.key === "ArrowLeft") goPrev()
      else if (e.key === "ArrowRight") goNext()
      else if (e.key === "Escape" && scale > 1) { setScale(1); setTranslate({ x: 0, y: 0 }) }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [goNext, goPrev, scale])

  // ── Reset zoom + sheet when image changes ─────────────────────────────────
  useEffect(() => {
    setScale(1)
    setTranslate({ x: 0, y: 0 })
    setSheetOpen(false)
    setSheetDragY(null)
  }, [id])

  // ── Measure sheet height after render (before paint) ─────────────────────
  useLayoutEffect(() => {
    if (sheetRef.current && image) setSheetHeight(sheetRef.current.offsetHeight)
  }, [image])

  // ── Desktop: mouse-wheel zoom ─────────────────────────────────────────────
  useEffect(() => {
    const el = desktopContainerRef.current
    if (!el) return
    const onWheel = (e) => {
      e.preventDefault()
      const factor = e.deltaY < 0 ? 1.12 : 0.9
      setScale((s) => {
        const next = Math.min(8, Math.max(1, s * factor))
        if (next <= 1) { setTranslate({ x: 0, y: 0 }); return 1 }
        return next
      })
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [image])

  // ── Desktop: mouse drag to pan ────────────────────────────────────────────
  const onDesktopMouseDown = useCallback((e) => {
    if (scale <= 1) return
    e.preventDefault()
    isDragging.current = true
    dragAnchor.current = { x: e.clientX, y: e.clientY, tx: translate.x, ty: translate.y }
  }, [scale, translate])

  useEffect(() => {
    const onMove = (e) => {
      if (!isDragging.current) return
      setTranslate({
        x: dragAnchor.current.tx + e.clientX - dragAnchor.current.x,
        y: dragAnchor.current.ty + e.clientY - dragAnchor.current.y,
      })
    }
    const onUp = () => { isDragging.current = false }
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp) }
  }, [])

  // ── Stable refs so the touch effect never needs to reinstall mid-gesture ──
  const scaleRef = useRef(scale)
  const goPrevRef = useRef(goPrev)
  const goNextRef = useRef(goNext)
  useEffect(() => { scaleRef.current = scale }, [scale])
  useEffect(() => { goPrevRef.current = goPrev }, [goPrev])
  useEffect(() => { goNextRef.current = goNext }, [goNext])

  // ── Mobile: pinch-zoom + swipe-to-navigate on image container ────────────
  // Deps: only [image] — reading scale/nav via refs keeps listeners stable
  // during an active gesture so wasMultiTouch is never reset mid-pinch.
  useEffect(() => {
    const el = mobileImgContainerRef.current
    if (!el) return

    let swipeStartX = 0
    let wasMultiTouch = false

    const onTouchStart = (e) => {
      if (e.touches.length >= 2) {
        wasMultiTouch = true
        lastPinchDist.current = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
      } else {
        swipeStartX = e.touches[0].clientX
        wasMultiTouch = false
      }
    }

    const onTouchMove = (e) => {
      if (e.touches.length >= 2) wasMultiTouch = true
      if (e.touches.length === 2 && lastPinchDist.current !== null) {
        e.preventDefault()
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        )
        setScale((s) => Math.min(Math.max(s * (dist / lastPinchDist.current), 1), 8))
        lastPinchDist.current = dist
      }
    }

    const onTouchEnd = (e) => {
      if (e.touches.length < 2) lastPinchDist.current = null

      // Only act when ALL fingers are lifted — prevents double-tap false positives
      // when two fingers lift in rapid succession after a pinch.
      if (e.touches.length !== 0) return

      setScale((s) => (s < 1.05 ? 1 : s))

      if (!wasMultiTouch && e.changedTouches.length > 0) {
        // Double-tap: reset zoom
        const now = Date.now()
        if (now - lastTap.current < 300) {
          setScale(1)
          setTranslate({ x: 0, y: 0 })
        }
        lastTap.current = now

        // Horizontal swipe to navigate (only when not zoomed)
        if (scaleRef.current <= 1) {
          const deltaX = e.changedTouches[0].clientX - swipeStartX
          if (Math.abs(deltaX) > 60) {
            if (deltaX > 0) goPrevRef.current()
            else goNextRef.current()
          }
        }
      }
    }

    el.addEventListener("touchstart", onTouchStart, { passive: true })
    el.addEventListener("touchmove", onTouchMove, { passive: false })
    el.addEventListener("touchend", onTouchEnd, { passive: true })
    return () => {
      el.removeEventListener("touchstart", onTouchStart)
      el.removeEventListener("touchmove", onTouchMove)
      el.removeEventListener("touchend", onTouchEnd)
    }
  }, [image])

  // ── Sheet drag ────────────────────────────────────────────────────────────
  const peekOffset = sheetHeight > PEEK_PX ? sheetHeight - PEEK_PX : 0

  const onSheetTouchStart = (e) => {
    sheetDrag.current = {
      active: true,
      startTouchY: e.touches[0].clientY,
      startOffset: sheetOpen ? 0 : peekOffset,
    }
    setSheetDragY(sheetDrag.current.startOffset)
  }

  const onSheetTouchMove = (e) => {
    if (!sheetDrag.current.active) return
    e.stopPropagation()
    const delta = e.touches[0].clientY - sheetDrag.current.startTouchY
    setSheetDragY(Math.max(0, Math.min(peekOffset, sheetDrag.current.startOffset + delta)))
  }

  const onSheetTouchEnd = () => {
    if (!sheetDrag.current.active) return
    const current = sheetDragY ?? peekOffset
    setSheetOpen(current < peekOffset / 2)
    setSheetDragY(null)
    sheetDrag.current.active = false
  }

  const sheetTransform = useMemo(() => {
    if (sheetDragY !== null) return `translateY(${sheetDragY}px)`
    return sheetOpen ? "translateY(0px)" : `translateY(${peekOffset}px)`
  }, [sheetDragY, sheetOpen, peekOffset])

  // ── Data fetching ─────────────────────────────────────────────────────────
  const fetchImage = async () => {
    setLoading(true)
    try { setImage(await getImage(id)) } catch (err) { console.error(err) }
    setLoading(false)
  }

  useEffect(() => { fetchImage() }, [id])
  useEffect(() => { getCategories().then(setCategories).catch(() => {}) }, [])

  const handleToggleFavorite = async () => {
    if (!image) return
    setTogglingFav(true)
    try {
      const result = await setImageFavorite(id, !image.favorite)
      setImage((prev) => ({ ...prev, favorite: result.favorite }))
    } catch (err) { console.error(err) }
    setTogglingFav(false)
  }

  const handleDelete = async () => {
    if (!window.confirm(`Permanently delete "${image?.filename}" from the NAS? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await deleteImage(id)
      try {
        const raw = sessionStorage.getItem(IMAGES_KEY)
        if (raw) {
          const imgs = JSON.parse(raw)
          sessionStorage.setItem(IMAGES_KEY, JSON.stringify(imgs.filter((img) => String(img.id) !== String(id))))
          const t = parseInt(sessionStorage.getItem(TOTAL_KEY), 10) || 0
          if (t > 0) sessionStorage.setItem(TOTAL_KEY, String(t - 1))
        }
      } catch {}
      if (nextId) navigate(`/image/${nextId}`, { replace: true })
      else if (prevId) navigate(`/image/${prevId}`, { replace: true })
      else navigate("/", { replace: true })
    } catch (err) { console.error(err); alert("Failed to delete image") }
    setDeleting(false)
  }

  const handleCategoryChange = async (cat) => {
    try { await updateImageCategory(id, cat); await fetchImage() } catch (err) { console.error(err) }
  }

  if (loading) return <div className="p-6 text-gray-500">Loading...</div>
  if (!image) return <div className="p-6 text-gray-500">Image not found</div>

  const isVid = image.is_video || VIDEO_EXTENSIONS.has(image.filename.split(".").pop()?.toLowerCase())
  const imgStyle = { transform: `translate(${translate.x}px,${translate.y}px) scale(${scale})`, transformOrigin: "center center" }
  const detailProps = {
    image, categories, fetchImage, togglingFav,
    onToggleFavorite: handleToggleFavorite,
    deleting, onDelete: handleDelete,
    onCategoryChange: handleCategoryChange,
  }

  return (
    <>
      {/* ══════════════════════════════════════════════════════════════════════
          MOBILE: full-screen image + swipe-up bottom sheet
          (hidden on md+ breakpoints)
      ══════════════════════════════════════════════════════════════════════ */}
      <div className="md:hidden fixed inset-0 z-50 bg-black">
        {/* Image area fills entire screen */}
        <div
          ref={mobileImgContainerRef}
          className="absolute inset-0 flex items-center justify-center overflow-hidden"
        >
          {isVid ? (
            <video
              src={fullImageUrl(image.id)}
              controls
              autoPlay
              className="w-full h-full object-contain"
            />
          ) : (
            <img
              src={fullImageUrl(image.id)}
              alt={image.filename}
              className="w-full h-full object-contain select-none"
              style={imgStyle}
              draggable={false}
            />
          )}

          {/* Top bar: back + counter */}
          <div className="absolute top-0 left-0 right-0 flex items-center justify-between p-4 bg-gradient-to-b from-black/60 to-transparent pointer-events-none">
            <button
              onClick={() => navigate(-1)}
              className="pointer-events-auto bg-black/40 backdrop-blur text-white px-3 py-1.5 rounded-lg text-sm"
            >
              ← Back
            </button>
            {position && total && (
              <span className="text-white/60 text-xs">{position} / {total}</span>
            )}
          </div>

          {/* Side navigation arrows */}
          {prevId && (
            <button
              onClick={goPrev}
              className="absolute left-3 top-1/2 -translate-y-1/2 w-9 h-9 bg-black/50 backdrop-blur text-white rounded-full flex items-center justify-center text-lg"
            >
              ‹
            </button>
          )}
          {(nextId || atEnd) && (
            <button
              onClick={goNext}
              className="absolute right-3 top-1/2 -translate-y-1/2 w-9 h-9 bg-black/50 backdrop-blur text-white rounded-full flex items-center justify-center text-lg"
            >
              ›
            </button>
          )}

          {/* Zoom indicator */}
          {scale > 1 && !isVid && (
            <div className="absolute bottom-28 left-1/2 -translate-x-1/2 bg-black/60 backdrop-blur text-white text-xs px-3 py-1 rounded-full pointer-events-none">
              {Math.round(scale * 100)}% · double-tap to reset
            </div>
          )}
        </div>

        {/* Bottom sheet */}
        <div
          ref={sheetRef}
          style={{
            transform: sheetTransform,
            transition: sheetDrag.current.active ? "none" : "transform 0.3s cubic-bezier(0.32,0.72,0,1)",
            maxHeight: "85vh",
          }}
          className="absolute bottom-0 left-0 right-0 bg-gray-900 rounded-t-2xl shadow-2xl flex flex-col"
        >
          {/* Drag handle + title row (always visible at peek) */}
          <div
            onTouchStart={onSheetTouchStart}
            onTouchMove={onSheetTouchMove}
            onTouchEnd={onSheetTouchEnd}
            className="shrink-0 px-4 pt-2 pb-3 cursor-grab active:cursor-grabbing select-none"
          >
            <div className="w-10 h-1 bg-gray-600 rounded-full mx-auto mb-3" />
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-white font-medium text-sm truncate flex-1">{image.filename}</h2>
              <button
                onClick={handleToggleFavorite}
                disabled={togglingFav}
                className={`text-2xl shrink-0 transition ${image.favorite ? "text-yellow-400" : "text-gray-600"}`}
              >
                {image.favorite ? "★" : "☆"}
              </button>
            </div>
            {/* Hint label when peeked */}
            {!sheetOpen && (
              <p className="text-xs text-gray-500 mt-1">Swipe up for details</p>
            )}
          </div>

          {/* Scrollable detail content */}
          <div className="overflow-y-auto flex-1 px-4 pb-10">
            <DetailContent {...detailProps} />
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════════
          DESKTOP: sidebar layout
          (hidden on mobile, shown on md+)
      ══════════════════════════════════════════════════════════════════════ */}
      <div className="hidden md:block p-6">
        {/* Top nav bar */}
        <div className="flex items-center justify-between mb-4">
          <button onClick={() => navigate(-1)} className="text-blue-500 hover:text-blue-400 text-sm">
            ← Back
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
              ← Prev
            </button>
            <button
              onClick={goNext}
              disabled={!nextId && !atEnd}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:hover:bg-gray-800 text-gray-300 rounded-lg transition text-sm"
            >
              Next →
            </button>
          </div>
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Image column */}
          <div className="lg:flex-1 flex items-center gap-2 min-h-0">
            {/* Prev arrow */}
            <div className="w-12 flex-shrink-0 flex items-center justify-center">
              {prevId && (
                <button
                  onClick={goPrev}
                  className="w-10 h-10 bg-gray-800 hover:bg-gray-700 text-white rounded-full flex items-center justify-center transition shadow-lg border border-gray-700"
                  title="Previous (Left Arrow)"
                >
                  ←
                </button>
              )}
            </div>

            {/* Image container: wheel-to-zoom, drag-to-pan, double-click to toggle */}
            <div
              ref={desktopContainerRef}
              className="flex-1 relative min-w-0"
              onMouseDown={onDesktopMouseDown}
              style={{ cursor: scale > 1 ? "grab" : "default" }}
            >
              <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 shadow-2xl">
                {isVid ? (
                  <video
                    src={fullImageUrl(image.id)}
                    controls
                    autoPlay
                    className="w-full h-auto max-h-[75vh] object-contain"
                  />
                ) : (
                  <img
                    ref={imgRef}
                    src={fullImageUrl(image.id)}
                    alt={image.filename}
                    className="w-full h-auto max-h-[75vh] object-contain select-none"
                    style={{ ...imgStyle, transition: isDragging.current ? "none" : "transform 0.1s ease" }}
                    onDoubleClick={() => {
                      if (scale > 1) { setScale(1); setTranslate({ x: 0, y: 0 }) }
                      else setScale(2.5)
                    }}
                    draggable={false}
                  />
                )}
              </div>

              {scale > 1 && !isVid && (
                <div className="absolute bottom-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded select-none">
                  {Math.round(scale * 100)}% · scroll to zoom · drag to pan · double-click to reset
                </div>
              )}
            </div>

            {/* Next arrow */}
            <div className="w-12 flex-shrink-0 flex items-center justify-center">
              {(nextId || atEnd) && (
                <button
                  onClick={goNext}
                  className="w-10 h-10 bg-gray-800 hover:bg-gray-700 text-white rounded-full flex items-center justify-center transition shadow-lg border border-gray-700"
                  title="Next (Right Arrow)"
                >
                  →
                </button>
              )}
            </div>
          </div>

          {/* Sidebar */}
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
              <DetailContent {...detailProps} />
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
