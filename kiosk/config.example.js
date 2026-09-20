/**
 * Kiosk configuration.
 *
 * Copy this file to config.js and fill in your real values:
 *   cp kiosk/config.example.js kiosk/config.js
 * (kiosk/config.js is already excluded from git by the root .gitignore.)
 *
 * IMPORTANT - read this before you worry about KIOSK_TOKEN being a secret:
 * This file is loaded directly into the customer's browser, so its
 * contents - INCLUDING KIOSK_TOKEN - are visible to anyone who views the
 * page source or opens browser dev tools on the kiosk screen. Do not
 * treat KIOSK_TOKEN as a real secret, and never put anything more
 * sensitive than it here (no other API keys belong in this file). The
 * actual protection against someone abusing your GPU with this token is
 * on the backend: its rate limit (30 try-ons per 10 minutes) and its
 * max-1-container cap (see backend/README.md and backend/app.py). Rotate
 * KIOSK_TOKEN with `modal secret create vton-secrets KIOSK_TOKEN=...` if
 * you ever suspect it's being abused.
 */
window.KIOSK_CONFIG = {
  // Base URL for the backend's /warmup and /tryon endpoints - this is the
  // "VTONModel.web" URL printed by `modal deploy backend/app.py` (see
  // backend/README.md), with no trailing slash.
  API_URL: "https://your-workspace--tailor-vton-backend-vtonmodel-web.modal.run",

  // Must match the KIOSK_TOKEN value in the backend's "vton-secrets" Modal
  // secret. Sent as the X-Kiosk-Token header on every /warmup and /tryon
  // request.
  KIOSK_TOKEN: "replace-with-your-kiosk-token",

  // Shown on the attract screen and elsewhere in the UI.
  STORE_NAME: "Your Store Name",

  // Path (relative to kiosk/index.html) to your logo image. If it's
  // missing, the kiosk falls back to showing STORE_NAME as text only.
  LOGO_PATH: "assets/logo.png",

  // 4-6 digit PIN staff enter to reach the hidden staff menu (tap the
  // top-left corner 5 times within 3 seconds to open the PIN pad).
  STAFF_PIN: "1234",

  // Seconds of no touch before the "Are you still there?" prompt appears.
  IDLE_SECONDS: 60,

  // When true, the kiosk never calls the real backend. /warmup resolves
  // instantly and /tryon returns the customer's own captured photo back
  // as a fake "result" after a short simulated delay, with a visible
  // "DEMO MODE" badge. Use this to test the full screen flow (camera,
  // navigation, idle timeout, staff menu, etc.) on a laptop or phone
  // without a deployed backend and without spending any GPU credit.
  // Set back to false before using this in front of real customers.
  DEMO_MODE: true,
};
