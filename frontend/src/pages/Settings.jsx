import { useEffect, useState } from "react"
import { getSettings, updateSettings, resetDatabase, changePassword } from "../api"

export default function Settings() {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [message, setMessage] = useState(null)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordMessage, setPasswordMessage] = useState(null)

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
        scan_concurrency: settings.scan_concurrency,
        scan_interval_minutes: settings.scan_interval_minutes,
        scan_schedule_enabled: settings.scan_schedule_enabled || false,
        scan_schedule_start: settings.scan_schedule_start || "22:00",
        scan_schedule_end: settings.scan_schedule_end || "06:00",
        searxng_url: settings.searxng_url || "",
        aeye_url: settings.aeye_url || "",
        aeye_user: settings.aeye_user || "",
        ...(settings.aeye_pass ? { aeye_pass: settings.aeye_pass } : {}),
      }
      await updateSettings(payload)
      setMessage({ type: "success", text: "Settings saved. Restart scan for changes to take effect." })
    } catch (err) {
      setMessage({ type: "error", text: "Failed to save settings" })
    }
    setSaving(false)
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

      {/* Integrations */}
      <Section title="Integrations">
        <Field label="SearXNG URL">
          <input
            type="text"
            value={settings.searxng_url || ""}
            onChange={(e) => setSettings({ ...settings, searxng_url: e.target.value })}
            placeholder="http://your-searxng-host:8080"
            className="input-field"
          />
          <p className="text-xs text-gray-600 mt-1">
            Self-hosted SearXNG instance for web image/video search.{" "}
            <a href="https://github.com/searxng/searxng" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
              What is SearXNG?
            </a>
          </p>
        </Field>
        <Field label="A-Eye URL">
          <input
            type="text"
            value={settings.aeye_url || ""}
            onChange={(e) => setSettings({ ...settings, aeye_url: e.target.value })}
            placeholder="http://10.0.1.x:8001"
            className="input-field"
          />
          <p className="text-xs text-gray-600 mt-1">
            URL of a running A-Eye instance. When set, untagged images can be sent to A-Eye for AI analysis.
            Both apps must share the same photos volume — A-Eye writes XMP sidecars which Eyeris re-imports.
          </p>
        </Field>
        <Field label="A-Eye Username">
          <input
            type="text"
            value={settings.aeye_user || ""}
            onChange={(e) => setSettings({ ...settings, aeye_user: e.target.value })}
            placeholder="admin"
            className="input-field"
          />
        </Field>
        <Field label="A-Eye Password">
          <input
            type="password"
            onChange={(e) => setSettings({ ...settings, aeye_pass: e.target.value })}
            placeholder="leave blank to keep existing"
            className="input-field"
          />
        </Field>
      </Section>

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium rounded-lg transition"
      >
        {saving ? "Saving..." : "Save Settings"}
      </button>

      {/* Change Password */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <h3 className="text-lg font-medium text-white mb-4">Change Password</h3>
        {passwordMessage && (
          <div className={`px-3 py-2 rounded text-sm mb-3 ${
            passwordMessage.type === "success" ? "bg-green-900/50 text-green-300 border border-green-800" : "bg-red-900/50 text-red-300 border border-red-800"
          }`}>
            {passwordMessage.text}
          </div>
        )}
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            setChangingPassword(true)
            setPasswordMessage(null)
            try {
              await changePassword(currentPassword, newPassword)
              setPasswordMessage({ type: "success", text: "Password updated. You'll be logged out." })
              setCurrentPassword("")
              setNewPassword("")
              setTimeout(() => {
                localStorage.removeItem("eyeris_auth_token")
                window.location.href = "/login"
              }, 1500)
            } catch (err) {
              setPasswordMessage({ type: "error", text: err.response?.data?.detail || err.message || "Failed to change password" })
            }
            setChangingPassword(false)
          }}
          className="space-y-3"
        >
          <Field label="Current Password">
            <input
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="input-field"
              placeholder="Current password"
            />
          </Field>
          <Field label="New Password">
            <input
              type="password"
              required
              minLength={4}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="input-field"
              placeholder="New password (min 4 chars)"
            />
          </Field>
          <button
            type="submit"
            disabled={changingPassword}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition"
          >
            {changingPassword ? "Updating…" : "Update Password"}
          </button>
        </form>
      </div>

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
