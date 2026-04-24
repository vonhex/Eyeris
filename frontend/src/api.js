import axios from "axios"

const api = axios.create({ baseURL: "/api" })

// Attach JWT token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("eyeris_auth_token")
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`
  }
  return config
})

// Handle 401 responses — redirect to login on frontend
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem("eyeris_auth_token")
      // Signal that auth is required
      window.dispatchEvent(new CustomEvent("eyeris-auth-require"))
    }
    return Promise.reject(error)
  }
)

export const getImages = (params) => api.get("/images", { params }).then((r) => r.data)
export const getImageIds = (params) => api.get("/images/ids", { params }).then((r) => r.data)
export const getImage = (id) => api.get(`/images/${id}`).then((r) => r.data)
export const getTags = () => api.get("/tags").then((r) => r.data)
export const getCategories = () => api.get("/categories").then((r) => r.data)
export const getAlbums = () => api.get("/albums").then((r) => r.data)
export const getAlbumImages = (name, params) => api.get(`/albums/${encodeURIComponent(name)}`, { params }).then((r) => r.data)
export const getStats = () => api.get("/stats").then((r) => r.data)
export const getHardwareStats = () => api.get("/stats/hardware").then((r) => r.data)
export const getScanStatus = () => api.get("/scan/status").then((r) => r.data)
export const getScanHistory = () => api.get("/scan/history").then((r) => r.data)
export const startScan = () => api.post("/scan/start").then((r) => r.data)
export const startGpuRescan = () => api.post("/scan/gpu-rescan").then((r) => r.data)
export const stopScan = () => api.post("/scan/stop").then((r) => r.data)
export const pauseScan = () => api.post("/scan/pause").then((r) => r.data)
export const resumeScan = () => api.post("/scan/resume").then((r) => r.data)
export const deleteImage = (id) => api.delete(`/images/${id}`).then((r) => r.data)
export const bulkDeleteImages = (ids) => api.post("/images/bulk-delete", { ids }).then((r) => r.data)
export const bulkDownloadImages = (ids) => api.post("/images/bulk-download", { ids }, { responseType: "blob" }).then((r) => r.data)
export const bulkUpdateTags = (ids, add, remove) => api.post("/images/bulk-tags", { ids, add, remove }).then((r) => r.data)
export const updateImageTags = (id, tags) => api.put(`/images/${id}/tags`, { tags }).then((r) => r.data)
export const updateImageCategory = (id, category) => api.put(`/images/${id}/category`, { category }).then((r) => r.data)
export const setImageFavorite = (id, favorite) => api.put(`/images/${id}/favorite`, { favorite }).then((r) => r.data)
export const getDuplicates = (threshold = 8) => api.get("/images/duplicates", { params: { threshold } }).then((r) => r.data)
export const startPhashScan = () => api.post("/scan/phash").then((r) => r.data)
export const getSentiments = () => api.get("/stats/sentiments").then((r) => r.data)
export const getFolders = () => api.get("/stats/folders").then((r) => r.data)
export const getLocations = () => api.get("/stats/locations").then((r) => r.data)
export const getCameras = () => api.get("/stats/cameras").then((r) => r.data)
export const getQualitySummary = () => api.get("/stats/quality").then((r) => r.data)
export const getFaces = (params) => api.get("/faces", { params }).then((r) => r.data)
export const getPeople = () => api.get("/faces/people").then((r) => r.data)
export const getUnknownFaces = (params) => api.get("/faces/unknown", { params }).then((r) => r.data)
export const updateFaceName = (faceId, name) => api.put(`/faces/${faceId}/name`, { name }).then((r) => r.data)
export const clusterFaces = () => api.post("/faces/cluster").then((r) => r.data)
export const nameCluster = (clusterId, name) => api.put(`/faces/cluster/${clusterId}/name`, { name }).then((r) => r.data)
export const mergeClusters = (sourceIds, targetId) => api.post("/faces/cluster/merge", { source_cluster_ids: sourceIds, target_cluster_id: targetId }).then((r) => r.data)
export const deleteCluster = (clusterId) => api.delete(`/faces/cluster/${clusterId}`).then((r) => r.data)
export const deleteClusters = (clusterIds) => api.post("/faces/clusters/delete", { cluster_ids: clusterIds }).then((r) => r.data)
const getToken = () => localStorage.getItem("eyeris_auth_token") || ""
export const faceCropUrl = (faceId) => `/api/faces/${faceId}/crop?token=${getToken()}`
export const resetDatabase = () => api.post("/scan/reset").then((r) => r.data)
export const getSettings = () => api.get("/settings").then((r) => r.data)
export const updateSettings = (data) => api.put("/settings", data).then((r) => r.data)
export const thumbnailUrl = (id, path = "") => {
  const t = getToken()
  const v = path ? path.split('.')[0] : ""
  const params = [t && `token=${t}`, v && `v=${v}`].filter(Boolean).join("&")
  return `/api/images/${id}/thumbnail${params ? `?${params}` : ""}`
}
export const fullImageUrl = (id) => `/api/images/${id}/file?token=${getToken()}`
export const getSmartAlbums = () => api.get("/smart-albums").then((r) => r.data)
export const createSmartAlbum = (name, filters) => api.post("/smart-albums", { name, filters }).then((r) => r.data)
export const updateSmartAlbum = (id, name, filters) => api.put(`/smart-albums/${id}`, { name, filters }).then((r) => r.data)
export const deleteSmartAlbum = (id) => api.delete(`/smart-albums/${id}`).then((r) => r.data)
export const searxngSearch = (q, page = 1, category = "images") => api.get("/searxng/search", { params: { q, page, category } }).then((r) => r.data)
export const searxngDownload = (urls, share, subfolder) => api.post("/searxng/download", { urls, share, subfolder }).then((r) => r.data)
export const searxngProxyUrl = (url) => {
  const t = getToken()
  return `/api/searxng/proxy?url=${encodeURIComponent(url)}${t ? `&token=${t}` : ""}`
}

// Auth endpoints — use direct fetch to avoid /api prefix conflicts
const authFetch = (path, options) => fetch(`/api${path}`, options).then((r) => r.json())

export const getAuthStatus = () => fetch("/auth/status").then((r) => r.json())
export const setupPassword = (password) => fetch("/auth/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) }).then((r) => r.json())
export const autoSetup = () => fetch("/auth/auto-setup", { method: "POST" }).then((r) => r.json())
export const login = (password) => fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) }).then(async (r) => {
  const data = await r.json()
  if (!r.ok) {
    const err = new Error(data.detail || "Login failed")
    err.response = { data }
    throw err
  }
  return data
})
export const changePassword = (current, newPass) => fetch("/auth/change-password", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current_password: current, new_password: newPass }) }).then(async (r) => {
  const data = await r.json()
  if (!r.ok) {
    const err = new Error(data.detail || "Failed to change password")
    err.response = { data }
    throw err
  }
  return data
})
export const logout = () => {
  localStorage.removeItem("eyeris_auth_token")
  return fetch("/auth/logout", { method: "POST" }).then((r) => r.json())
}
