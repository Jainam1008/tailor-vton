"""tailor-vton backend - Modal app running FASHN VTON v1.5 for live customer try-on.

Two Modal images are used:
  - health_image: tiny, no ML dependencies. Backs GET /health so a liveness
    check never spins up a GPU container.
  - vton_image: heavy, GPU inference dependencies. Backs the VTONModel class
    (POST /warmup, POST /tryon).

------------------------------------------------------------------------------
LICENSING NOTE - read this before changing anything below that touches
_install_human_parser_stub(), segmentation_free, or garment_photo_type.
------------------------------------------------------------------------------
fashn-vton-1.5 (Apache-2.0) hard-depends on a second PyPI package,
`fashn-human-parser`. That package's own LICENSE file states plainly that
its weights are a fine-tuned NVIDIA SegFormer checkpoint under the "NVIDIA
Source Code License for SegFormer", which restricts use to non-commercial
research/evaluation only (Section 3.3). We are a commercial kiosk, so we
are not permitted to run those weights.

This is not avoidable by using FASHN's "maskless" (segmentation_free=True)
mode: `fashn_vton.pipeline.TryOnPipeline.__init__` unconditionally
constructs `FashnHumanParser()`, and that constructor unconditionally
downloads and loads the real weights the moment it runs - before
segmentation_free is ever checked. `TryOnPipeline.__call__` then
unconditionally calls `.predict()` on both the person and garment image,
also before segmentation_free is checked.

What IS true: when a pipeline call uses segmentation_free=True AND
garment_photo_type="flat-lay" (both of which we always use - see
VTONModel._run_single_pass below), fashn-vton's own preprocessing code
(create_clothing_agnostic_image / create_garment_image) returns the image
unchanged before ever touching the parser's output. In that exact
configuration the human parser's result is provably dead code - computed
and thrown away. So never running it at all produces identical output to
running it, while completely avoiding the non-commercial dependency.

The fix used here:
  1. vton_image installs fashn-vton-1.5 with `--no-deps`, then installs
     every one of its OTHER dependencies by hand. The real
     `fashn-human-parser` package (and its own dependency, `transformers`)
     is never installed, never downloaded, never present in this image.
  2. _install_human_parser_stub() registers a tiny stand-in module under
     sys.modules["fashn_human_parser"] before fashn_vton is ever imported,
     so fashn_vton's `from fashn_human_parser import ...` statements
     resolve to our stub instead of failing outright. The stub re-declares
     only the plain label-name tables fashn_vton's code expects at import
     time (not model code, not weights, nothing derived from SegFormer),
     plus a FashnHumanParser class whose constructor is a no-op and whose
     .predict() returns a dummy all-zero mask instead of running any real
     model. .predict() genuinely IS called on every single request (that's
     expected, not a bug) - it's the dummy mask being read for anything
     real that must never happen.

Do not add a call path that uses segmentation_free=False or
garment_photo_type="model" without re-reading this note first. Either
change would make fashn_vton's own code start reading the stub's dummy
all-zero mask as if it were real segmentation, and silently produce wrong
(not obviously broken) try-on output instead of raising anything.
------------------------------------------------------------------------------
"""

import logging
import time

import modal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vton-backend")

app = modal.App("tailor-vton-backend")

# Persistent storage for model weights, so they only download once.
weights_volume = modal.Volume.from_name("vton-weights", create_if_missing=True)

# --- Images -------------------------------------------------------------

# Lightweight image for the health check endpoint only. No torch, no GPU
# libs, so cold starts are near-instant and it costs nothing to hit often.
health_image = modal.Image.debian_slim(python_version="3.11").pip_install("fastapi[standard]")

# Heavy image for the try-on model. See the LICENSING NOTE above for why
# fashn-vton-1.5 is installed with --no-deps and fashn-human-parser is
# deliberately absent from this list.
vton_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1", "libglib2.0-0")
    .pip_install(
        "fastapi[standard]",
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "safetensors>=0.3.0",
        "huggingface_hub>=0.20.0",
        "pillow>=9.0.0",
        "numpy>=1.21.0",
        "opencv-python>=4.5.0",
        "tqdm>=4.65.0",
        "einops>=0.6.0",
        "onnxruntime-gpu>=1.14.0",
        "matplotlib>=3.5.0",
    )
    .pip_install(
        "git+https://github.com/fashn-AI/fashn-vton-1.5.git",
        extra_options="--no-deps",
    )
)

# --- Human parser stub (see LICENSING NOTE) ------------------------------


def _install_human_parser_stub() -> None:
    """Register a stand-in `fashn_human_parser` module before fashn_vton is imported.

    Must run before the first `import fashn_vton` in this process. See the
    LICENSING NOTE at the top of this file for the full reasoning.
    """
    import sys
    import types

    if "fashn_human_parser" in sys.modules:
        return

    stub = types.ModuleType("fashn_human_parser")

    ids_to_labels = {
        0: "background", 1: "face", 2: "hair", 3: "top", 4: "dress", 5: "skirt",
        6: "pants", 7: "belt", 8: "bag", 9: "hat", 10: "scarf", 11: "glasses",
        12: "arms", 13: "hands", 14: "legs", 15: "feet", 16: "torso", 17: "jewelry",
    }
    stub.IDS_TO_LABELS = ids_to_labels
    stub.LABELS_TO_IDS = {v: k for k, v in ids_to_labels.items()}
    stub.CATEGORY_TO_BODY_COVERAGE = {"tops": "upper", "bottoms": "lower", "one-pieces": "full"}
    stub.BODY_COVERAGE_TO_LABELS = {
        "upper": ["top", "dress", "scarf"],
        "lower": ["skirt", "pants", "belt"],
        "full": ["top", "dress", "scarf", "skirt", "pants", "belt"],
    }
    stub.IDENTITY_LABELS = ["face", "hair", "jewelry", "bag", "glasses", "hat"]

    class FashnHumanParser:
        """Stub. Never downloads or runs the real, non-commercially-licensed model.

        fashn_vton.pipeline.TryOnPipeline.__call__ unconditionally calls
        .predict() on both the person and garment image, on every single
        request, regardless of segmentation_free - so this WILL be called
        every time, that is expected. It returns a dummy all-zero mask
        instead. That is only safe because every pipeline call in this app
        also fixes garment_photo_type="flat-lay", and together
        segmentation_free=True + garment_photo_type="flat-lay" is the one
        configuration where fashn_vton's own preprocessing
        (create_clothing_agnostic_image / create_garment_image) returns the
        image unchanged BEFORE ever reading this dummy output - see the
        LICENSING NOTE at the top of this file. If either of those two
        arguments ever changes, this dummy data would start being read for
        real masking decisions and silently produce wrong output - do not
        change them without re-reading that note.
        """

        def __init__(self, *args, **kwargs) -> None:
            pass

        def predict(self, image, *args, **kwargs):
            import numpy as np

            height, width = image.shape[0], image.shape[1]
            return np.zeros((height, width), dtype=np.uint8)

    stub.FashnHumanParser = FashnHumanParser
    sys.modules["fashn_human_parser"] = stub


# --- One-off weight download ---------------------------------------------


@app.function(image=vton_image, volumes={"/weights": weights_volume}, timeout=1800)
def download_weights() -> None:
    """One-off: download FASHN VTON v1.5 + DWPose weights into the persistent Volume.

    Deliberately mirrors only two of the three steps in fashn-vton-1.5's own
    scripts/download_weights.py - the try-on model and DWPose. It skips that
    script's third step (FashnHumanParser weights) entirely; see the
    LICENSING NOTE at the top of this file for why.
    """
    import os

    from huggingface_hub import hf_hub_download

    weights_dir = "/weights"
    os.makedirs(weights_dir, exist_ok=True)

    print("Downloading TryOnModel weights...")
    hf_hub_download(repo_id="fashn-ai/fashn-vton-1.5", filename="model.safetensors", local_dir=weights_dir)

    dwpose_dir = os.path.join(weights_dir, "dwpose")
    os.makedirs(dwpose_dir, exist_ok=True)
    for filename in ["yolox_l.onnx", "dw-ll_ucoco_384.onnx"]:
        print(f"Downloading DWPose/{filename}...")
        hf_hub_download(repo_id="fashn-ai/DWPose", filename=filename, local_dir=dwpose_dir)

    weights_volume.commit()
    print("Done. Weights saved to the 'vton-weights' Modal Volume.")


@app.local_entrypoint()
def main() -> None:
    """Run with: modal run backend/app.py"""
    download_weights.remote()


# --- Rate limiting ---------------------------------------------------------


class RateLimiter:
    """Simple in-memory sliding-window rate limiter.

    Fine as in-memory-only state because max_containers=1 - there is only
    ever one container, so there's nothing to keep in sync across.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []

    def allow(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) >= self.max_requests:
            return False
        self._timestamps.append(now)
        return True


TRYON_RATE_LIMIT_MAX = 30
TRYON_RATE_LIMIT_WINDOW_SECONDS = 600.0  # 10 minutes
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_DIMENSION = 2048  # px, longest side - larger inputs are downscaled
MAX_PASSES = 4


# --- The GPU model + web app -----------------------------------------------


@app.cls(
    image=vton_image,
    gpu="A10",  # ~31% faster than L4 and ~5% cheaper per try-on - benchmarked 2026-09-20, see CLAUDE.md
    scaledown_window=120,  # scale to zero 120s after the last request
    max_containers=1,  # single kiosk terminal - no need for more
    timeout=300,
    volumes={"/weights": weights_volume},
    secrets=[modal.Secret.from_name("vton-secrets")],
)
class VTONModel:
    @modal.enter()
    def load(self) -> None:
        """Runs once per container, before any request is served."""
        _install_human_parser_stub()
        from fashn_vton import TryOnPipeline

        t0 = time.monotonic()
        self.pipeline = TryOnPipeline(weights_dir="/weights")
        self.rate_limiter = RateLimiter(TRYON_RATE_LIMIT_MAX, TRYON_RATE_LIMIT_WINDOW_SECONDS)
        logger.info("model loaded in %.1fs", time.monotonic() - t0)

    def _run_single_pass(self, person_image, garment_image, category: str):
        """Run one try-on pass. See the LICENSING NOTE for why these two
        arguments (segmentation_free, garment_photo_type) must stay fixed."""
        result = self.pipeline(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            garment_photo_type="flat-lay",
            segmentation_free=True,
        )
        return result.images[0]

    @modal.asgi_app()
    def web(self):
        import base64
        import binascii
        import hmac
        import io
        import os
        from typing import List, Literal, Optional

        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from PIL import Image, UnidentifiedImageError
        from pydantic import BaseModel

        class TryOnPass(BaseModel):
            garment_image: str  # base64 JPEG
            category: Literal["tops", "bottoms", "one-pieces"]

        class TryOnRequest(BaseModel):
            person_image: str  # base64 JPEG
            garment_image: Optional[str] = None
            category: Optional[Literal["tops", "bottoms", "one-pieces"]] = None
            # Optional multi-garment sequence, e.g. bottoms then tops for a
            # two-piece suit. Each pass's output feeds into the next pass as
            # the new "person" image. Mutually exclusive with
            # garment_image/category above.
            passes: Optional[List[TryOnPass]] = None

        class TryOnResponse(BaseModel):
            result_image: str  # base64 JPEG
            processing_time_seconds: float

        def require_kiosk_token(x_kiosk_token: str = Header(default="", alias="X-Kiosk-Token")) -> None:
            expected = os.environ.get("KIOSK_TOKEN", "")
            if not expected or not hmac.compare_digest(x_kiosk_token, expected):
                raise HTTPException(status_code=401, detail="invalid or missing X-Kiosk-Token")

        def decode_image(b64_data: str, field_name: str) -> "Image.Image":
            """Decode + validate a base64 image. Never touches disk - stays in memory."""
            try:
                raw = base64.b64decode(b64_data, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(400, f"{field_name} is not valid base64") from exc
            if len(raw) > MAX_IMAGE_BYTES:
                raise HTTPException(400, f"{field_name} exceeds the 5 MB limit")
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()  # force full decode now, catches truncated/non-image data
            except (UnidentifiedImageError, OSError) as exc:
                raise HTTPException(400, f"{field_name} is not a valid image") from exc
            img = img.convert("RGB")
            width, height = img.size
            longest = max(width, height)
            if longest > MAX_IMAGE_DIMENSION:
                scale = MAX_IMAGE_DIMENSION / longest
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                img = img.resize(new_size, Image.LANCZOS)
            return img

        def encode_image_base64(img: "Image.Image") -> str:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            return base64.b64encode(buf.getvalue()).decode("ascii")

        allowed_origin = os.environ.get("ALLOWED_ORIGIN", "")

        web_app = FastAPI(title="tailor-vton backend")
        web_app.add_middleware(
            CORSMiddleware,
            allow_origins=[allowed_origin] if allowed_origin else [],
            # Allow any localhost/127.0.0.1 port during development.
            allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Kiosk-Token"],
        )

        @web_app.post("/warmup")
        async def warmup(_: None = Depends(require_kiosk_token)) -> dict:
            # By the time this handler runs at all, @modal.enter() has
            # already finished loading the model - Modal won't route a
            # request to a container until its enter() hook completes. So
            # this endpoint's real job is letting the KIOSK trigger that
            # container startup (and absorb the cold-start latency) the
            # moment a customer taps Start, instead of during their first
            # real /tryon call.
            return {"status": "ready"}

        @web_app.post("/tryon", response_model=TryOnResponse)
        async def tryon(payload: TryOnRequest, _: None = Depends(require_kiosk_token)) -> TryOnResponse:
            if not self.rate_limiter.allow():
                raise HTTPException(429, "Too many try-on requests - please wait a few minutes")

            passes = payload.passes
            if passes:
                if payload.garment_image or payload.category:
                    raise HTTPException(400, "Provide either garment_image+category or passes, not both")
                if len(passes) > MAX_PASSES:
                    raise HTTPException(400, f"Too many passes (max {MAX_PASSES})")
            else:
                if not payload.garment_image or not payload.category:
                    raise HTTPException(400, "garment_image and category are required when passes is not given")
                passes = [TryOnPass(garment_image=payload.garment_image, category=payload.category)]

            start = time.monotonic()
            try:
                current = decode_image(payload.person_image, "person_image")
                for i, one_pass in enumerate(passes):
                    garment_img = decode_image(one_pass.garment_image, f"passes[{i}].garment_image")
                    current = self._run_single_pass(current, garment_img, one_pass.category)
            except HTTPException:
                raise
            except Exception:
                # Never log the exception's arguments if they could contain
                # image data - just the type/traceback location.
                logger.exception("tryon inference failed")
                raise HTTPException(500, "try-on failed")
            elapsed = time.monotonic() - start

            logger.info("tryon ok passes=%d elapsed=%.2fs", len(passes), elapsed)
            return TryOnResponse(result_image=encode_image_base64(current), processing_time_seconds=round(elapsed, 2))

        return web_app


# --- Health check (separate, no GPU) ---------------------------------------


@app.function(image=health_image)
@modal.fastapi_endpoint(method="GET")
def health() -> dict:
    return {"status": "ok"}
