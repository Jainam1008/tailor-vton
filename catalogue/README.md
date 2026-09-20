# catalogue

Stage 1 (offline) — turns fabric swatch photos into catalogue garment images.

Run this whenever a new fabric arrives at the shop. It is **not** run live
while a customer is at the kiosk. Python scripts take a fabric swatch photo
plus a template garment image (e.g. a kurta, sherwani, bandhgala, Nehru
jacket, shirt, or suit flat-lay/mannequin shot) and use
[fal.ai](https://fal.ai) image-editing models to generate a photorealistic
image of that garment made from that fabric. A local review tool lets you
look at each generated image and approve or reject it before it's added to
the kiosk's catalogue.

`output_review/` holds generated images pending review and is not checked
into git (see root `.gitignore`).

## Setup / run instructions

_Not yet implemented — this README will be filled in with copy-pasteable
commands once the scripts exist._
