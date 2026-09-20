# tailor-vton

Virtual try-on kiosk for a men's custom tailoring store in India — suiting,
shirting, and ethnic wear (kurta, sherwani, bandhgala, Nehru jacket).

Customers pick a fabric at the kiosk and see themselves wearing a garment
made from it, before placing a stitching order.

See [`CLAUDE.md`](./CLAUDE.md) for the full project design, priorities, and
conventions. Short version:

- **`catalogue/`** — offline scripts that turn a fabric swatch photo into a
  catalogue garment image (fal.ai). Run ahead of time, once per fabric.
- **`backend/`** — Modal serverless GPU app running FASHN VTON v1.5. Runs
  live, per customer, at the kiosk.
- **`kiosk/`** — plain HTML/CSS/JS kiosk web page, no build step, hosted on
  Cloudflare Pages.
- **`docs/`** — setup notes.

Each folder has its own README with plain-English run instructions.

## Priorities

1. Minimum running cost
2. Customer privacy — photos are never stored, processed in memory only
3. Simplicity to maintain for a non-developer shop owner

## Status

Project scaffolding only — no application code yet.
