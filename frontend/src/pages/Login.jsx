import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { login } from "../api"

export default function Login() {
  const navigate = useNavigate()
  const [authState, setAuthState] = useState("checking") // checking | login
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch("/auth/auto-setup", { method: "POST" })
      .then(async (r) => {
        const data = await r.json()
        if (r.status === 409) {
          setAuthState("login")
          return
        }
        if (!r.ok) {
          setError(data.detail || "Setup failed")
          setAuthState("login")
          return
        }
        // First-time setup: token auto-created, store and redirect
        localStorage.setItem("eyeris_auth_token", data.token)
        navigate("/", { replace: true })
      })
      .catch(() => {
        setAuthState("login")
      })
  }, [])

  const handleLogin = async (e) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await login(password)
      localStorage.setItem("eyeris_auth_token", data.token)
      navigate("/", { replace: true })
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Invalid password")
    } finally {
      setLoading(false)
    }
  }

  if (authState === "checking") {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-400 animate-pulse">Loading…</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-8 shadow-xl">
          <div className="text-center mb-8">
            <img src="/eyeris-logo-icon.png" alt="Eyeris" className="h-16 w-16 rounded mx-auto mb-4 bg-white p-1 object-contain" />
            <h1 className="text-2xl font-bold text-white tracking-wide">Welcome Back</h1>
            <p className="text-gray-400 text-sm mt-2">Sign in to access your photo gallery</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600 transition"
                placeholder="Enter your password"
                autoFocus
              />
            </div>

            {error && (
              <div className="text-red-400 text-sm bg-red-950 border border-red-900 rounded px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className={`w-full py-2.5 px-4 rounded font-medium transition ${
                loading ? "bg-blue-700 cursor-wait text-white" : "bg-blue-600 hover:bg-blue-700 text-white"
              }`}
            >
              {loading ? "Signing in…" : "Sign In"}
            </button>
          </form>

          <p className="text-xs text-gray-600 text-center mt-6">
            Default password: <span className="font-mono text-gray-500">eyeris</span> — change it in Settings after logging in
          </p>
        </div>
      </div>
    </div>
  )
}
