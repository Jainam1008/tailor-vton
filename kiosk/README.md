# kiosk

The web page customers actually use at the kiosk terminal.

Plain HTML/CSS/JavaScript — no framework, no build step. Takes a photo of
the customer, lets them pick a department/style/fabric from the catalogue
(produced offline by `catalogue/`), calls the live try-on backend
(`backend/`), and shows the result. Hosted on
[Cloudflare Pages](https://pages.cloudflare.com).

The customer's photo and every try-on result live only in browser memory
(a plain JavaScript variable) for the length of that one session — never
in `localStorage`, `sessionStorage`, `IndexedDB`, or a cookie, and never
uploaded anywhere except directly to the backend for processing. Starting
over, or 60+10 seconds of no touch, wipes it.

## Testing this on your laptop or phone (no real kiosk screen or camera needed)

You don't need a touchscreen, a TV, or even the real backend to try this
out. From the repo root:

```bash
cd kiosk
python -m http.server 8000
```

Then open **http://localhost:8000** in a browser on the same machine (or,
for your phone, find your laptop's local IP address — e.g. `ipconfig` /
`ifconfig` — and open `http://<that-ip>:8000` on the phone, as long as
both devices are on the same Wi-Fi). Your laptop's or phone's own camera
works fine for the camera screen — `getUserMedia` is allowed over plain
`http://` on `localhost` and local IPs for testing (a real deployment on
Cloudflare Pages gets `https://` automatically, which is required
everywhere else).

**Demo mode is already on** in the `kiosk/config.js` that ships in this
repo (it's gitignored, so this is a local working copy, not what gets
deployed). With `DEMO_MODE: true` in `config.js`, the kiosk never calls
the real backend: `/warmup` resolves instantly and `/tryon` just echoes
your own captured photo back as the "result" after a short simulated
delay, with a gold **DEMO MODE** badge in the corner so it's never
ambiguous. This lets you click through the entire flow — attract, consent,
camera, department/style/fabric, processing, result, compare, idle
timeout, staff menu — without a deployed backend and without spending any
GPU credit. Set `DEMO_MODE: false` once you're ready to test or use the
real backend.

Note that until you've approved at least one fabric with
`catalogue/review.py`, `kiosk/catalogue/catalogue.json` has an empty
`items` list, so the department screen will correctly show "No fabrics
have been published yet" — that's expected, not a bug. Approve something
in the catalogue tool to see real department/style/fabric choices.

## What to edit in config.js

```bash
cp kiosk/config.example.js kiosk/config.js
```

Then edit `kiosk/config.js`:

| Field | What it is |
|---|---|
| `API_URL` | The backend's `/warmup` + `/tryon` base URL (the "VTONModel.web" URL from `modal deploy` — see `backend/README.md`) |
| `KIOSK_TOKEN` | Must match the backend's `KIOSK_TOKEN` secret |
| `STORE_NAME` | Shown on the attract screen |
| `LOGO_PATH` | Path to your logo image (optional — falls back to text if missing) |
| `STAFF_PIN` | PIN for the hidden staff menu |
| `IDLE_SECONDS` | Seconds of no touch before "Are you still there?" appears |
| `DEMO_MODE` | `true` = never calls the real backend (see above). Set `false` for real use. |

**`config.js` is never committed to git** (see the root `.gitignore`) —
`config.example.js` is the template everyone starts from.

### A word about KIOSK_TOKEN not really being secret

`config.js` is loaded straight into the customer's browser, so its
contents — including `KIOSK_TOKEN` — are visible to anyone who opens
browser dev tools on the kiosk screen. That's fine: the real protection
against someone abusing your GPU with a copied token is on the backend
side — its 30-try-ons-per-10-minutes rate limit and its max-1-container
cap (see `backend/README.md`). Don't put anything more sensitive than
this token in `config.js`.

## The hidden staff menu

Tap the very top-left corner of the screen 5 times within 3 seconds (it's
an invisible ~70x70px zone, not something a customer would stumble into)
to bring up a PIN pad. Enter `STAFF_PIN` to reach:

- **Reload catalogue** — re-fetches `catalogue.json` without reloading the whole page
- **Test backend** — calls the backend to confirm it's reachable
- **Show last error** — the most recent error message, useful for diagnosing a stuck kiosk
- **Exit kiosk** — exits fullscreen if the browser is in it (a web page can't force-close the browser itself — close the window/tab, or Alt+F4, to fully exit Chrome kiosk mode)

## Deploying to Cloudflare Pages

This is a static site with no build step, so deployment is just "point
Cloudflare Pages at this folder": set the project's build output directory
to `kiosk/` (build command: none). Remember `kiosk/config.js` is
gitignored on purpose — you'll need to either add it directly in your
Cloudflare Pages deployment (upload alongside, or set it via their
dashboard file editor) or adjust your `.gitignore` if you'd rather commit
a real one for this specific deployment. Don't commit a `config.js` with
a real `KIOSK_TOKEN` to a public repo.

## Running on the actual kiosk screen (Chrome kiosk mode)

On the touchscreen/TV device, launch Chrome pointed at your deployed URL
with kiosk mode flags, e.g. (Windows):

```
chrome.exe --kiosk --incognito https://your-kiosk.pages.dev
```

`--incognito` keeps each browser session clean (no autofill/history
buildup over weeks of use) — consistent with never keeping customer data
around. If the screen is portrait-mounted, rotate it in your OS display
settings; the layout is built for a 1080x1920 portrait screen but also
works in landscape and on a phone.
