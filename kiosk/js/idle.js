/**
 * Idle timeout: after IDLE_SECONDS with no touch/click, calls onWarn() to
 * show the "Are you still there?" prompt; if still no interaction after a
 * further 10 seconds, calls onTimeout() to wipe the session and return to
 * the attract screen.
 *
 * pause()/resume() let app.js suspend idle tracking while it doesn't make
 * sense (e.g. during the processing screen, where a 30-60s wait with zero
 * touches is completely normal, or while the staff menu is open).
 */
const Idle = (() => {
  const WARNING_SECONDS = 10;

  let warnTimer = null;
  let idleSeconds = 60;
  let onWarn = () => {};
  let onTimeout = () => {};
  let paused = true;

  function armWarnTimer() {
    clearTimeout(warnTimer);
    if (paused) return;
    warnTimer = setTimeout(() => onWarn(), idleSeconds * 1000);
  }

  function handleActivity() {
    if (paused) return;
    armWarnTimer();
  }

  function init(options) {
    idleSeconds = options.idleSeconds || 60;
    onWarn = options.onWarn || onWarn;
    onTimeout = options.onTimeout || onTimeout;

    ["pointerdown", "touchstart", "mousedown", "keydown"].forEach((eventName) => {
      document.addEventListener(eventName, handleActivity, { passive: true });
    });
  }

  function resume() {
    paused = false;
    armWarnTimer();
  }

  function pause() {
    paused = true;
    clearTimeout(warnTimer);
  }

  return { init, resume, pause, WARNING_SECONDS };
})();
