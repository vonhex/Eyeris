import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { getTags } from "../api"

function TagCloud({ tags, maxCount }) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6 mb-6">
      <div className="flex flex-wrap gap-2">
        {tags.map((tag) => {
          const size = 0.75 + (tag.image_count / maxCount) * 1.0
          return (
            <Link
              key={tag.id}
              to={`/?tag=${encodeURIComponent(tag.name)}`}
              className="px-3 py-1.5 bg-gray-800 hover:bg-blue-600 text-gray-300 hover:text-white rounded-full transition"
              style={{ fontSize: `${size}rem` }}
            >
              {tag.name}
              <span className="ml-1.5 text-xs text-gray-500">{tag.image_count}</span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

function TagTable({ tags, maxCount }) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left px-4 py-3 text-gray-500 font-medium">Tag</th>
            <th className="text-right px-4 py-3 text-gray-500 font-medium">Images</th>
            <th className="px-4 py-3 text-gray-500 font-medium">Distribution</th>
          </tr>
        </thead>
        <tbody>
          {tags.map((tag) => (
            <tr key={tag.id} className="border-b border-gray-800/50 hover:bg-gray-800/50">
              <td className="px-4 py-2">
                <Link to={`/?tag=${encodeURIComponent(tag.name)}`} className="text-blue-400 hover:text-blue-300">
                  {tag.name}
                </Link>
              </td>
              <td className="px-4 py-2 text-right text-gray-400">{tag.image_count}</td>
              <td className="px-4 py-2">
                <div className="w-full bg-gray-800 rounded-full h-1.5">
                  <div
                    className="bg-blue-600 h-1.5 rounded-full"
                    style={{ width: `${(tag.image_count / maxCount) * 100}%` }}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Tags() {
  const [tags, setTags] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")

  useEffect(() => {
    getTags()
      .then(setTags)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-gray-500">Loading tags...</div>

  const maxCount = Math.max(...tags.map((t) => t.image_count), 1)
  const filtered = search
    ? tags.filter((t) => t.name.toLowerCase().includes(search.toLowerCase()))
    : tags

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-white">Tags ({tags.length})</h2>
        <input
          type="text"
          placeholder="Filter tags..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 placeholder-gray-600 focus:outline-none focus:border-blue-500 w-48"
        />
      </div>

      <TagCloud tags={filtered} maxCount={maxCount} />
      <TagTable tags={filtered} maxCount={maxCount} />
    </div>
  )
}
