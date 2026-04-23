import { useEffect, useState } from "react"
import { getHardwareStats } from "../api"

function Bar({ pct, color = "bg-blue-500" }) {
  const w = pct != null ? Math.min(100, Math.max(0, pct)) : 0
  return (
    <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
      <div className={`h-1.5 rounded-full transition-all duration-500 ${color}`} style={{ width: `${w}%` }} />
    </div>
  )
}

function tempColor(t) {
  if (t == null) return "text-gray-500"
  if (t >= 85) return "text-red-400"
  if (t >= 70) return "text-orange-400"
  if (t >= 55) return "text-yellow-400"
  return "text-green-400"
}

function barColor(pct) {
  if (pct == null) return "bg-gray-600"
  if (pct >= 90) return "bg-red-500"
  if (pct >= 70) return "bg-orange-500"
  if (pct >= 40) return "bg-yellow-500"
  return "bg-green-500"
}

function StatRow({ label, value, pct, unit = "", barCol }) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">{label}</span>
        <span className="text-xs text-gray-300 tabular-nums">
          {value != null ? `${value}${unit}` : "—"}
        </span>
      </div>
      {pct != null && <Bar pct={pct} color={barCol || barColor(pct)} />}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</p>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

export default function HardwareStats() {
  const [data, setData] = useState(null)

  useEffect(() => {
    const fetch = () => getHardwareStats().then(setData).catch(() => {})
    fetch()
    const id = setInterval(fetch, 2000)
    return () => clearInterval(id)
  }, [])

  if (!data) return null

  const { cpu, igpu, gpu } = data

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-4">
      <h3 className="text-sm font-medium text-gray-300">Hardware</h3>

      {/* CPU */}
      <Section title="CPU">
        <div className="flex items-center gap-3">
          <div className="flex-1 space-y-2">
            <StatRow label="Usage" value={cpu.usage_pct} unit="%" pct={cpu.usage_pct} />
            <StatRow label="RAM" value={`${cpu.ram_used_gb} / ${cpu.ram_total_gb}`} unit=" GB" pct={cpu.ram_pct} barCol="bg-blue-500" />
          </div>
          {cpu.temp_c != null && (
            <div className="text-right shrink-0">
              <p className={`text-lg font-bold tabular-nums ${tempColor(cpu.temp_c)}`}>{cpu.temp_c}°</p>
              <p className="text-xs text-gray-600">Tdie</p>
            </div>
          )}
        </div>
        {cpu.freq_mhz != null && (
          <p className="text-xs text-gray-600">{(cpu.freq_mhz / 1000).toFixed(2)} GHz</p>
        )}
      </Section>

      {/* AMD iGPU */}
      <Section title={igpu.name}>
        <div className="flex items-center gap-3">
          <div className="flex-1 space-y-2">
            <StatRow label="Usage" value={igpu.usage_pct} unit="%" pct={igpu.usage_pct} />
            {igpu.vram_total_mb != null && (
              <StatRow
                label="VRAM"
                value={`${igpu.vram_used_mb} / ${igpu.vram_total_mb}`}
                unit=" MB"
                pct={igpu.vram_total_mb ? Math.round((igpu.vram_used_mb / igpu.vram_total_mb) * 100) : null}
                barCol="bg-purple-500"
              />
            )}
          </div>
          {igpu.temp_c != null && (
            <div className="text-right shrink-0">
              <p className={`text-lg font-bold tabular-nums ${tempColor(igpu.temp_c)}`}>{igpu.temp_c}°</p>
              <p className="text-xs text-gray-600">GPU</p>
            </div>
          )}
        </div>
        {igpu.freq_mhz != null && (
          <p className="text-xs text-gray-600">{igpu.freq_mhz} MHz</p>
        )}
      </Section>

      {/* NVIDIA RTX 5060 Ti */}
      <Section title={gpu.name}>
        <div className="flex items-center gap-3">
          <div className="flex-1 space-y-2">
            <StatRow label="Usage" value={gpu.usage_pct} unit="%" pct={gpu.usage_pct} />
            {gpu.vram_total_mb != null && (
              <StatRow
                label="VRAM"
                value={`${gpu.vram_used_mb} / ${gpu.vram_total_mb}`}
                unit=" MB"
                pct={gpu.vram_total_mb ? Math.round((gpu.vram_used_mb / gpu.vram_total_mb) * 100) : null}
                barCol="bg-green-500"
              />
            )}
          </div>
          {gpu.temp_c != null && (
            <div className="text-right shrink-0">
              <p className={`text-lg font-bold tabular-nums ${tempColor(gpu.temp_c)}`}>{gpu.temp_c}°</p>
              <p className="text-xs text-gray-600">GPU</p>
            </div>
          )}
        </div>
        {gpu.mem_usage_pct != null && (
          <p className="text-xs text-gray-600">Mem bandwidth: {gpu.mem_usage_pct}%</p>
        )}
      </Section>
    </div>
  )
}
