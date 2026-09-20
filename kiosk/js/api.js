/**
 * All calls to the backend (backend/app.py running on Modal), plus the
 * demo-mode shortcuts that avoid calling it at all. See config.js for
 * DEMO_MODE.
 */
const Api = (() => {
  const TRYON_TIMEOUT_MS = 60_000;
  const WARMUP_TIMEOUT_MS = 20_000;
  const HEALTH_TIMEOUT_MS = 10_000;

  function config() {
    return window.KIOSK_CONFIG || {};
  }

  async function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error("The request took too long and was cancelled (slow network).");
      }
      throw new Error("Could not reach the try-on service (backend offline or unreachable).");
    } finally {
      clearTimeout(timer);
    }
  }

  /** POST /warmup - fire this the moment the attract screen is tapped. */
  async function warmup() {
    if (config().DEMO_MODE) {
      return { status: "ready (demo mode)" };
    }
    const response = await fetchWithTimeout(
      `${config().API_URL}/warmup`,
      { method: "POST", headers: { "X-Kiosk-Token": config().KIOSK_TOKEN } },
      WARMUP_TIMEOUT_MS
    );
    if (!response.ok) {
      throw new Error(`warmup failed: HTTP ${response.status}`);
    }
    return response.json();
  }

  /**
   * POST /tryon. `payload` is either
   *   { person_image, garment_image, category }
   * or
   *   { person_image, passes: [{garment_image, category}, ...] }
   *
   * In demo mode, skips the network entirely and echoes the person photo
   * back as a fake "result" after a short simulated delay, so the whole
   * screen flow can be tested without a deployed backend or GPU spend.
   */
  async function tryOn(payload) {
    if (config().DEMO_MODE) {
      await new Promise((resolve) => setTimeout(resolve, 1800));
      return {
        result_image: payload.person_image,
        processing_time_seconds: 1.8,
      };
    }

    const response = await fetchWithTimeout(
      `${config().API_URL}/tryon`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Kiosk-Token": config().KIOSK_TOKEN,
        },
        body: JSON.stringify(payload),
      },
      TRYON_TIMEOUT_MS
    );

    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).detail || "";
      } catch (_) {
        // response body wasn't JSON - ignore, we still have the status code
      }
      if (response.status === 429) {
        throw new Error("Too many try-ons right now - please wait a few minutes and try again.");
      }
      throw new Error(`Try-on failed (HTTP ${response.status})${detail ? ": " + detail : ""}`);
    }

    return response.json();
  }

  /**
   * Staff "Test backend" check. There isn't a lightweight /health route on
   * this same API_URL (the backend's real GET /health lives on a separate,
   * GPU-less URL - see backend/README.md); calling /warmup here is a more
   * useful diagnostic anyway, since it also proves the auth token and the
   * GPU container path both work, not just that a web server is up.
   */
  async function testBackend() {
    if (config().DEMO_MODE) {
      return { ok: true, detail: "Demo mode is on - no real backend was contacted." };
    }
    const start = performance.now();
    try {
      const response = await fetchWithTimeout(
        `${config().API_URL}/warmup`,
        { method: "POST", headers: { "X-Kiosk-Token": config().KIOSK_TOKEN } },
        HEALTH_TIMEOUT_MS
      );
      const elapsed = ((performance.now() - start) / 1000).toFixed(1);
      if (!response.ok) {
        return { ok: false, detail: `HTTP ${response.status} after ${elapsed}s` };
      }
      return { ok: true, detail: `Responded in ${elapsed}s` };
    } catch (err) {
      return { ok: false, detail: err.message };
    }
  }

  return { warmup, tryOn, testBackend };
})();
