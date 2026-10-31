// Where the browser reaches the Nimbus API.

/**
 * REST calls are same-origin: next.config.ts rewrites /api/* to the backend, so the session
 * cookie is first-party and survives browsers that block third-party cookies.
 */
export const API_BASE = "";

/**
 * WebSockets can't go through the rewrite on Vercel, so they connect to the backend directly and
 * authenticate with a short-lived ticket from POST /api/tasks/{id}/stream-ticket.
 */
export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  (process.env.NODE_ENV === "development" ? "ws://localhost:8000" : "wss://nimbus-api-l32h.onrender.com");
