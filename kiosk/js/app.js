/**
 * Main kiosk state machine. Wires together Catalogue, Api, Camera, Idle
 * and Staff into the actual screen flow.
 */
(() => {
  "use strict";

  // --- session state -------------------------------------------------------
  // Everything here is customer data and lives ONLY in this JS variable -
  // never localStorage/sessionStorage/IndexedDB/cookies. wipeSession()
  // clears it completely on Start Over, idle timeout, or a fatal error.

  function freshSession() {
    return {
      personPhotoBase64: null, // no "data:...;base64," prefix
      personPhotoDataUrl: null, // for <img>/preview display
      department: null,
      style: null, // { id, name }
      fabric: null, // catalogue item
      currentResult: null, // { imageDataUrl, fabric, style }
      recentResults: [], // up to 3, most recent last
    };
  }

  let session = freshSession();

  // Diagnostics are NOT customer data (no photos, just short text) and are
  // deliberately kept OUTSIDE `session` so they survive a session wipe -
  // staff need to see the last error even after the kiosk has reset.
  const diagnostics = { lastError: null };

  function recordError(context, err) {
    diagnostics.lastError = `[${new Date().toLocaleTimeString()}] ${context}: ${err.message || err}`;
    console.error(context, err);
  }

  // --- DOM refs --------------------------------------------------------------

  const screens = {};
  document.querySelectorAll(".screen").forEach((el) => {
    screens[el.id.replace("screen-", "")] = el;
  });

  const el = (id) => document.getElementById(id);

  // --- screen management -------------------------------------------------

  let currentScreenName = null;

  function goToScreen(name) {
    Object.values(screens).forEach((s) => s.classList.remove("is-active"));
    const target = screens[name];
    if (!target) {
      console.error("Unknown screen:", name);
      return;
    }
    target.classList.add("is-active");
    currentScreenName = name;

    // Idle tracking only makes sense while a customer might reasonably be
    // expected to touch something. It's paused on attract (that IS the
    // resting state) and on processing (a 30-60s wait with no touches is
    // normal there, not idleness).
    if (name === "attract" || name === "processing") {
      Idle.pause();
    } else {
      Idle.resume();
    }
  }

  // --- boot ------------------------------------------------------------------

  async function boot() {
    const config = window.KIOSK_CONFIG;
    if (!config || !config.API_URL || !config.KIOSK_TOKEN) {
      showFatalError(
        "kiosk/config.js is missing or incomplete. Copy kiosk/config.example.js to " +
          "kiosk/config.js and fill in your values (see kiosk/README.md)."
      );
      return;
    }

    el("attract-store-name").textContent = config.STORE_NAME || "Our Store";
    if (config.LOGO_PATH) {
      const logo = el("attract-logo");
      logo.src = config.LOGO_PATH;
      logo.hidden = false;
      logo.onerror = () => {
        logo.hidden = true;
      };
    }
    el("demo-badge").classList.toggle("is-active", !!config.DEMO_MODE);

    try {
      await Catalogue.load();
    } catch (err) {
      recordError("loading catalogue", err);
      showFatalError("Could not load the fabric catalogue. Please check your connection and try again.");
      return;
    }

    Idle.init({
      idleSeconds: config.IDLE_SECONDS || 60,
      onWarn: showIdleWarning,
      onTimeout: () => {
        hideOverlay("overlay-idle");
        wipeSessionAndReturnToAttract();
      },
    });

    Staff.initCornerTrigger(el("staff-trigger"), openStaffPin);

    goToScreen("attract");
  }

  function showFatalError(message) {
    el("fatal-error-message").textContent = message;
    goToScreen("fatal-error");
  }

  el("fatal-error-retry").addEventListener("click", () => {
    window.location.reload();
  });

  // --- 1. Attract screen ---------------------------------------------------

  el("attract-tapzone").addEventListener("click", () => {
    // Fire-and-forget: don't make the customer wait on this, and don't
    // block the flow if it fails - they'll just eat the cold-start
    // latency on their actual /tryon call instead.
    Api.warmup().catch((err) => recordError("warmup", err));
    goToScreen("consent");
  });

  // --- 2. Consent screen ---------------------------------------------------

  el("consent-agree").addEventListener("click", () => {
    goToScreen("camera");
    startCameraFlow();
  });
  el("consent-cancel").addEventListener("click", () => goToScreen("attract"));

  // --- 3. Camera screen -----------------------------------------------------

  let countdownTimer = null;

  function setCameraState(state) {
    // state: "live" | "review" | "error"
    el("camera-controls-live").hidden = state !== "live";
    el("camera-controls-review").hidden = state !== "review";
    el("camera-controls-error").hidden = state !== "error";
    el("camera-error").classList.toggle("is-active", state === "error");
    el("camera-tips").hidden = state === "error";
    el("camera-video").hidden = state === "review";
    el("camera-captured").hidden = state !== "review";
    el("camera-silhouette").hidden = state !== "live";
  }

  async function startCameraFlow() {
    setCameraState("live");
    try {
      await Camera.start(el("camera-video"));
    } catch (err) {
      recordError("camera start", err);
      el("camera-error").textContent = err.message;
      setCameraState("error");
    }
  }

  el("camera-retry").addEventListener("click", startCameraFlow);

  el("camera-back").addEventListener("click", () => {
    Camera.stop();
    clearInterval(countdownTimer);
    goToScreen("consent");
  });

  el("camera-capture").addEventListener("click", () => {
    let remaining = 5;
    const countdownEl = el("camera-countdown");
    countdownEl.textContent = String(remaining);
    countdownEl.parentElement.classList.add("is-active");
    countdownTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(countdownTimer);
        countdownEl.parentElement.classList.remove("is-active");
        doCapture();
      } else {
        countdownEl.textContent = String(remaining);
      }
    }, 1000);
  });

  function doCapture() {
    // Was previously unguarded: if Camera.capture() failed (e.g. the video
    // wasn't actually ready), the exception vanished silently and the
    // customer never saw an error - see the camera.js comment for what
    // that looked like from their side (a black "result"). Route any
    // capture failure to the same error UI camera-start failures use.
    try {
      const { dataUrl, base64 } = Camera.capture(el("camera-video"));
      session.personPhotoDataUrl = dataUrl;
      session.personPhotoBase64 = base64;
      el("camera-captured").src = dataUrl;
      setCameraState("review");
    } catch (err) {
      recordError("camera capture", err);
      el("camera-error").textContent = err.message || "Could not capture a photo - please try again.";
      setCameraState("error");
    }
  }

  el("camera-use-photo").addEventListener("click", () => {
    Camera.stop();
    populateDepartments();
    goToScreen("department");
  });

  el("camera-retake").addEventListener("click", () => {
    session.personPhotoBase64 = null;
    session.personPhotoDataUrl = null;
    setCameraState("live");
  });

  // --- 4. Department screen ---------------------------------------------

  function populateDepartments() {
    const grid = el("department-grid");
    grid.innerHTML = "";
    const departments = Catalogue.getDepartments();
    if (departments.length === 0) {
      grid.innerHTML = '<p class="empty-state">No fabrics have been published to the kiosk yet. Please check back soon.</p>';
      return;
    }
    for (const dept of departments) {
      const btn = document.createElement("button");
      btn.className = "choice-card";
      btn.textContent = dept.label;
      btn.addEventListener("click", () => {
        session.department = dept.id;
        populateStyles(dept.id, dept.label);
        goToScreen("style");
      });
      grid.appendChild(btn);
    }
  }

  document.querySelectorAll('[data-go="attract"]').forEach((btnEl) => {
    btnEl.addEventListener("click", () => {
      Camera.stop();
      goToScreen("attract");
    });
  });
  document.querySelectorAll('[data-go="department"]').forEach((btnEl) => {
    btnEl.addEventListener("click", () => goToScreen("department"));
  });
  document.querySelectorAll('[data-go="style"]').forEach((btnEl) => {
    btnEl.addEventListener("click", () => goToScreen("style"));
  });

  // --- 5. Style screen -----------------------------------------------------

  function populateStyles(departmentId, departmentLabel) {
    el("style-heading").textContent = `${departmentLabel}: choose a style`;
    const grid = el("style-grid");
    grid.innerHTML = "";
    const styles = Catalogue.getStyles(departmentId);
    if (styles.length === 0) {
      grid.innerHTML = '<p class="empty-state">No styles available in this department yet.</p>';
      return;
    }
    for (const style of styles) {
      const btn = document.createElement("button");
      btn.className = "choice-card";
      btn.textContent = style.name;
      btn.addEventListener("click", () => {
        session.style = style;
        populateFabrics(departmentId, style.id, style.name);
        goToScreen("fabric");
      });
      grid.appendChild(btn);
    }
  }

  // --- 6. Fabric screen ------------------------------------------------------

  function populateFabrics(departmentId, styleId, styleName) {
    el("fabric-heading").textContent = `${styleName}: choose a fabric`;
    const grid = el("fabric-grid");
    grid.innerHTML = "";
    const fabrics = Catalogue.getFabrics(departmentId, styleId);
    if (fabrics.length === 0) {
      grid.innerHTML = '<p class="empty-state">No fabrics available for this style yet.</p>';
      return;
    }
    for (const item of fabrics) {
      const card = document.createElement("button");
      card.className = "fabric-card";
      card.innerHTML = `
        <img src="${item.swatch}" alt="${item.fabric_name}">
        <span class="fabric-name">${item.fabric_name}</span>
        <span class="fabric-code">${item.fabric_code}</span>
      `;
      card.addEventListener("click", () => {
        session.fabric = item;
        goToScreen("processing");
        runTryOn();
      });
      grid.appendChild(card);
    }
  }

  // --- 7. Processing screen ---------------------------------------------

  const PROCESSING_MESSAGES = [
    "Preparing your preview…",
    "Draping the fabric…",
    "Tailoring the fit…",
    "Adding the finishing touches…",
    "Almost ready…",
  ];
  let processingMessageTimer = null;

  function startProcessingMessages() {
    let i = 0;
    el("processing-message").textContent = PROCESSING_MESSAGES[0];
    el("processing-error-controls").hidden = true;
    processingMessageTimer = setInterval(() => {
      i = (i + 1) % PROCESSING_MESSAGES.length;
      el("processing-message").textContent = PROCESSING_MESSAGES[i];
    }, 3200);
  }

  function stopProcessingMessages() {
    clearInterval(processingMessageTimer);
  }

  // Same-origin catalogue image fetches need their own timeout, same as
  // the backend calls in api.js get via fetchWithTimeout - otherwise a
  // stalled connection here hangs the processing screen forever with no
  // error shown, which is exactly the "stuck on loading" bug this was
  // written to fix (2026-09-21).
  const IMAGE_FETCH_TIMEOUT_MS = 20_000;

  async function fetchImageAsBase64(url) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), IMAGE_FETCH_TIMEOUT_MS);
    let response;
    try {
      response = await fetch(url, { cache: "force-cache", signal: controller.signal });
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error("Loading the garment image took too long - please check your connection and try again.");
      }
      throw new Error(`Could not load ${url}: ${err.message}`);
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) {
      throw new Error(`Could not load ${url} (HTTP ${response.status})`);
    }
    const blob = await response.blob();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = () => reject(new Error("Could not read image data"));
      reader.readAsDataURL(blob);
    });
  }

  function buildTryOnPayload(personBase64, garmentBase64, tryonPlan) {
    if (Array.isArray(tryonPlan)) {
      return {
        person_image: personBase64,
        passes: tryonPlan.map((category) => ({ garment_image: garmentBase64, category })),
      };
    }
    return { person_image: personBase64, garment_image: garmentBase64, category: tryonPlan };
  }

  // Belt-and-braces top-level timeout: whatever might hang inside runTryOn
  // (now or after a future change), the customer never gets stuck on the
  // processing screen with no way out - they always land on a friendly
  // retry message within this many seconds.
  const PROCESSING_TIMEOUT_MS = 45_000;

  function withTimeout(promise, ms, message) {
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), ms);
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
  }

  // Incremented on every runTryOn() call so a stale attempt (e.g. one that
  // times out client-side but is still running in the background) can
  // never clobber the screen state of a newer retry/attempt that
  // superseded it.
  let tryOnGeneration = 0;

  async function runTryOn() {
    const myGeneration = ++tryOnGeneration;
    startProcessingMessages();
    try {
      const work = (async () => {
        const garmentBase64 = await fetchImageAsBase64(session.fabric.image);
        const payload = buildTryOnPayload(session.personPhotoBase64, garmentBase64, session.fabric.tryon_plan);
        return Api.tryOn(payload);
      })();
      const result = await withTimeout(
        work,
        PROCESSING_TIMEOUT_MS,
        "This is taking longer than expected - please try again."
      );
      if (myGeneration !== tryOnGeneration) return; // superseded by a newer attempt

      stopProcessingMessages();
      const imageDataUrl = `data:image/jpeg;base64,${result.result_image}`;
      session.currentResult = { imageDataUrl, fabric: session.fabric, style: session.style };
      session.recentResults.push(session.currentResult);
      if (session.recentResults.length > 3) {
        session.recentResults.shift();
      }
      showResult(session.currentResult);
      goToScreen("result");
    } catch (err) {
      if (myGeneration !== tryOnGeneration) return;
      stopProcessingMessages();
      recordError("try-on", err);
      el("processing-message").textContent = err.message || "Something went wrong generating your preview.";
      el("processing-error-controls").hidden = false;
    }
  }

  el("processing-retry").addEventListener("click", () => {
    goToScreen("processing");
    runTryOn();
  });

  // --- 8. Result screen -------------------------------------------------

  function showResult(result) {
    // Diagnostic (2026-09-21): if a capture-time black-frame check in
    // camera.js ever passes clean but the customer still sees a black
    // result, these logs prove the bug is downstream of capture (payload
    // handling, or the <img> failing to decode) rather than in capture
    // itself - length/prefix of what we're about to display, plus
    // naturalWidth/Height once the browser actually decodes it.
    console.log(
      "[Result] displaying image:",
      `dataUrlLength=${result.imageDataUrl.length}`,
      `prefix=${result.imageDataUrl.slice(0, 40)}`
    );
    const img = el("result-image");
    img.onload = () => console.log(`[Result] image decoded OK: naturalWidth=${img.naturalWidth} naturalHeight=${img.naturalHeight}`);
    img.onerror = () => console.error("[Result] image FAILED to decode/load - src was invalid or corrupted");
    img.src = result.imageDataUrl;
    el("result-swatch").src = result.fabric.swatch;
    el("result-fabric-name").textContent = result.fabric.fabric_name;
    el("result-fabric-code").textContent = result.fabric.fabric_code;
  }

  el("result-another-fabric").addEventListener("click", () => {
    populateFabrics(session.department, session.style.id, session.style.name);
    goToScreen("fabric");
  });

  el("result-another-style").addEventListener("click", () => {
    const departments = Catalogue.getDepartments();
    const label = (departments.find((d) => d.id === session.department) || {}).label || session.department;
    populateStyles(session.department, label);
    goToScreen("style");
  });

  el("result-start-over").addEventListener("click", wipeSessionAndReturnToAttract);

  el("result-compare").addEventListener("click", () => {
    const grid = el("compare-grid");
    grid.innerHTML = "";
    for (const r of session.recentResults) {
      const item = document.createElement("div");
      item.className = "compare-item";
      item.innerHTML = `
        <div class="result-image-frame"><img src="${r.imageDataUrl}" alt="${r.fabric.fabric_name}"></div>
        <div class="label">${r.style.name} &middot; ${r.fabric.fabric_name}</div>
      `;
      grid.appendChild(item);
    }
    showOverlay("overlay-compare");
  });
  el("compare-close").addEventListener("click", () => hideOverlay("overlay-compare"));

  // --- overlays: shared helpers -------------------------------------------

  function showOverlay(id) {
    el(id).classList.add("is-active");
    Idle.pause();
  }
  function hideOverlay(id) {
    el(id).classList.remove("is-active");
    if (currentScreenName !== "attract" && currentScreenName !== "processing") {
      Idle.resume();
    }
  }

  // --- idle warning ---------------------------------------------------------

  let idleWarningTimer = null;

  function showIdleWarning() {
    let remaining = Idle.WARNING_SECONDS;
    el("idle-countdown").textContent = String(remaining);
    showOverlay("overlay-idle");
    idleWarningTimer = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(idleWarningTimer);
        hideOverlay("overlay-idle");
        wipeSessionAndReturnToAttract();
      } else {
        el("idle-countdown").textContent = String(remaining);
      }
    }, 1000);
  }

  el("idle-still-here").addEventListener("click", dismissIdleWarning);
  el("overlay-idle").addEventListener("click", (e) => {
    if (e.target.id === "overlay-idle") dismissIdleWarning();
  });

  function dismissIdleWarning() {
    clearInterval(idleWarningTimer);
    hideOverlay("overlay-idle");
  }

  function wipeSessionAndReturnToAttract() {
    Camera.stop();
    clearInterval(countdownTimer);
    stopProcessingMessages();
    session = freshSession();
    goToScreen("attract");
  }

  // --- staff menu -----------------------------------------------------------

  let pinEntered = "";

  function buildPinGrid() {
    const grid = el("pin-grid");
    grid.innerHTML = "";
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Clear", "0", "⌫"];
    for (const key of keys) {
      const btn = document.createElement("button");
      btn.textContent = key;
      btn.addEventListener("click", () => handlePinKey(key));
      grid.appendChild(btn);
    }
  }

  function handlePinKey(key) {
    if (key === "Clear") {
      pinEntered = "";
    } else if (key === "⌫") {
      pinEntered = pinEntered.slice(0, -1);
    } else {
      pinEntered += key;
    }
    el("pin-display").textContent = pinEntered.replace(/./g, "●");
    el("pin-error").textContent = "";

    const expectedLength = String((window.KIOSK_CONFIG || {}).STAFF_PIN || "").length;
    if (pinEntered.length >= expectedLength && expectedLength > 0) {
      if (Staff.checkPin(pinEntered)) {
        pinEntered = "";
        hideOverlay("overlay-staff-pin");
        openStaffMenu();
      } else {
        el("pin-error").textContent = "Incorrect PIN";
        pinEntered = "";
        setTimeout(() => (el("pin-display").textContent = ""), 300);
      }
    }
  }

  function openStaffPin() {
    pinEntered = "";
    el("pin-display").textContent = "";
    el("pin-error").textContent = "";
    buildPinGrid();
    showOverlay("overlay-staff-pin");
  }

  el("pin-cancel").addEventListener("click", () => {
    pinEntered = "";
    hideOverlay("overlay-staff-pin");
  });

  function openStaffMenu() {
    el("staff-status").hidden = true;
    showOverlay("overlay-staff-menu");
  }

  function setStaffStatus(text) {
    const statusEl = el("staff-status");
    statusEl.textContent = text;
    statusEl.hidden = false;
  }

  el("staff-reload-catalogue").addEventListener("click", async () => {
    setStaffStatus("Reloading catalogue…");
    try {
      const items = await Catalogue.load();
      setStaffStatus(`Catalogue reloaded: ${items.length} item(s).`);
    } catch (err) {
      recordError("staff reload catalogue", err);
      setStaffStatus(`Failed to reload catalogue: ${err.message}`);
    }
  });

  el("staff-test-backend").addEventListener("click", async () => {
    setStaffStatus("Testing backend…");
    const result = await Api.testBackend();
    setStaffStatus(result.ok ? `Backend OK. ${result.detail}` : `Backend problem: ${result.detail}`);
  });

  el("staff-show-error").addEventListener("click", () => {
    setStaffStatus(diagnostics.lastError || "No errors recorded since the kiosk started.");
  });

  el("staff-exit-kiosk").addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      }
      setStaffStatus("Exited fullscreen. Close this browser window/tab to fully exit kiosk mode.");
    } catch (err) {
      setStaffStatus(`Could not exit fullscreen automatically: ${err.message}. Close the browser window manually.`);
    }
  });

  el("staff-menu-close").addEventListener("click", () => hideOverlay("overlay-staff-menu"));

  // --- go --------------------------------------------------------------------

  boot();
})();
