import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { api } from "./lib/api";
import "./index.css";

// ── Global JS xato hisoboti (K5) — backendga yuboriladi, cheklangan ──
const seenErrors = new Set<string>();
let reportCount = 0;

function reportError(message: string, context: string) {
  if (!message || reportCount >= 10) return;
  const key = message.slice(0, 200);
  if (seenErrors.has(key)) return;
  seenErrors.add(key);
  reportCount += 1;
  api.reportClientError(message.slice(0, 2000), context);
}

window.addEventListener("error", (e) => {
  const where = e.filename ? ` @ ${e.filename}:${e.lineno}` : "";
  reportError(`${e.message}${where}`, "window.error");
});

window.addEventListener("unhandledrejection", (e) => {
  const reason = e.reason;
  const msg =
    reason instanceof Error
      ? `${reason.message}\n${reason.stack ?? ""}`
      : String(reason);
  reportError(msg, "unhandledrejection");
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
