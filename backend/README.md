# backend

Stage 2 (live) — the try-on engine the kiosk calls when a customer is
standing at the kiosk with their photo and a chosen fabric/garment.

This is a [Modal](https://modal.com) serverless GPU app running
[FASHN VTON v1.5](https://github.com/fashn-AI/fashn-vton-1.5) (Apache-2.0).
Given a customer photo and a catalogue garment image (produced offline by
`catalogue/`), it returns an image of the customer wearing that garment.

## Cost/config rules (do not change without good reason)

- GPU: **L4**
- Scale to zero when idle (no warm containers)
- Max **1** container

## Privacy rule

Customer photos are processed in memory only for the duration of a single
request and are never written to disk, logged, or stored anywhere.

## Setup / run instructions

_Not yet implemented — this README will be filled in with copy-pasteable
`modal` CLI commands once the app exists._
