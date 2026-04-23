import { useRef } from "react"
import { Link } from "react-router-dom"
import { thumbnailUrl } from "../api"

export default function ImageCard({ image, selectMode, selected, onToggleSelect, onLongPress }) {
  const pressTimer = useRef(null)
  const didLongPress = useRef(false)

  const handleClick = (e) => {
    if (selectMode) {
      e.preventDefault()
      onToggleSelect(image.id, e.shiftKey)
    }
  }

  const handleCheckbox = (e) => {
    e.preventDefault()
    e.stopPropagation()
    onToggleSelect(image.id, e.shiftKey)
  }

  // Long-press to enter select mode on mobile
  const handleTouchStart = () => {
    didLongPress.current = false
    pressTimer.current = setTimeout(() => {
      didLongPress.current = true
      onLongPress?.(image.id)
    }, 500)
  }

  const handleTouchEnd = (e) => {
    clearTimeout(pressTimer.current)
    // Prevent click if we long-pressed
    if (didLongPress.current) {
      e.preventDefault()
      didLongPress.current = false
    }
  }

  const handleTouchMove = () => {
    clearTimeout(pressTimer.current)
  }

  return (
    <Link
      to={selectMode ? "#" : `/image/${image.id}`}
      onClick={handleClick}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      onTouchMove={handleTouchMove}
      className={`group relative bg-gray-900 rounded-lg overflow-hidden border transition-all hover:shadow-lg ${
        selected
          ? "border-red-500 ring-2 ring-red-500/50"
          : "border-gray-800 hover:border-blue-500 hover:shadow-blue-500/10"
      }`}
    >
      <div className="aspect-square overflow-hidden">
        <img
          src={thumbnailUrl(image.id, image.thumbnail_path)}
          alt={image.filename}
          className={`w-full h-full object-cover transition-transform duration-300 ${
            selected ? "opacity-60" : "group-hover:scale-105"
          }`}
          loading="lazy"
        />
      </div>
      <div className="p-2">
        <p className="text-xs text-gray-400 truncate">{image.filename}</p>
        <p className="text-xs text-gray-600 truncate">{image.source_folder}</p>
        {image.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {image.tags.slice(0, 3).map((t) => (
              <span
                key={t.tag_name}
                className="text-[10px] px-1.5 py-0.5 bg-gray-800 text-gray-400 rounded"
              >
                {t.tag_name}
              </span>
            ))}
            {image.tags.length > 3 && (
              <span className="text-[10px] text-gray-600">+{image.tags.length - 3}</span>
            )}
          </div>
        )}
      </div>

      {/* Favorite star */}
      {image.favorite && !selectMode && (
        <div className="absolute top-2 right-2 text-yellow-400 text-sm leading-none drop-shadow">★</div>
      )}

      {selectMode && (
        <div
          className="absolute top-2 left-2"
          onClick={handleCheckbox}
        >
          <div className={`w-5 h-5 rounded border-2 flex items-center justify-center transition ${
            selected
              ? "bg-red-500 border-red-500"
              : "bg-black/50 border-gray-400 hover:border-white"
          }`}>
            {selected && (
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            )}
          </div>
        </div>
      )}
    </Link>
  )
}
