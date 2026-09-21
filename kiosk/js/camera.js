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

    const canvas = document.createElement("canvas");
    canvas.width = TARGET_WIDTH;
    canvas.height = TARGET_HEIGHT;
    const ctx = canvas.getContext("2d");

    // Mirror horizontally to match the mirrored live preview the customer saw.
    ctx.translate(TARGET_WIDTH, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(videoEl, cropX, cropY, cropWidth, cropHeight, 0, 0, TARGET_WIDTH, TARGET_HEIGHT);

    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    const base64 = dataUrl.split(",")[1];
    return { dataUrl, base64 };
  }

  return { start, stop, capture };
})();
