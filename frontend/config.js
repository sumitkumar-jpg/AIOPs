// Frontend runtime configuration.
//
// When the frontend is served by FastAPI (local development) requests go to the
// same origin, so the base stays empty.
//
// On Vercel (frontend hosted separately from the Railway backend), set the
// API base to your Railway backend URL, e.g.:
//   window.AIOPS_API_BASE = "https://your-app.up.railway.app";
// (leave the trailing slash OFF).

window.AIOPS_API_BASE = window.AIOPS_API_BASE || "";
