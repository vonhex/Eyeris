import ImageCard from "./ImageCard"

export default function ImageGrid({ images, loading, selectMode, selected, onToggleSelect, onLongPress }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
        {Array.from({ length: 24 }).map((_, i) => (
          <div key={i} className="aspect-square bg-gray-900 rounded-lg animate-pulse" />
        ))}
      </div>
    )
  }

  if (!images.length) {
    return (
      <div className="text-center py-20 text-gray-500">
        <p className="text-lg">No images found</p>
        <p className="text-sm mt-1">Try adjusting your filters or wait for the scanner to find images.</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
      {images.map((img) => (
        <ImageCard
          key={img.id}
          image={img}
          selectMode={selectMode}
          selected={selected?.has(img.id)}
          onToggleSelect={onToggleSelect}
          onLongPress={onLongPress}
        />
      ))}
    </div>
  )
}
