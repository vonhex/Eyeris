import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import App from "./App.jsx"

const root = createRoot(document.getElementById("root"))

// Global error overlay — catches anything that crashes React
let unhandledErrors = []
window.addEventListener("error", (e) => {
  unhandledErrors.push(e.message || String(e))
  console.error("[Global Error]", e.message, e.filename, e.lineno)
})
window.addEventListener("unhandledrejection", (e) => {
  unhandledErrors.push(String(e.reason))
  console.error("[Unhandled Rejection]", e.reason)
})

root.render(
  <StrictMode>
    <App />
  </StrictMode>
)
