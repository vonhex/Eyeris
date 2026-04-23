import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { getFolders, thumbnailUrl } from "../api"

function FolderGrid({ folders }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
      {folders.map((f) => (
        <Link
          key={f.folder}
          to={`/?folder=${encodeURIComponent(f.folder)}`}
          className="bg-gray-900 rounded-lg border border-gray-800 hover:border-blue-500 transition overflow-hidden group"
        >
          <div className="aspect-video overflow-hidden">
            {f.sample_image_id ? (
              <img
                src={thumbnailUrl(f.sample_image_id)}
                alt={f.folder}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                loading="lazy"
              />
            ) : (
              <div className="w-full h-full bg-gray-800 flex items-center justify-center text-gray-600">
                No preview
              </div>
            )}
          </div>
          <div className="p-4">
            <h3 className="text-sm font-medium text-white mb-2">{f.folder}</h3>
            <div className="flex justify-between text-xs text-gray-400 mb-2">
              <span>{f.total} images</span>
              <span>{f.analyzed} analyzed</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5">
              <div
                className="bg-green-500 h-1.5 rounded-full transition-all"
                style={{ width: `${f.total > 0 ? (f.analyzed / f.total) * 100 : 0}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {f.total > 0 ? Math.round((f.analyzed / f.total) * 100) : 0}% analyzed
            </p>
          </div>
        </Link>
      ))}
    </div>
  )
}

export default function Folders() {
  const [folders, setFolders] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getFolders()
      .then(setFolders)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-gray-500">Loading folders...</div>

  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold text-white mb-6">Source Folders</h2>
      {folders.length === 0 ? (
        <p className="text-gray-500">No folders found</p>
      ) : (
        <FolderGrid folders={folders} />
      )}
    </div>
  )
}
