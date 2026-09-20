/**
 * Hidden staff access: tapping the invisible top-left corner trigger 5
 * times within 3 seconds fires the callback that opens the PIN pad.
 * Everything else about the staff menu (PIN entry, the menu itself) is
 * wired up in app.js alongside the other overlays.
 */
const Staff = (() => {
  const TAP_COUNT_REQUIRED = 5;
  const WINDOW_MS = 3000;

  let tapTimestamps = [];

  function initCornerTrigger(el, onTriggered) {
    const registerTap = () => {
      const now = Date.now();
      tapTimestamps.push(now);
      tapTimestamps = tapTimestamps.filter((t) => now - t <= WINDOW_MS);
      if (tapTimestamps.length >= TAP_COUNT_REQUIRED) {
        tapTimestamps = [];
        onTriggered();
      }
    };
    el.addEventListener("click", registerTap);
    el.addEventListener("touchstart", (e) => {
      e.preventDefault();
      registerTap();
    });
  }

  function checkPin(candidate) {
    return String(candidate) === String((window.KIOSK_CONFIG || {}).STAFF_PIN);
  }

  return { initCornerTrigger, checkPin };
})();
