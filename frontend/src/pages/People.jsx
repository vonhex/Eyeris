import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { getPeople, clusterFaces, nameCluster, thumbnailUrl, faceCropUrl, getUnknownFaces, mergeClusters, updateFaceName, deleteCluster, deleteClusters } from "../api"

// ---------------------------------------------------------------------------
// Person card
// ---------------------------------------------------------------------------
function PersonCard({ cluster, onRename, onDelete, selectMode, selectSelected, onSelectToggle }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(cluster.person_name || "")
  const navigate = useNavigate()

  const displayName = cluster.person_name || `Person ${cluster.cluster_id + 1}`
  const imgSrc = cluster.has_crop
    ? faceCropUrl(cluster.sample_face_id)
    : thumbnailUrl(cluster.sample_image_id)

  const save = async () => {
    await onRename(cluster.cluster_id, draft.trim())
    setEditing(false)
  }

  const onKey = (e) => {
    if (e.key === "Enter") save()
    if (e.key === "Escape") { setDraft(cluster.person_name || ""); setEditing(false) }
  }

  const isSelected = selectSelected?.has(cluster.cluster_id)
  const inSelectMode = !!selectMode

  return (
    <div className={`bg-gray-900 rounded-lg border transition overflow-hidden ${
      inSelectMode
        ? isSelected
          ? "border-red-500 ring-2 ring-red-500/50"
          : "border-gray-700 hover:border-gray-500"
        : "border-gray-800 hover:border-gray-600"
    }`}>
      <div
        className="aspect-square overflow-hidden cursor-pointer relative"
        onClick={() => inSelectMode ? onSelectToggle(cluster.cluster_id) : navigate(`/?cluster_id=${cluster.cluster_id}`)}
      >
        <img
          src={imgSrc}
          alt={displayName}
          className="w-full h-full object-cover hover:scale-105 transition-transform duration-200"
          loading="lazy"
        />
        {inSelectMode && isSelected && (
          <div className="absolute inset-0 bg-red-500/30 flex items-center justify-center">
            <div className="w-8 h-8 bg-red-500 rounded-full flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          </div>
        )}
        {/* Single-card delete button (visible on hover when not in any select mode) */}
        {!inSelectMode && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(cluster.cluster_id) }}
            className="absolute top-1.5 right-1.5 w-6 h-6 bg-black/60 hover:bg-red-600 text-white rounded-full items-center justify-center hidden group-hover:flex transition opacity-0 group-hover:opacity-100"
            title="Delete this group"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="p-3">
        {editing ? (
          <div className="flex items-center gap-1">
            <input
              autoFocus
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder="Enter name..."
              className="flex-1 min-w-0 bg-gray-800 text-white text-sm px-2 py-1 rounded border border-gray-600 focus:border-blue-500 outline-none"
            />
            <button onClick={save} className="text-blue-400 hover:text-blue-300 text-sm px-1">✓</button>
            <button onClick={() => { setDraft(cluster.person_name || ""); setEditing(false) }} className="text-gray-500 hover:text-gray-400 text-sm px-1">✕</button>
          </div>
        ) : (
          <div
            className="flex items-center gap-1 cursor-pointer group"
            onClick={() => !inSelectMode && (setDraft(cluster.person_name || ""), setEditing(true))}
            title={inSelectMode ? undefined : "Click to name this person"}
          >
            <span className="text-sm text-white truncate flex-1 group-hover:text-blue-400 transition">
              {displayName}
            </span>
            {!inSelectMode && <span className="text-gray-600 group-hover:text-gray-400 text-xs">✎</span>}
          </div>
        )}
        <p className="text-xs text-gray-500 mt-1">
          {cluster.face_count} photo{cluster.face_count !== 1 ? "s" : ""}
        </p>
      </div>
    </div>
  )
}

function PeopleGrid({ clusters, onRename, onDelete, selectMode, selectSelected, onSelectToggle }) {
  if (!clusters.length) return null
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
      {clusters.map((c) => (
        <div key={c.cluster_id} className="group relative">
          <PersonCard
            cluster={c}
            onRename={onRename}
            onDelete={onDelete}
            selectMode={selectMode}
            selectSelected={selectSelected}
            onSelectToggle={onSelectToggle}
          />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Unknown faces tab
// ---------------------------------------------------------------------------
function UnknownFaces() {
  const [data, setData] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [namingId, setNamingId] = useState(null)
  const [nameDraft, setNameDraft] = useState("")

  const load = (p = 1) => {
    setLoading(true)
    getUnknownFaces({ page: p, page_size: 48 })
      .then((d) => { setData(d); setPage(p) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(1) }, [])

  const saveName = async (faceId) => {
    await updateFaceName(faceId, nameDraft.trim())
    setNamingId(null)
    setNameDraft("")
    load(page)
  }

  if (loading) return <div className="py-8 text-center text-gray-500 text-sm">Loading...</div>

  const faces = data?.faces || []
  const total = data?.total || 0

  if (!faces.length) return (
    <div className="py-16 text-center text-gray-500">
      <p>No unclustered faces — all faces have been grouped.</p>
    </div>
  )

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-400">{total} unclustered face{total !== 1 ? "s" : ""}</p>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
        {faces.map((f) => (
          <div key={f.id} className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
            <div className="aspect-square">
              {f.has_crop ? (
                <img src={`/api/faces/${f.id}/crop`} alt="" className="w-full h-full object-cover" loading="lazy" />
              ) : (
                <div className="w-full h-full bg-gray-800 flex items-center justify-center text-gray-600 text-xs">No crop</div>
              )}
            </div>
            <div className="p-1.5">
              {namingId === f.id ? (
                <div className="flex gap-1">
                  <input
                    autoFocus
                    type="text"
                    value={nameDraft}
                    onChange={(e) => setNameDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") saveName(f.id); if (e.key === "Escape") setNamingId(null) }}
                    className="flex-1 min-w-0 bg-gray-800 text-white text-xs px-1 py-0.5 rounded border border-gray-600 focus:border-blue-500 outline-none"
                    placeholder="Name..."
                  />
                  <button onClick={() => saveName(f.id)} className="text-blue-400 text-xs">✓</button>
                </div>
              ) : (
                <button
                  onClick={() => { setNamingId(f.id); setNameDraft(f.person_name || "") }}
                  className="w-full text-left text-xs text-gray-500 hover:text-gray-300 truncate"
                >
                  {f.person_name || "Name..."}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      {total > faces.length && (
        <div className="flex gap-2 justify-center">
          {page > 1 && (
            <button onClick={() => load(page - 1)} className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm">Prev</button>
          )}
          <button onClick={() => load(page + 1)} className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-sm">Next</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export function PeopleList() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [clustering, setClustering] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState("grouped") // "grouped" | "unknown"
  const [selectMode, setSelectMode] = useState(null) // null | "merge" | "delete"
  const [selectSelected, setSelectSelected] = useState(new Set())
  const [merging, setMerging] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const load = () => {
    setLoading(true)
    getPeople()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const handleCluster = async () => {
    setClustering(true)
    setError(null)
    try {
      await clusterFaces()
      load()
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
        "Grouping failed. Make sure facenet-pytorch is installed: pip install facenet-pytorch"
      )
    }
    setClustering(false)
  }

  const handleRename = async (clusterId, name) => {
    await nameCluster(clusterId, name)
    load()
  }

  const handleDeleteOne = async (clusterId) => {
    if (!window.confirm("Delete this group? These faces won't appear in People or be re-grouped on future scans.")) return
    try {
      await deleteCluster(clusterId)
      load()
    } catch (err) {
      alert(err?.response?.data?.detail || "Delete failed")
    }
  }

  const toggleSelect = (clusterId) => {
    setSelectSelected((prev) => {
      const next = new Set(prev)
      if (next.has(clusterId)) next.delete(clusterId)
      else next.add(clusterId)
      return next
    })
  }

  const handleMerge = async () => {
    if (selectSelected.size < 2) return
    const ids = [...selectSelected]
    const targetId = ids[0]
    const sourceIds = ids.slice(1)
    setMerging(true)
    try {
      await mergeClusters(sourceIds, targetId)
      setSelectMode(null)
      setSelectSelected(new Set())
      load()
    } catch (err) {
      alert(err?.response?.data?.detail || "Merge failed")
    }
    setMerging(false)
  }

  const handleDeleteSelected = async () => {
    if (selectSelected.size === 0) return
    if (!window.confirm(`Delete ${selectSelected.size} group${selectSelected.size !== 1 ? "s" : ""}? These faces won't appear in People or be re-grouped on future scans.`)) return
    setDeleting(true)
    try {
      await deleteClusters([...selectSelected])
      setSelectMode(null)
      setSelectSelected(new Set())
      load()
    } catch (err) {
      alert(err?.response?.data?.detail || "Delete failed")
    }
    setDeleting(false)
  }

  const cancelSelectMode = () => { setSelectMode(null); setSelectSelected(new Set()) }

  if (loading) return <div className="p-6 text-gray-500">Loading people...</div>

  const { clusters = [], has_embeddings = false, unclustered_count = 0 } = data || {}

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-start justify-between mb-5 flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">People</h2>
          {clusters.length > 0 && (
            <p className="text-xs text-gray-500 mt-0.5">
              {clusters.length} {clusters.length === 1 ? "person" : "people"} · click a photo to see their gallery
            </p>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          {tab === "grouped" && clusters.length > 0 && !selectMode && (
            <>
              <button
                onClick={() => setSelectMode("merge")}
                className="text-sm px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition"
              >
                Merge
              </button>
              <button
                onClick={() => setSelectMode("delete")}
                className="text-sm px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition"
              >
                Delete
              </button>
            </>
          )}
          {selectMode === "merge" && (
            <>
              <button
                onClick={handleMerge}
                disabled={selectSelected.size < 2 || merging}
                className="text-sm px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-lg transition"
              >
                {merging ? "Merging..." : `Merge ${selectSelected.size} selected`}
              </button>
              <button onClick={cancelSelectMode} className="text-sm px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition">
                Cancel
              </button>
            </>
          )}
          {selectMode === "delete" && (
            <>
              <button
                onClick={handleDeleteSelected}
                disabled={selectSelected.size === 0 || deleting}
                className="text-sm px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white rounded-lg transition"
              >
                {deleting ? "Deleting..." : `Delete ${selectSelected.size} selected`}
              </button>
              <button onClick={cancelSelectMode} className="text-sm px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition">
                Cancel
              </button>
            </>
          )}
          {!selectMode && (
            <button
              onClick={handleCluster}
              disabled={clustering}
              className="shrink-0 text-sm px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition"
            >
              {clustering ? "Grouping faces..." : clusters.length ? "Re-group Faces" : "Group Faces"}
            </button>
          )}
        </div>
      </div>

      {selectMode === "merge" && (
        <div className="mb-4 px-4 py-2 bg-blue-900/20 border border-blue-800/40 rounded text-sm text-blue-300">
          Select 2+ groups to merge. The first selected becomes the target and keeps its name.
        </div>
      )}
      {selectMode === "delete" && (
        <div className="mb-4 px-4 py-2 bg-red-900/20 border border-red-800/40 rounded text-sm text-red-300">
          Select groups to delete. Deleted faces are hidden and won't be re-grouped on future scans.
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-3 rounded bg-red-900/40 text-red-300 border border-red-800/60 text-sm">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-800">
        <button
          onClick={() => setTab("grouped")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
            tab === "grouped" ? "border-blue-500 text-white" : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          Grouped ({clusters.length})
        </button>
        <button
          onClick={() => setTab("unknown")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
            tab === "unknown" ? "border-blue-500 text-white" : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          Unknown {unclustered_count > 0 && <span className="ml-1 px-1.5 py-0.5 bg-yellow-600/40 text-yellow-400 text-xs rounded">{unclustered_count}</span>}
        </button>
      </div>

      {tab === "grouped" && (
        <>
          {!has_embeddings && !clusters.length && (
            <div className="mb-5 px-4 py-3 rounded bg-yellow-900/20 text-yellow-300 border border-yellow-800/40 text-sm">
              No face data found yet. Run a scan (or GPU Rescan) first so faces can be detected,
              then click <strong>Group Faces</strong>.
            </div>
          )}

          {clusters.length === 0 ? (
            <div className="text-center py-16 text-gray-500">
              <p className="text-base">No people grouped yet.</p>
              {has_embeddings && (
                <p className="text-sm mt-1">Click <strong className="text-gray-400">Group Faces</strong> to organise detected faces.</p>
              )}
            </div>
          ) : (
            <PeopleGrid
              clusters={clusters}
              onRename={handleRename}
              onDelete={handleDeleteOne}
              selectMode={selectMode}
              selectSelected={selectSelected}
              onSelectToggle={toggleSelect}
            />
          )}
        </>
      )}

      {tab === "unknown" && <UnknownFaces />}
    </div>
  )
}

export default PeopleList
