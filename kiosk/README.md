# kiosk

The web page customers actually use at the kiosk terminal.

Plain HTML/CSS/JavaScript — no framework, no build step. Lets a customer
take or upload a photo, pick a fabric/garment from the catalogue (produced
offline by `catalogue/`), calls the live try-on backend (`backend/`), and
shows the result. Hosted on [Cloudflare Pages](https://pages.cloudflare.com).

The customer's photo is only ever held in the browser and sent directly to
the backend for processing — it is never uploaded to Cloudflare Pages or
stored anywhere.

## Setup / run instructions

_Not yet implemented — this README will be filled in with plain steps to
preview locally and deploy to Cloudflare Pages once the page exists._
