import { useState, useEffect } from "react"

export default function SearchBar({ value: controlledValue = "", onSearch }) {
  const [value, setValue] = useState(controlledValue)

  // Sync from parent when URL changes (back/forward)
  useEffect(() => {
    setValue(controlledValue)
  }, [controlledValue])

  const handleSubmit = (e) => {
    e.preventDefault()
    onSearch(value)
  }

  return (
    <form onSubmit={handleSubmit} className="relative">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search images..."
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 pl-10 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition"
      />
      <svg className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      {value && (
        <button
          type="button"
          onClick={() => { setValue(""); onSearch("") }}
          className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-300"
        >
          x
        </button>
      )}
    </form>
  )
}
