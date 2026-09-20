# Setting up the kiosk PC (Windows mini PC + portrait TV + USB webcam)

This is a one-time setup guide for the physical device in the shop — the
small Windows PC, the portrait-mounted TV or touchscreen, and the USB
webcam. It assumes the kiosk web page is already deployed to Cloudflare
Pages (see `docs/deploy.md`) and you have that URL in hand.

Do these steps roughly in order — some later steps (like the camera
permission trick) depend on decisions made earlier (like using
`--incognito`).

Where this guide says "Settings," it means the Windows Settings app
(Start menu → the gear icon). Menu names shift slightly between Windows
versions — if you don't see the exact item named, search for it using the
search box at the top of Settings.

**A plain TV isn't touch-enabled.** If you're using a regular TV rather
than a touchscreen, customers need some other way to tap the on-screen
buttons — a wireless mouse mounted or shelved near the screen is the
simplest option (every button in the kiosk is sized for touch, but works
identically with a mouse click). A USB/IR touch overlay frame is a
fancier alternative if you want the real touch experience without buying
a touch-native display.

---

## 1. Rotate the display to portrait

1. Right-click an empty spot on the desktop → **Display settings** (or
   Settings → System → Display).
2. Find **Display orientation** and change it from **Landscape** to
   **Portrait**.
3. Windows will preview the change and ask you to confirm within 15
   seconds — click **Keep changes**.
4. If the picture looks upside-down or mirrored compared to how the TV is
   physically mounted, switch to **Portrait (flipped)** instead — one of
   the two will match your mount.

---

## 2. Grant camera permission once, so it's remembered

**Read this before step 3.** We're going to launch Chrome with the
`--incognito` flag (recommended below, for a clean session every time —
no autofill or history quietly building up on a shared kiosk PC). The
catch: Chrome's incognito mode does **not** remember a "camera access:
Allow" you click during one session into the next session — so if you
just click Allow the normal way, the very next time the watchdog or a
reboot relaunches Chrome, the customer would see that permission prompt
again.

The fix is to tell Chrome, at the Windows level, "always allow the camera
for this exact website, no prompt, no matter what" — a setting that
survives incognito mode entirely because it's not a per-session choice.

1. Press **Win+R**, type `regedit`, press Enter (click **Yes** if
   Windows asks for permission).
2. Navigate to:
   ```
   HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Google\Chrome
   ```
   If `Policies`, `Google`, or `Chrome` don't exist yet, right-click each
   parent folder → **New** → **Key**, and name it exactly as shown, until
   you've built out that full path.
3. Inside `Chrome`, right-click → **New** → **Key**, name it
   `VideoCaptureAllowedUrls`.
4. Inside that new key, right-click the empty right-hand pane → **New** →
   **String Value**, name it `1`. Double-click it and set its value to
   your kiosk's exact URL with a wildcard, e.g.:
   ```
   https://your-project.pages.dev/*
   ```
5. Close Registry Editor and restart the PC (or at least fully quit and
   reopen Chrome) for the policy to take effect.

To confirm it worked: open Chrome (not necessarily in kiosk mode) and go
to `chrome://policy` — you should see `VideoCaptureAllowedUrls` listed
under Chrome policies with your URL as its value. From now on, that site
gets camera access silently, every time, incognito or not.

*(If you'd rather skip the registry step: don't use `--incognito` in step
3 below, and just click "Allow" on the camera prompt the first time. A
normal (non-incognito) Chrome profile does remember that choice across
restarts. The trade-off is that a normal profile also quietly accumulates
browsing data over time on a device anyone can walk up to — the registry
approach avoids that entirely.)*

---

## 3. Create the kiosk-mode shortcut

1. Right-click the desktop → **New** → **Shortcut**.
2. For the location, paste (adjust the Chrome path if yours differs):
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --incognito --noerrdialogs --disable-infobars --disable-session-crashed-bubble --no-first-run --no-default-browser-check --disable-pinch --overscroll-history-navigation=0 "https://your-project.pages.dev"
   ```
   (Replace `https://your-project.pages.dev` with your real Cloudflare
   Pages URL.)
3. Name it something like `Kiosk`.

What each flag does, briefly:

| Flag | Why |
|---|---|
| `--kiosk` | Full-screen, no address bar, no tabs, no way out via the UI |
| `--incognito` | Clean session each launch — see the camera note above |
| `--noerrdialogs` | Suppresses Chrome's own error popups |
| `--disable-infobars` | Suppresses notification bars ("Chrome is being controlled...", etc.) |
| `--disable-session-crashed-bubble` | Suppresses the "Chrome didn't shut down properly, restore pages?" prompt after a crash or forced restart |
| `--no-first-run` / `--no-default-browser-check` | Skips first-run welcome screens and the "make default browser" nag |
| `--disable-pinch` | Stops a stray two-finger pinch on the touchscreen from zooming the page |
| `--overscroll-history-navigation=0` | Stops an edge swipe from being read as "back/forward" navigation |

You'll reuse this same command line in the auto-start task and the
watchdog script below, so keep this shortcut around as your reference
copy — or better, save it as `C:\Kiosk\start-kiosk.bat` (one line, same
command) so every other step can just point at that one file instead of
repeating the whole command line.

---

## 4. Auto-start Chrome at login (and auto-login to Windows)

For a true "walk up and it's already running" kiosk, Windows itself needs
to log in without anyone typing a password, and Chrome needs to launch
right after.

### 4a. Auto-login to Windows

1. Press **Win+R**, type `netplwiz`, press Enter.
2. Select the kiosk's Windows user account, untick **"Users must enter a
   user name and password to use this computer,"** click **OK**.
3. Enter that account's password when prompted (it types this into
   registry, encrypted, so it can auto-fill it at every boot).

*(If the checkbox doesn't "stick" — a known quirk on some Windows
builds — set it directly instead: Win+R → `regedit` →
`HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`
→ set `AutoAdminLogon` to `1`, and set `DefaultUsername` /
`DefaultPassword` to the account's credentials.)*

### 4b. Launch Chrome at login

We'll fold this into the same Scheduled Task as the crash-watchdog in
step 6, so it does double duty: instantly launches Chrome the moment you
log in, *and* keeps checking every minute afterward that it's still
running. Skip ahead to step 6 and come back here once it's set up — or,
if you'd rather keep it simpler and skip the watchdog, just drop the
`Kiosk` shortcut from step 3 into the Startup folder:

1. Press **Win+R**, type `shell:startup`, press Enter — this opens your
   user's Startup folder.
2. Copy the `Kiosk` shortcut into it.

That alone makes Chrome launch every time you log in — just without the
auto-recovery-if-it-crashes part that the watchdog task adds.

---

## 5. Prevent sleep and screensaver

A kiosk PC has no upside to sleeping — it's not battery-powered, and a
sleeping or screensaver-locked screen looks broken to a customer walking
up. Simplest is to just turn both off entirely:

1. Settings → System → **Power & battery** (older Windows: **Power &
   sleep**) → under **Screen and sleep**, set every dropdown ("On battery
   power, screen turns off after," "When plugged in, screen turns off
   after," and the matching "sleep" ones) to **Never**.
2. Settings → Personalization → **Lock screen** → **Screen saver** (this
   opens an older-style dialog) → set **Screen saver** to **(None)** →
   **OK**.

*(If you'd rather the PC actually save power overnight while the store's
closed, that's a reasonable thing to want, but it adds complexity — two
Scheduled Tasks that run `powercfg /change standby-timeout-ac 0` at
opening time and a non-zero value at closing time. The default "just
never sleep" above is simpler and is what most kiosks do — the PC is a
dedicated appliance, not something you're trying to save watts on.)*

---

## 6. Set up the crash-watchdog (and auto-start) Scheduled Task

This is one Scheduled Task that does two jobs at once: launches Chrome
the moment you log in, and re-launches it automatically if it ever
crashes, gets killed, or gets force-closed by a confused customer.

### 6a. The watchdog script

Create `C:\Kiosk\watchdog.bat` with:

```bat
@echo off
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I "chrome.exe" >NUL
if errorlevel 1 (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --incognito --noerrdialogs --disable-infobars --disable-session-crashed-bubble --no-first-run --no-default-browser-check --disable-pinch --overscroll-history-navigation=0 "https://your-project.pages.dev"
)
```

(Same URL and flags as your shortcut in step 3 — replace the URL with
your real one.) This checks once whether `chrome.exe` is running; if not,
it starts it; if it's already running, it does nothing. It's meant to be
run repeatedly by Task Scheduler, not looped by itself — that keeps the
script itself simple and nothing-to-crash.

### 6b. The Scheduled Task

1. Open **Task Scheduler** (search for it in the Start menu).
2. **Action** → **Create Task...** (not "Create Basic Task" — we need the
   extra options).
3. **General** tab:
   - Name: `Kiosk Watchdog`
   - Select **"Run whether user is logged on or not"**
   - Tick **"Run with highest privileges"**
4. **Triggers** tab → **New...** → set **Begin the task** to **At log
   on** (any user, or specifically your kiosk account) → **OK**.
5. **Triggers** tab → **New...** again → set **Begin the task** to
   **Daily**, starting a few minutes before your usual opening time →
   tick **Repeat task every** and choose **1 minute**, **for a duration
   of** **Indefinitely** → **OK**.

   (You now have two triggers on one task: one that fires immediately at
   login, and one that keeps firing every minute all day. Both run the
   same action, so either one relaunches Chrome if it's not running.)
6. **Actions** tab → **New...** → **Start a program** → browse to
   `C:\Kiosk\watchdog.bat` → **OK**.
7. **Conditions** tab → untick **"Start the task only if the computer is
   on AC power"** (a kiosk PC is always plugged in, but this box is
   ticked by default and would silently stop the task on a laptop-class
   mini PC).
8. **OK** to save, entering the kiosk account's password if asked.

---

## 7. Pause Windows Update restarts during store hours

Windows won't install updates and force a restart during your declared
**Active hours** — but it will happily do so outside them, which is fine
(that's when the store's closed anyway).

1. Settings → **Windows Update** → **Advanced options** → **Active
   hours**.
2. Switch it to **Manually** if it's on **Automatically**.
3. Set **Start time** to just before opening and **End time** to just
   after closing.

Windows caps this window at **18 hours** — plenty for any normal shop's
hours, but if yours somehow spans longer than that, split the difference
around your busiest period.

This doesn't stop updates from *downloading* in the background (that's
fine, it's silent), only from forcing a *restart* mid-shift. If a restart
is pending, Windows will do it automatically the next time it's outside
active hours.

---

## 8. How to exit kiosk mode

There's an important distinction here: the kiosk web app itself has a
staff menu option called **"Exit kiosk"** (tap the top-left corner 5
times, enter the PIN) — but that only exits the *page's* fullscreen
request, which does nothing here, because Chrome's `--kiosk` command-line
flag is a browser-level window mode that the page has no control over at
all. To actually get out to the Windows desktop, use one of these instead:

- **Alt+F4** — closes the focused Chrome window. Usually works.
- **Ctrl+Alt+Delete**, then choose **Task Manager** → find **Google
  Chrome** → **End task**. Works even if Alt+F4 doesn't respond.
- **Ctrl+Shift+Esc** — opens Task Manager directly, same as above.

Once Chrome is closed, remember the watchdog task will relaunch it within
a minute (that's the whole point) — so if you actually need to leave the
kiosk down for maintenance, also open Task Scheduler and **Disable** the
`Kiosk Watchdog` task first, then re-enable it when you're done.

---

## Daily checklist for staff

### Opening

- [ ] Turn on the TV/screen (the PC itself should already be running —
      it never sleeps, per step 5).
- [ ] If the kiosk page isn't already showing, give it up to a minute —
      the watchdog auto-starts it. If it's still not up after that, see
      "How to exit kiosk mode" above, close any error window, and it
      should relaunch within a minute on its own.
- [ ] Tap the attract screen once yourself to confirm the camera prompt
      does *not* appear (if it does, camera permission wasn't set up
      correctly — see step 2) and that a test photo captures cleanly.
- [ ] Wipe the camera lens and the touchscreen (if present) with a clean
      cloth.

### Closing

- [ ] If a customer's photo/result is currently on screen, tap **Start
      over** so nothing lingers on the screen overnight (it's held only
      in memory and vanishes on its own after 60–70 seconds of no touch
      or on the next customer's "Start over" anyway, but there's no
      reason to leave it up).
- [ ] Turn off the TV/screen. Leave the PC itself running — it needs to
      stay on for Windows Update's active-hours window and for the
      watchdog to keep it ready for tomorrow.
- [ ] If anything seemed slow or glitchy that day, use the staff menu's
      "Show last error" (tap the top-left corner 5 times, enter the PIN)
      and note it down for whoever manages the kiosk.
