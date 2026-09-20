# backend

Stage 2 (live) — the try-on engine the kiosk calls when a customer is
standing at the kiosk with their photo and a chosen fabric/garment.

This is a [Modal](https://modal.com) serverless GPU app running
[FASHN VTON v1.5](https://github.com/fashn-AI/fashn-vton-1.5) (Apache-2.0).
Given a customer photo and a catalogue garment image (produced offline by
`catalogue/`), it returns an image of the customer wearing that garment.

It exposes three HTTP endpoints:

- `GET  /health` — is the backend up? No login needed, no GPU spun up.
- `POST /warmup` — call this the instant a customer taps "Start" on the
  kiosk, so the GPU container is already awake by the time they upload a
  photo, instead of making them wait through a cold start.
- `POST /tryon` — the real try-on: a person photo plus one garment image
  (or a `passes` list of several, applied in sequence — e.g. bottoms then
  tops for a two-piece suit) in, a result image out.

## A licensing note — please read before deploying

FASHN VTON v1.5 itself is Apache-2.0 (free to use commercially). But its
official install also pulls in a second package, `fashn-human-parser`,
whose weights are a fine-tuned NVIDIA model licensed **non-commercial use
only**. We do **not** install that package here at all. Instead, `app.py`
registers a small placeholder in its place and always calls the pipeline in
its "maskless"/flat-lay mode — the one configuration where FASHN's own code
proves the real parser's output is never actually used. The full reasoning
is written out in the big comment block at the top of `app.py`. If you ever
touch `_install_human_parser_stub()`, or the `segmentation_free` /
`garment_photo_type` arguments in `VTONModel._run_single_pass()`, read that
comment first.

## Cost controls (do not change without good reason)

- GPU: **A10** — benchmarked against L4 on 2026-09-20 with real try-on
  requests and came out ~31% faster *and* ~5% cheaper per try-on (it costs
  more per second, but finishes proportionally faster). See `CLAUDE.md` for
  the numbers. Re-benchmark before changing this either direction.
- Scales to zero 120 seconds after the last request — nothing runs, nothing
  costs money, when no customer is at the kiosk
- Max **1** container — fine for a single kiosk terminal, and keeps costs
  predictable

## Privacy

Customer photos are decoded and processed in memory only, for the duration
of a single request, and are never written to disk, to the Modal Volume, or
to the logs. Only timings and errors are logged.

## One-time setup

You'll need Python 3.11+ on the machine you're deploying from (your laptop
is fine — you don't run the actual app locally, this just talks to Modal).

**1. Install the Modal CLI:**

```bash
pip install modal
```

**2. Log in** (opens a browser window and links this machine to your Modal
account — create a free account first at [modal.com](https://modal.com) if
you don't have one):

```bash
modal setup
```

**3. Create the secret** that holds the kiosk's auth token and the allowed
website origin. Make up your own long random string for `KIOSK_TOKEN` —
this is the "password" the kiosk page sends on every request so strangers
can't use your GPU. `ALLOWED_ORIGIN` is the exact URL your kiosk page will
be hosted at (e.g. your Cloudflare Pages URL — you can update this later
once you know it):

```bash
modal secret create vton-secrets \
    KIOSK_TOKEN=replace-with-a-long-random-string \
    ALLOWED_ORIGIN=https://your-kiosk.pages.dev
```

Running this command again with new values overwrites the old secret.

**4. Download the model weights** into a Modal Volume (persistent storage).
This only needs to be done once ever — it downloads about 2GB and every
future deploy reuses it:

```bash
modal run backend/app.py
```

## Deploy

```bash
modal deploy backend/app.py
```

## Finding your endpoint URLs

The `deploy` command prints them when it finishes — look for lines like:

```
✓ Created web function health => https://<workspace>--tailor-vton-backend-health.modal.run
✓ Created web function VTONModel.web => https://<workspace>--tailor-vton-backend-vtonmodel-web.modal.run
```

- The **health URL** is your `GET /health` endpoint, ready to use as-is.
- The **VTONModel.web URL** is the base for `/warmup` and `/tryon` — the
  full addresses are that URL plus `/warmup` and plus `/tryon`
  (e.g. `https://<workspace>--tailor-vton-backend-vtonmodel-web.modal.run/tryon`).

If you lose track of them later, run `modal app list`, or check the "Apps"
page at [modal.com/apps](https://modal.com/apps) after logging in. Put both
URLs into the kiosk's configuration once `kiosk/` is built.

## Updating after a code change

```bash
modal deploy backend/app.py
```

This rebuilds only what changed and redeploys in place — same URLs, no
need to reconfigure the kiosk.

## Quick check it's working

```bash
curl https://<your-health-url>
# {"status":"ok"}
```

`/warmup` and `/tryon` both require the `X-Kiosk-Token` header set to the
`KIOSK_TOKEN` value you chose above, e.g.:

```bash
curl -X POST https://<your-vtonmodel-web-url>/warmup \
    -H "X-Kiosk-Token: replace-with-a-long-random-string"
# {"status":"ready"}
```

## Testing a real try-on from the command line

`test_tryon.py` runs a full try-on against your deployed backend, saves the
result image, and prints timing plus an estimated cost — useful for
checking image quality and roughly how much each try-on costs before
customers start using the kiosk.

**1. Set up `backend/.env`** (one-time, holds your URL + token so you don't
retype them every time — already excluded from git):

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and fill in `TRYON_BASE_URL` (the **VTONModel.web**
URL from the deploy step above) and `KIOSK_TOKEN` (the value you chose when
creating the secret).

**2. Run it** with a person photo and a garment photo:

```bash
python backend/test_tryon.py --person person.jpg --garment shirt.jpg --category tops
```

Or test a two-piece suit (each garment applied in sequence, e.g. trousers
first, then the jacket on top):

```bash
python backend/test_tryon.py --person person.jpg \
    --passes trousers.jpg bottoms jacket.jpg tops
```

Either way it prints something like:

```
Cold-start (warmup) time: 16.73s (a warm container would respond in under ~1s)
Inference time (server-reported): 19.25s
Total /tryon request time (incl. network): 21.77s
Estimated cost for this try-on: $0.005891 (inference time x $0.000306/s GPU rate - ...)
Result saved to: test_output.jpg
```

The cost estimate uses a price constant at the top of `test_tryon.py`
(`GPU_PRICE_PER_SECOND`) copied from
[modal.com/pricing](https://modal.com/pricing) for whichever GPU
`backend/app.py` is currently deployed on (A10, as of 2026-09-20) — if
Modal changes their pricing, or the `gpu=` argument in `app.py` ever
changes, update that constant too (there's no API to read either live). It
only covers the GPU-seconds spent on inference itself, not the one-off cold
start or the idle time before the container scales down — real cost per
try-on will be lower than this when the kiosk is busy (cold start gets
shared across many try-ons) and closer to this number when try-ons are
spaced out.
