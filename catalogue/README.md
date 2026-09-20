# catalogue

Stage 1 (offline) — turns fabric swatch photos into catalogue garment images.

Run this whenever new fabric arrives at the shop. It is **not** run live
while a customer is at the kiosk — it's something you (or whoever manages
the catalogue) run at your own desk, ahead of time, once per fabric.

## How it works, in plain English

1. **You photograph fabric swatches.** One close-up photo per fabric,
   filed under `catalogue/fabrics/`.
2. **`generate.py` makes garment photos.** For every fabric photo, and
   every garment style that fabric applies to (a suiting fabric only makes
   suits/blazers, a shirting fabric only makes shirts, an ethnic fabric
   only makes kurtas/sherwanis/etc.), it asks an AI image-editing model
   (via [fal.ai](https://fal.ai)) to redraw that style's reference photo
   using your fabric's colour and pattern. It saves a couple of different
   attempts ("variants") for each fabric x style combination, so you have
   something to choose between.
3. **`review.py` shows you the results.** A small web page, running only
   on your own computer, shows each fabric's variants side by side. You
   pick the best one (or reject all of them if none look right).
4. **Approving publishes it to the kiosk.** The chosen image is resized
   and copied into `kiosk/catalogue/images/`, and
   `kiosk/catalogue/catalogue.json` is updated to describe it. Once you
   push/deploy the `kiosk/` folder (see `kiosk/README.md`), customers can
   see and try on that fabric in that style.

## One-time setup

**1. Install Python dependencies:**

```bash
pip install -r catalogue/requirements.txt
```

**2. Get a fal.ai API key** by signing up at [fal.ai](https://fal.ai) and
creating one at [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys).
fal.ai bills per image generated (a few cents each) — there's no monthly
fee, you only pay for what you generate.

**3. Set up `catalogue/.env`:**

```bash
cp catalogue/.env.example catalogue/.env
```

Edit `catalogue/.env` and paste in your `FAL_KEY`.

## The regular workflow

### Step 1 — add photos

- **Fabric photos** go in `catalogue/fabrics/`, one clear close-up photo
  per fabric, named `<CODE>-<number>.jpg` where `<CODE>` is `SU` for a
  suiting fabric, `SH` for a shirting fabric, or `ET` for an ethnic
  fabric — e.g. `SU-01.jpg`, `SH-04.jpg`, `ET-02.jpg`. The prefix decides
  which garment styles that fabric is offered in (a suiting fabric never
  gets turned into a shirt, etc.) — see `config.yaml` if you ever need to
  change that mapping.
- **Template photos** — one clean reference photo per garment style,
  front view, plain background, full garment visible — go in
  `catalogue/templates/`, named to match the style's `id` in
  `config.yaml` (e.g. `two_piece_suit.jpg`). `generate.py` skips any
  style whose template photo is missing and tells you so, so it's safe to
  add these gradually.

`config.yaml` already has nine styles set up (two-piece suit, three-piece
suit, blazer, formal shirt, mandarin-collar shirt, kurta, sherwani,
bandhgala, Nehru jacket) — you shouldn't need to touch it unless you're
adding a new style or changing a prompt.

### Step 2 — generate

```bash
python catalogue/generate.py
```

It figures out every fabric x style combination that doesn't have images
yet, prints how many images that is and an estimated total cost, and asks
you to confirm before spending more than $5. It's safe to run this
repeatedly — anything already generated is skipped, so adding one new
fabric and re-running only pays for that fabric's images.

Results land in `catalogue/output_review/<fabric code>/<style id>/` and
aren't published anywhere yet.

### Step 3 — review

```bash
python catalogue/review.py
```

This prints a `http://127.0.0.1:5050` address — open it in your browser.
For each fabric you'll see its variants for each matching style. Type in
a proper display name for the fabric (e.g. "Navy Blue Pinstripe Wool")
and click **Save name**, then click **Approve** under whichever variant
looks best, or **Reject all** if none do. You can change your mind later
by approving a different variant, or rejecting something you'd already
approved — the kiosk catalogue updates immediately either way.

Rejecting doesn't delete the generated variants, just unpublishes them —
so if you reject everything for a fabric x style and want fresh attempts,
delete that folder under `catalogue/output_review/` yourself and run
`generate.py` again.

### Step 4 — publish

Approved images are already copied into `kiosk/catalogue/images/` and
listed in `kiosk/catalogue/catalogue.json` the moment you click Approve —
there's no separate export step. To actually put them in front of
customers, commit and deploy the `kiosk/` folder as usual (see
`kiosk/README.md`).

## Cost control

- `generate.py` skips anything already generated, so re-runs are cheap.
- It asks for confirmation before spending more than $5 in one run.
- `config.yaml`'s `models:` section controls which fal.ai model (and
  therefore roughly how much) each department costs — suiting and
  shirting default to FLUX.2 [pro] edit, ethnic defaults to Nano Banana 2
  edit. Check [fal.ai's pricing pages](https://fal.ai/pricing) for the
  current real price per image and update `approx_cost_usd` there if it
  changes — the estimate is only as accurate as that number.

## Privacy

Fabric and garment photos aren't sensitive customer data (they're your
shop's own product photos), so unlike `backend/`, this tool does write
files to disk and to git-ignored local folders. Nothing about a specific
customer ever passes through `catalogue/`.
