/**
 * getUserMedia handling: start/stop the live preview, and capture +
 * crop + resize a frame to a portrait ~768x1152 JPEG.
 */
const Camera = (() => {
  const TARGET_WIDTH = 768;
  const TARGET_HEIGHT = 1152; // 2:3 portrait, matches the on-screen frame

  let stream = null;

  /** Returns a user-friendly message for a getUserMedia error. */
  function describeError(err) {
    switch (err.name) {
      case "NotAllowedError":
      case "SecurityError":
        return "Camera access was denied. Please allow camera access for this page and try again.";
      case "NotFoundError":
      case "OverconstrainedError":
        return "No camera was found on this device.";
      case "NotReadableError":
        return "The camera is already in use by another app.";
      default:
        return "Something went wrong accessing the camera.";
    }
  }

  /**
   * Resolves once the video element has genuinely decoded a real frame
   * (readyState >= HAVE_CURRENT_DATA, non-zero dimensions) - not just once
   * play() has resolved, which on some browsers/devices happens slightly
   * before real frame data is actually available. Polls via
   * requestAnimationFrame rather than a fixed delay, so it's as fast as
   * the device allows but never proceeds on a still-black video.
   */
  function waitUntilFrameReady(videoEl, timeoutMs = 8000) {
    return new Promise((resolve, reject) => {
      const start = performance.now();
      function check() {
        if (videoEl.readyState >= 2 && videoEl.videoWidth > 0 && videoEl.videoHeight > 0) {
          console.log(
            `[Camera] frame ready after ${(performance.now() - start).toFixed(0)}ms:`,
            `videoWidth=${videoEl.videoWidth} videoHeight=${videoEl.videoHeight} readyState=${videoEl.readyState}`
          );
          resolve();
          return;
        }
        if (performance.now() - start > timeoutMs) {
          reject(
            new Error(
              `Timed out waiting for the camera to produce a frame (videoWidth=${videoEl.videoWidth}, ` +
                `videoHeight=${videoEl.videoHeight}, readyState=${videoEl.readyState}).`
            )
          );
          return;
        }
        requestAnimationFrame(check);
      }
      check();
    });
  }

  async function start(videoEl) {
    stop(); // in case a previous stream is still open
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1080 },
          height: { ideal: 1920 },
        },
        audio: false,
      });
    } catch (err) {
      throw new Error(describeError(err));
    }
    videoEl.srcObject = stream;
    await videoEl.play();
    // Don't consider the camera "live" (and don't let the customer see a
    // Capture button) until a real frame has actually decoded - see
    // waitUntilFrameReady's comment for why play() resolving isn't enough
    // on its own.
    try {
      await waitUntilFrameReady(videoEl);
    } catch (err) {
      throw new Error("The camera started but never produced a picture - please try again.");
    }
  }

  function stop() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
  }

  /**
   * Captures the current video frame, center-crops it to a 2:3 portrait
   * rectangle (matching what the customer sees framed on screen regardless
   * of the camera's native aspect ratio), then downsizes to ~768x1152.
   * Returns { dataUrl, base64 } where base64 has no "data:...;base64,"
   * prefix, ready to send straight to the backend.
   */
  function capture(videoEl) {
    // Diagnostic: log the exact state at the moment of capture. If this
    // ever produces a black result again, these numbers (plus the
    // "[Camera] after drawImage" log below) tell us definitively whether
    // it's a not-ready video, a dead/stopped stream, or something else -
    // rather than guessing again (2026-09-21).
    const track = stream ? stream.getVideoTracks()[0] : null;
    console.log(
      "[Camera] capture() called:",
      `videoWidth=${videoEl.videoWidth}`,
      `videoHeight=${videoEl.videoHeight}`,
      `readyState=${videoEl.readyState}`,
      `paused=${videoEl.paused}`,
      `streamActive=${stream ? stream.active : "no stream"}`,
      `trackReadyState=${track ? track.readyState : "no track"}`,
      `trackEnabled=${track ? track.enabled : "n/a"}`
    );

    // If the video element hasn't actually decoded a frame yet (videoWidth/
    // videoHeight are 0), drawImage below silently draws nothing rather
    // than throwing - the canvas is left in its default transparent state,
    // which toDataURL("image/jpeg", ...) then flattens to solid opaque
    // BLACK (JPEG has no alpha channel). That produced a "successful"
    // capture that was actually a black photo, with no error anywhere
    // (2026-09-21). Guard against it explicitly instead.
    if (!videoEl.videoWidth || !videoEl.videoHeight || videoEl.readyState < 2) {
      throw new Error("The camera isn't ready yet - please wait a moment and try again.");
    }
    if (!stream || !stream.active || !track || track.readyState !== "live") {
      throw new Error("The camera stream stopped unexpectedly - please try again.");
    }

    const videoWidth = videoEl.videoWidth;
    const videoHeight = videoEl.videoHeight;
    const targetAspect = TARGET_WIDTH / TARGET_HEIGHT;
    const sourceAspect = videoWidth / videoHeight;

    let cropWidth = videoWidth;
    let cropHeight = videoHeight;
    if (sourceAspect > targetAspect) {
      cropWidth = videoHeight * targetAspect;
    } else {
      cropHeight = videoWidth / targetAspect;
    }
    const cropX = (videoWidth - cropWidth) / 2;
    const cropY = (videoHeight - cropHeight) / 2;

    // Canvas dimensions are fixed constants (not derived from any DOM
    // element's size) and are set before drawImage runs - setting
    // canvas.width/height AFTER drawing would reset/clear the canvas, so
    // order matters here and is deliberate.
    const canvas = document.createElement("canvas");
    canvas.width = TARGET_WIDTH;
    canvas.height = TARGET_HEIGHT;
    const ctx = canvas.getContext("2d");

    // Mirror horizontally to match the mirrored live preview the customer saw.
    ctx.translate(TARGET_WIDTH, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(videoEl, cropX, cropY, cropWidth, cropHeight, 0, 0, TARGET_WIDTH, TARGET_HEIGHT);

    // Sample a spread-out grid (not just the center - a real photo can
    // legitimately have a black pixel at any single point, e.g. dark hair
    // or clothing) to catch a genuinely empty/untouched canvas before it
    // ever reaches the customer as a fake-looking "successful" result. A
    // truly blank canvas is black at *every* point; a real photo essentially
    // never is at all 25 of these simultaneously.
    const GRID = 5;
    let blackPoints = 0;
    let maxChannel = 0;
    for (let gx = 0; gx < GRID; gx++) {
      for (let gy = 0; gy < GRID; gy++) {
        const x = Math.floor(((gx + 0.5) / GRID) * TARGET_WIDTH);
        const y = Math.floor(((gy + 0.5) / GRID) * TARGET_HEIGHT);
        const [r, g, b] = ctx.getImageData(x, y, 1, 1).data;
        maxChannel = Math.max(maxChannel, r, g, b);
        if (r < 3 && g < 3 && b < 3) blackPoints++;
      }
    }
    console.log(
      "[Camera] after drawImage:",
      `canvas=${canvas.width}x${canvas.height}`,
      `crop=${cropWidth.toFixed(0)}x${cropHeight.toFixed(0)}@${cropX.toFixed(0)},${cropY.toFixed(0)}`,
      `blackPoints=${blackPoints}/${GRID * GRID}`,
      `maxChannelValue=${maxChannel}`
    );
    if (blackPoints === GRID * GRID) {
      throw new Error("The captured photo came out black - please try again.");
    }

    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    const base64 = dataUrl.split(",")[1];
    return { dataUrl, base64 };
  }

  return { start, stop, capture };
})();
