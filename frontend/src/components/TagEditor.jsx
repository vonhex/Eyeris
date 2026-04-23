import { useState } from "react"
import { updateImageTags } from "../api"

export default function TagEditor({ imageId, tags, onUpdate }) {
  const [editing, setEditing] = useState(false)
  const [input, setInput] = useState("")
  const [currentTags, setCurrentTags] = useState(tags.map((t) => t.tag_name))
  const [saving, setSaving] = useState(false)

  const addTag = () => {
    const tag = input.trim().toLowerCase()
    if (tag && !currentTags.includes(tag)) {
      setCurrentTags([...currentTags, tag])
    }
    setInput("")
  }

  const removeTag = (tag) => {
    setCurrentTags(currentTags.filter((t) => t !== tag))
  }

  const save = async () => {
    setSaving(true)
    try {
      await updateImageTags(imageId, currentTags)
      onUpdate()
      setEditing(false)
    } catch (e) {
      console.error(e)
    }
    setSaving(false)
  }

  if (!editing) {
    return (
      <div>
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span key={t.tag_name} className="text-xs px-2 py-1 bg-gray-800 text-gray-300 rounded-full">
              {t.tag_name}
            </span>
          ))}
          {tags.length === 0 && <span className="text-xs text-gray-600">No tags</span>}
        </div>
        <button
          onClick={() => setEditing(true)}
          className="text-xs text-blue-500 hover:text-blue-400 mt-2"
        >
          Edit tags
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {currentTags.map((tag) => (
          <span key={tag} className="text-xs px-2 py-1 bg-blue-600/20 text-blue-400 rounded-full flex items-center gap-1">
            {tag}
            <button onClick={() => removeTag(tag)} className="hover:text-red-400">x</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
          placeholder="Add tag..."
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:border-blue-500"
        />
        <button onClick={addTag} className="text-xs px-2 py-1 bg-gray-700 rounded hover:bg-gray-600">Add</button>
      </div>
      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="text-xs px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded transition disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        <button
          onClick={() => { setCurrentTags(tags.map((t) => t.tag_name)); setEditing(false) }}
          className="text-xs px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded transition"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
