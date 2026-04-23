import { useEffect, useState } from "react"
import { getSettings, updateSettings, resetDatabase } from "../api"

export default function Settings() {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [message, setMessage] = useState(null)
  const [newShare, setNewShare] = useState("")
  const [smbPassword, setSmbPassword] = useState("")

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6 text-gray-500">Loading settings...</div>
  if (!settings) return <div className="p-6 text-gray-500">Failed to load settings</div>

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const payload = {
        smb_host: settings.smb_host,
        smb_username: settings.smb_username,
        smb_shares: settings.smb_shares,
        scan_concurrency: settings.scan_concurrency,
        scan_interval_minutes: settings.scan_interval_minutes,
        scan_schedule_enabled: settings.scan_schedule_enabled || false,
        scan_schedule_start: settings.scan_schedule_start || "22:00",
        scan_schedule_end: settings.scan_schedule_end || "06:00",
      }
      if (smbPassword) payload.smb_password = smbPassword
      await updateSettings(payload)
      setMessage({ type: "success", text: "Settings saved. Restart scan for changes to take effect." })
      setSmbPassword("")
    } catch (err) {
      setMessage({ type: "error", text: "Failed to save settings" })
    }
    setSaving(false)
  }

  const addShare = () => {
    const s = newShare.trim()
    if (s && !settings.smb_shares.includes(s)) {
      setSettings({ ...settings, smb_shares: [...settings.smb_shares, s] })
      setNewShare("")
    }
  }

  const removeShare = (share) => {
    setSettings({ ...settings, smb_shares: settings.smb_shares.filter((s) => s !== share) })
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold text-white">Settings</h2>

      {message && (
        <div className={`px-4 py-3 rounded text-sm ${
          message.type === "success" ? "bg-green-900/50 text-green-300 border border-green-800" : "bg-red-900/50 text-red-300 border border-red-800"
        }`}>
          {message.text}
        </div>
      )}

      {/* NAS Connection */}
      <Section title="NAS Connection (SMB)">
        <Field label="NAS IP Address">
          <input
            type="text"
            value={settings.smb_host}
            onChange={(e) => setSettings({ ...settings, smb_host: e.target.value })}
            className="input-field"
          />
        </Field>
        <Field label="Username">
          <input
            type="text"
            value={settings.smb_username}
            onChange={(e) => setSettings({ ...settings, smb_username: e.target.value })}
            className="input-field"
          />
        </Field>
        <Field label="Password">
          <input
            type="password"
            value={smbPassword}
            onChange={(e) => setSmbPassword(e.target.value)}
            placeholder="Leave blank to keep current"
            className="input-field"
          />
        </Field>
      </Section>

      {/* Share Folders */}
      <Section title="Share Folders">
        <div className="space-y-2">
          {settings.smb_shares.map((share) => {
            return (
              <div key={share} className="flex items-center gap-2 bg-gray-800 rounded px-3 py-2">
                <span className="flex-1 text-sm text-gray-300">{share}</span>
                <button
                  onClick={() => removeShare(share)}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
              </div>
            )
          })}
          <div className="flex gap-2">
            <input
              type="text"
              value={newShare}
              onChange={(e) => setNewShare(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addShare()}
              placeholder="Share name (e.g. Photos)"
              className="input-field flex-1"
            />
            <button onClick={addShare} className="btn-primary">Add</button>
          </div>
        </div>
      </Section>

      {/* Scanner */}
      <Section title="Scanner">
        <Field label="Concurrent Workers">
          <input
            type="number"
            min="1"
            max="10"
            value={settings.scan_concurrency}
            onChange={(e) => setSettings({ ...settings, scan_concurrency: parseInt(e.target.value) || 1 })}
            className="input-field w-24"
          />
        </Field>
        <Field label="Scan Interval (minutes)">
          <input
            type="number"
            min="1"
            value={settings.scan_interval_minutes}
            onChange={(e) => setSettings({ ...settings, scan_interval_minutes: parseInt(e.target.value) || 60 })}
            className="input-field w-24"
          />
        </Field>
      </Section>

      {/* Scheduled Processing Window */}
      <Section title="Scheduled Processing Window">
        <p className="text-xs text-gray-500 -mt-2 mb-2">
          Restrict automatic scans to a time window (e.g. overnight). Crosses midnight if Start &gt; End.
        </p>
        <Field label="">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.scan_schedule_enabled || false}
              onChange={(e) => setSettings({ ...settings, scan_schedule_enabled: e.target.checked })}
              className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500"
            />
            <span className="text-sm text-gray-300">Enable scheduled window</span>
          </label>
        </Field>
        {settings.scan_schedule_enabled && (
          <div className="flex gap-4 items-end">
            <Field label="Window Start (HH:MM)">
              <input
                type="time"
                value={settings.scan_schedule_start || "22:00"}
                onChange={(e) => setSettings({ ...settings, scan_schedule_start: e.target.value })}
                className="input-field w-32"
              />
            </Field>
            <Field label="Window End (HH:MM)">
              <input
                type="time"
                value={settings.scan_schedule_end || "06:00"}
                onChange={(e) => setSettings({ ...settings, scan_schedule_end: e.target.value })}
                className="input-field w-32"
              />
            </Field>
          </div>
        )}
      </Section>

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium rounded-lg transition"
      >
        {saving ? "Saving..." : "Save Settings"}
      </button>

      {/* Danger Zone */}
      <div className="bg-gray-900 border border-red-900/50 rounded-lg p-5">
        <h3 className="text-lg font-medium text-red-400 mb-1">Danger Zone</h3>
        <p className="text-xs text-gray-500 mb-4">
          This will permanently delete all images, tags, faces, and scan history from the database and remove all thumbnails.
          Your original files on the NAS are not affected.
        </p>
        <button
          onClick={async () => {
            if (!window.confirm(
              "Start Over?\n\nThis will delete ALL images, tags, faces, and scan history.\nYour files on the NAS will NOT be deleted.\n\nThis cannot be undone."
            )) return
            setResetting(true)
            setMessage(null)
            try {
              const res = await resetDatabase()
              if (res.status === "error") {
                setMessage({ type: "error", text: res.message })
              } else {
                setMessage({ type: "success", text: "Database cleared. You can now start a fresh scan." })
              }
            } catch (err) {
              setMessage({ type: "error", text: "Failed to reset database" })
            }
            setResetting(false)
          }}
          disabled={resetting}
          className="px-4 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition"
        >
          {resetting ? "Clearing..." : "Start Over / Clear Database"}
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
      <h3 className="text-lg font-medium text-white mb-4">{title}</h3>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  )
}
