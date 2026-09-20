# Deploying the kiosk to Cloudflare Pages

`kiosk/` is a static site (plain HTML/CSS/JS, no build step), so deploying
it is just "put these files on Cloudflare Pages." This doc covers two ways
to do that, the security headers file that ships with the kiosk, and the
one backend change you must make right after your first deploy.

Both options are free on Cloudflare's standard Pages plan (500 builds/month
for Git integration, unlimited direct-upload deployments, both with
unlimited bandwidth and requests) — there's no cost here regardless of
which you pick.

## Before you deploy

Make sure `kiosk/config.js` exists and is filled in (see `kiosk/README.md`
— `cp kiosk/config.example.js kiosk/config.js`, then edit it) and that
`DEMO_MODE` is set to `false` once you're ready for real customers.

## The `_headers` file (already included)

`kiosk/_headers` is a Cloudflare Pages convention: a plain text file in
your published folder that adds HTTP response headers, no code required.
It's already set up in this repo with:

- **`Permissions-Policy: camera=(self), ...`** — allows camera access for
  this site only (needed for the camera screen), and explicitly denies
  microphone/geolocation, which the kiosk never uses.
- **`Content-Security-Policy`** — restricts the page to loading scripts,
  styles and connections only from itself, Google Fonts, and your Modal
  backend. This means if some other script somehow got injected into the
  page, the browser would refuse to let it phone home anywhere else.
- **`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`** —
  standard defensive headers (don't allow embedding in another site's
  iframe, don't let browsers guess content types, don't leak the full URL
  to third parties via the Referer header).

**One thing you must edit yourself:** the `Content-Security-Policy` line
hard-codes your backend's URL in `connect-src`, because a static headers
file can't read `config.js` at request time — it has to already know
which origins are allowed to talk to the page. It currently has:

```
https://jainam-7701--tailor-vton-backend-vtonmodel-web.modal.run
```

If you ever redeploy the backend to a different Modal workspace (a
different URL), update **both** `kiosk/config.js`'s `API_URL` **and** this
`connect-src` value in `kiosk/_headers`, then redeploy the kiosk. If you
forget, the kiosk will load fine but every `/warmup`/`/tryon` call will be
silently blocked by the browser with a CSP error in the console — if that
ever happens, that's the first thing to check.

Cloudflare picks up `_headers` automatically with either deployment method
below — no extra step needed.

---

## Option A — Connect the GitHub repo (auto-deploys on every push)

Best if you want "push to GitHub → live on the kiosk" with no manual
steps after the first setup.

**A note on `kiosk/config.js` and git:** it's gitignored by default (see
`kiosk/README.md`) because it holds your `KIOSK_TOKEN`. This project's own
docs already establish that token isn't a real secret — it's visible in
the page source to anyone at the kiosk regardless, and the actual abuse
protection is on the backend (rate limit + max-1-container). So for this
auto-deploy path, the simplest approach is to commit a real
`kiosk/config.js`:

```bash
git add -f kiosk/config.js
git commit -m "Add kiosk config for Cloudflare Pages deploy"
```

If you'd rather never have it in git at all, skip Option A and use Option
B (direct upload) instead — it uploads your local `config.js` without
ever needing it committed.

### Steps

1. Push this repository to GitHub if you haven't already.
2. Go to the [Cloudflare dashboard](https://dash.cloudflare.com) →
   **Workers & Pages**.
3. Click **Create application** → **Pages** → **Connect to Git**.
4. Sign in / authorize GitHub, then pick this repository.
5. On the setup screen, fill in:
   - **Project name**: whatever you want (this becomes
     `<project-name>.pages.dev`)
   - **Production branch**: `main` (or whichever branch you deploy from)
   - **Build command**: leave **blank** (no build step)
   - **Build output directory**: `kiosk`
6. Click **Save and Deploy**.

Cloudflare will publish the contents of `kiosk/` and give you a URL like
`https://your-project.pages.dev`. From now on, every push to your
production branch redeploys automatically.

---

## Option B — Direct upload with the Wrangler CLI

Best if you don't want `kiosk/config.js` in git at all, or you just want
to deploy once without setting up Git integration.

### One-time setup

```bash
npm install -g wrangler
wrangler login
```

`wrangler login` opens a browser window to authorize the CLI against your
Cloudflare account.

### Create the project (once)

```bash
npx wrangler pages project create tailor-vton-kiosk --production-branch main
```

(Pick any project name — this becomes `<project-name>.pages.dev`. It'll
ask for a production branch name even though you're not using Git
integration; `main` is fine.)

### Deploy

```bash
npx wrangler pages deploy kiosk --project-name=tailor-vton-kiosk
```

This uploads everything in the local `kiosk/` folder as-is — including
your local `config.js` (gitignored or not, it doesn't matter here;
Wrangler just reads what's on disk) and `_headers`.

### Redeploying after a change

Just run the same `wrangler pages deploy` command again — it publishes a
new version to the same URL.

---

## After your first deploy: update the backend's ALLOWED_ORIGIN

**Do this now, before customers use the kiosk.** The backend's CORS
policy only accepts requests from the origin you told it about when you
set up `vton-secrets` (see `backend/README.md`) — probably still a
placeholder. Point it at your real Cloudflare Pages URL:

```bash
modal secret create vton-secrets \
    KIOSK_TOKEN=your-existing-kiosk-token \
    ALLOWED_ORIGIN=https://your-project.pages.dev
```

(Use the exact URL from your deploy — no trailing slash. Re-running
`modal secret create` with the same secret name overwrites it; keep
`KIOSK_TOKEN` the same as what's already in `kiosk/config.js` unless
you're deliberately rotating it.)

Then redeploy the backend so it picks up the new secret value:

```bash
modal deploy backend/app.py
```

Until you do this, the kiosk page will load fine, but every `/warmup` and
`/tryon` call will fail with a CORS error in the browser console — the
backend will be rejecting requests from an origin it doesn't recognize.
