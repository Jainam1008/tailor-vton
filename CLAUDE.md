# CLAUDE.md

Guidance for Claude Code (and any other AI assistant) working in this repository.

## What this project is

A virtual try-on (VTON) kiosk for a men's custom tailoring store in India. The
store sells suiting, shirting, and ethnic fabrics (kurta, sherwani, bandhgala,
Nehru jacket) and stitches garments to order. Customers stand in front of a
kiosk, pick a fabric, and see a photo of themselves wearing a garment made
from that fabric before they commit to an order.

## Two-stage design

The system is deliberately split into an **offline stage** and a **live
stage**, so that the expensive/slow work happens once per fabric (not once
per customer):

### Stage 1 — Catalogue generation (offline, run ahead of time)

`catalogue/` turns a photo of a fabric swatch plus a template garment (e.g. a
flat-lay or mannequin shot of a kurta, sherwani, bandhgala, Nehru jacket,
shirt, or suit) into a finished "catalogue garment image" — a photorealistic
image of that garment as if made from that fabric. This uses fal.ai
image-editing models and is run by the shop owner (or whoever manages the
fabric catalogue) ahead of time, whenever a new fabric arrives. A local
review tool lets a human approve or reject generated images before they go
live in the kiosk. Output images are the only per-fabric artifact the live
kiosk ever needs.

### Stage 2 — Live try-on (online, runs per customer at the kiosk)

`backend/` is a Modal serverless GPU app running FASHN VTON v1.5. At the
kiosk, a live customer photo is combined with a chosen catalogue garment
image (produced in Stage 1) to generate a try-on image of that customer
wearing that garment. This runs live, on demand, while the customer is
standing at the kiosk, and must be fast and cheap.

`kiosk/` is the plain HTML/CSS/JS front end the customer actually touches:
capture or upload a photo, pick a fabric/garment, call the Stage 2 backend,
show the result. It is a static site with no build step, hosted on
Cloudflare Pages.

## Priorities (in order)

1. **Minimum running cost.** This is a small shop, not a SaaS product. Every
   design choice should default to the cheapest option that works. Prefer
   pay-per-use, scale-to-zero infrastructure over anything with a standing
   monthly cost. Avoid always-on servers, databases, or queues unless there
   is a concrete reason one is needed.
2. **Customer privacy.** Customer photos are sensitive. They must **never be
   stored** — not on disk, not in a database, not in logs, not in cloud
   storage, not in error-tracking tools. Process customer photos in memory
   only, for the duration of a single request, and discard them immediately
   after. This applies to every stage of the pipeline the photo passes
   through (kiosk browser, backend, any intermediate service).
3. **Simplicity for a non-developer shop owner.** The person maintaining
   this day to day is not a software engineer. Prefer the smallest number of
   moving parts, plain-language documentation, and scripts/commands that can
   be copy-pasted rather than systems requiring ongoing engineering
   attention. Avoid clever abstractions in favor of code that is easy to
   read top-to-bottom.

## Cost controls (backend, Modal)

The Modal app in `backend/` MUST be configured so that:

- **GPU type is L4.** Do not upgrade to a larger/more expensive GPU without
  an explicit reason tied to a measured quality or latency problem.
- **Scales to zero when idle.** No warm/always-on containers. The kiosk is
  used intermittently through the day; paying for idle GPU time is against
  priority #1.
- **Max 1 container.** Concurrency is not a concern for a single kiosk
  terminal — do not configure autoscaling beyond a single container.

Any change to these settings should be treated as a deliberate cost/latency
trade-off, not a default to reach for.

## Conventions

- **Python 3.11** for `backend/` and `catalogue/`.
- **Type hints** on all function signatures.
- **Clear comments** where the *why* isn't obvious from the code (a
  workaround, a non-obvious constraint, a cost/privacy trade-off) — not
  comments that restate what the code does.
- **A README in each top-level folder** (`backend/`, `catalogue/`,
  `kiosk/`, `docs/`) written in plain English, aimed at the shop owner or
  whoever is setting things up, with copy-pasteable run instructions.
- No customer photo, and no derivative of one, is ever written to disk,
  logged, or persisted anywhere in this repo's code paths.

## Repository layout

```
backend/    Modal serverless GPU app — FASHN VTON v1.5 (Stage 2, live try-on)
catalogue/  fal.ai-based scripts to turn fabric swatches into catalogue
            garment images, plus a local review tool (Stage 1, offline)
kiosk/      Static HTML/CSS/JS kiosk front end, hosted on Cloudflare Pages
docs/       Setup notes
```
