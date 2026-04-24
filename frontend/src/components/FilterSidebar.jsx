import { useEffect, useState } from "react"
import { getTags, getCategories, getLocations, getCameras, getFolders } from "../api"

export default function FilterSidebar({ filters, onFilterChange, open, onClose }) {
  const [tags, setTags] = useState([])
  const [categories, setCategories] = useState([])
  const [folders, setFolders] = useState([])
  const [locations, setLocations] = useState([])
  const [cameras, setCameras] = useState([])

  useEffect(() => {
    getTags().then(setTags).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getLocations().then(setLocations).catch(() => {})
    getCameras().then(setCameras).catch(() => {})
    getFolders().then(setFolders).catch(() => {})
  }, [])

  const handleFilter = (newFilters) => {
    onFilterChange(newFilters)
    if (onClose) onClose()
  }

  return (
    <>
      {open && (
        <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={onClose} />
      )}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-gray-950 border-r border-gray-800 p-4 overflow-y-auto
        transform transition-transform duration-200 ease-in-out
        lg:static lg:w-56 lg:shrink-0 lg:transform-none lg:border-0 lg:bg-transparent lg:p-0 lg:z-auto
        ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      `}>
        <div className="space-y-6">

          {/* Favorites */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Favorites</h3>
            <button
              onClick={() => handleFilter({ ...filters, favorite: filters.favorite ? null : true })}
              className={`flex items-center gap-2 w-full text-left text-sm px-2 py-1 rounded transition ${
                filters.favorite ? "bg-yellow-600/20 text-yellow-400" : "text-gray-400 hover:text-white"
              }`}
            >
              <span>{filters.favorite ? "★" : "☆"}</span>
              <span>Favorites only</span>
            </button>
          </div>

          {/* Date Range */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Date Taken</h3>
            <div className="space-y-1.5">
              <div>
                <label className="text-xs text-gray-500 block mb-0.5">From</label>
                <input
                  type="date"
                  value={filters.date_from || ""}
                  onChange={(e) => handleFilter({ ...filters, date_from: e.target.value || null })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-0.5">To</label>
                <input
                  type="date"
                  value={filters.date_to || ""}
                  onChange={(e) => handleFilter({ ...filters, date_to: e.target.value || null })}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-blue-500"
                />
              </div>
              {(filters.date_from || filters.date_to) && (
                <button
                  onClick={() => handleFilter({ ...filters, date_from: null, date_to: null })}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Clear dates
                </button>
              )}
            </div>
          </div>

          {/* Folders */}
          {!filters.is_video && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Source Folder</h3>
              <button
                onClick={() => handleFilter({ ...filters, folder: null })}
                className={`block w-full text-left text-sm px-2 py-1 rounded ${
                  !filters.folder ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                }`}
              >
                All Folders
              </button>
              <div className="max-h-64 overflow-y-auto space-y-0.5">
                {folders.map((f) => {
                  const label = f.folder.split('/').slice(-2).join('/') || f.folder
                  return (
                    <button
                      key={f.folder}
                      onClick={() => handleFilter({ ...filters, folder: f.folder })}
                      className={`flex justify-between w-full text-left text-sm px-2 py-1 rounded transition ${
                        filters.folder === f.folder ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                      }`}
                      title={f.folder}
                    >
                      <span className="truncate">{label}</span>
                      <span className="text-xs text-gray-600 ml-1 shrink-0">{f.total}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Categories */}
          {categories.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Category</h3>
              <button
                onClick={() => handleFilter({ ...filters, category: null })}
                className={`block w-full text-left text-sm px-2 py-1 rounded ${
                  !filters.category ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                }`}
              >
                All Categories
              </button>
              {categories.map((c) => (
                <button
                  key={c.id}
                  onClick={() => handleFilter({ ...filters, category: c.name })}
                  className={`block w-full text-left text-sm px-2 py-1 rounded flex justify-between ${
                    filters.category === c.name ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                  }`}
                >
                  <span className="truncate">{c.name}</span>
                  <span className="text-xs text-gray-600 ml-1">{c.image_count}</span>
                </button>
              ))}
            </div>
          )}

          {/* Tags */}
          {tags.length > 0 && !filters.is_video && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Tags</h3>
              <div className="flex flex-wrap gap-1 max-h-64 overflow-y-auto">
                {tags.slice(0, 30).map((t) => (
                  <button
                    key={t.id}
                    onClick={() => handleFilter({ ...filters, tag: filters.tag === t.name ? null : t.name })}
                    className={`text-xs px-2 py-0.5 rounded-full transition ${
                      filters.tag === t.name
                        ? "bg-blue-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                    }`}
                  >
                    {t.name}
                    <span className="ml-1 text-gray-500">{t.image_count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Location */}
          {locations.length > 0 && !filters.is_video && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Location</h3>
              <button
                onClick={() => handleFilter({ ...filters, location: null })}
                className={`block w-full text-left text-sm px-2 py-1 rounded ${
                  !filters.location ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                }`}
              >
                All Locations
              </button>
              <div className="max-h-40 overflow-y-auto space-y-0.5">
                {locations.map((l) => (
                  <button
                    key={l.name}
                    onClick={() => handleFilter({ ...filters, location: filters.location === l.name ? null : l.name })}
                    className={`flex justify-between w-full text-left text-sm px-2 py-1 rounded truncate ${
                      filters.location === l.name ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                    }`}
                  >
                    <span className="truncate">{l.name}</span>
                    <span className="text-xs text-gray-600 ml-1 shrink-0">{l.count}</span>
                  </button>
                ))}
              </div>
              <button
                onClick={() => handleFilter({ ...filters, has_gps: filters.has_gps ? null : true })}
                className={`mt-1 flex items-center gap-1.5 text-xs px-2 py-1 rounded transition ${
                  filters.has_gps ? "text-green-400 bg-green-900/20" : "text-gray-500 hover:text-gray-300"
                }`}
              >
                <span>{filters.has_gps ? "★" : "☆"}</span> GPS photos only
              </button>
            </div>
          )}

          {/* Camera */}
          {cameras.length > 0 && !filters.is_video && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Camera</h3>
              <button
                onClick={() => handleFilter({ ...filters, camera: null })}
                className={`block w-full text-left text-sm px-2 py-1 rounded ${
                  !filters.camera ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                }`}
              >
                All Cameras
              </button>
              <div className="max-h-36 overflow-y-auto space-y-0.5">
                {cameras.map((c) => (
                  <button
                    key={c.name}
                    onClick={() => handleFilter({ ...filters, camera: filters.camera === c.name ? null : c.name })}
                    className={`flex justify-between w-full text-left text-xs px-2 py-1 rounded ${
                      filters.camera === c.name ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
                    }`}
                  >
                    <span className="truncate">{c.name}</span>
                    <span className="text-xs text-gray-600 ml-1 shrink-0">{c.count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

        </div>
      </aside>
    </>
  )
}
