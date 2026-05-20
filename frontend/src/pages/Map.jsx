import { useEffect, useState, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import { getImages, thumbnailUrl } from "../api"

// Fix Leaflet's broken default icon paths when bundled with Vite
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
})

function FitBounds({ points }) {
  const map = useMap()
  const fitted = useRef(false)
  useEffect(() => {
    if (!fitted.current && points.length > 0) {
      fitted.current = true
      if (points.length === 1) {
        map.setView([points[0][0], points[0][1]], 13)
      } else {
        map.fitBounds(points, { padding: [40, 40] })
      }
    }
  }, [points, map])
  return null
}

export default function Map() {
  const [images, setImages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    async function load() {
      try {
        let all = []
        let page = 1
        const pageSize = 200
        while (true) {
          const resp = await getImages({ has_gps: true, page, page_size: pageSize })
          all = all.concat(resp.images)
          if (all.length >= resp.total || resp.images.length < pageSize) break
          page++
        }
        setImages(all)
      } catch (err) {
        setError(err?.response?.data?.detail || err?.message || String(err))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const validImages = images.filter((img) => img.gps_lat != null && img.gps_lon != null)
  const points = validImages.map((img) => [img.gps_lat, img.gps_lon])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-400 text-lg animate-pulse">
        Loading map…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3 text-red-400">
        <p className="text-lg font-medium">Failed to load map</p>
        <pre className="text-sm bg-gray-900 rounded p-4 max-w-xl text-red-300 whitespace-pre-wrap">{error}</pre>
      </div>
    )
  }

  if (validImages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3 text-gray-400">
        <svg className="w-12 h-12 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
        </svg>
        <p className="text-lg">No photos with GPS data found.</p>
        <p className="text-sm text-gray-500">Photos need location metadata to appear on the map.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-57px)]">
      <div className="px-6 py-3 bg-gray-900 border-b border-gray-800 flex items-center gap-3 shrink-0">
        <span className="text-white font-medium">Photo Map</span>
        <span className="text-gray-400 text-sm">{validImages.length.toLocaleString()} photo{validImages.length !== 1 ? "s" : ""} with location</span>
      </div>
      <div className="flex-1">
        <MapContainer
          center={[20, 0]}
          zoom={2}
          className="w-full h-full"
          style={{ background: "#1a1a2e" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <FitBounds points={points} />
          {validImages.map((img) => (
            <Marker key={img.id} position={[img.gps_lat, img.gps_lon]}>
              <Popup>
                <div className="flex flex-col items-center gap-2" style={{ minWidth: 160 }}>
                  <img
                    src={thumbnailUrl(img.id)}
                    alt={img.filename}
                    className="rounded"
                    style={{ width: 160, height: 120, objectFit: "cover", cursor: "pointer" }}
                    onClick={() => navigate(`/image/${img.id}`)}
                  />
                  <div style={{ fontSize: 12, color: "#ccc", textAlign: "center", maxWidth: 160, wordBreak: "break-word" }}>
                    {img.location_name || img.filename}
                  </div>
                  <button
                    onClick={() => navigate(`/image/${img.id}`)}
                    style={{
                      fontSize: 12,
                      padding: "4px 12px",
                      background: "#2563eb",
                      color: "white",
                      border: "none",
                      borderRadius: 4,
                      cursor: "pointer",
                    }}
                  >
                    View
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  )
}
