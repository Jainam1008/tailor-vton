"""Command-line tool to test the deployed tailor-vton backend.

Calls POST /warmup then POST /tryon against your already-deployed Modal
backend, saves the result image, and prints timing plus an estimated
per-try-on cost. Uses only the Python standard library - no `pip install`
needed beyond Python 3.11 itself.

Usage:
    python backend/test_tryon.py --person person.jpg --garment shirt.jpg --category tops

    # Two-piece suit: trousers applied first, then the jacket on top.
    python backend/test_tryon.py --person person.jpg \\
        --passes trousers.jpg bottoms jacket.jpg tops

Reads TRYON_BASE_URL and KIOSK_TOKEN from backend/.env - copy
backend/.env.example to backend/.env and fill it in first.
"""

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Tuple

# Modal's published per-second price for whatever GPU backend/app.py's
# VTONModel currently uses (A10 as of 2026-09-20, see CLAUDE.md), from
# https://modal.com/pricing. Edit this if Modal changes their pricing, or
# if app.py's `gpu=` argument ever changes - there's no API to read either
# live.
GPU_PRICE_PER_SECOND = 0.000306  # A10

VALID_CATEGORIES = ("tops", "bottoms", "one-pieces")

DEFAULT_ENV_PATH = Path(__file__).parent / ".env"


def load_env(path: Path) -> dict:
    """Minimal .env parser: KEY=VALUE lines, '#' comments. No external deps."""
    if not path.exists():
        print(f"error: {path} not found - copy backend/.env.example to backend/.env and fill it in", file=sys.stderr)
        sys.exit(1)
    env: dict = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def encode_image(path: Path) -> str:
    if not path.exists():
        print(f"error: image not found: {path}", file=sys.stderr)
        sys.exit(1)
    return base64.b64encode(path.read_bytes()).decode("ascii")


def post_json(url: str, token: str, payload: dict) -> Tuple[dict, float]:
    """POST JSON to `url`, return (parsed response body, wall-clock seconds)."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Kiosk-Token": token},
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"error: {url} returned HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"error: could not reach {url}: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    elapsed = time.monotonic() - start
    return body, elapsed


def parse_passes(values: List[str]) -> List[Tuple[Path, str]]:
    """Parse a flat --passes list of [IMAGE, CATEGORY, IMAGE, CATEGORY, ...] pairs."""
    if len(values) % 2 != 0 or len(values) < 2:
        print(
            "error: --passes needs pairs of IMAGE CATEGORY (an even number of "
            "arguments, at least one pair)",
            file=sys.stderr,
        )
        sys.exit(1)
    passes = []
    for i in range(0, len(values), 2):
        image_path, category = Path(values[i]), values[i + 1]
        if category not in VALID_CATEGORIES:
            print(f"error: invalid category '{category}' - must be one of {VALID_CATEGORIES}", file=sys.stderr)
            sys.exit(1)
        passes.append((image_path, category))
    return passes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test the deployed tailor-vton backend end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Single garment:
    python backend/test_tryon.py --person person.jpg --garment shirt.jpg --category tops

  Two-piece suit (bottoms applied first, then tops):
    python backend/test_tryon.py --person person.jpg \\
        --passes trousers.jpg bottoms jacket.jpg tops
""",
    )
    parser.add_argument("--person", required=True, type=Path, help="Path to the person photo")
    parser.add_argument("--garment", type=Path, help="Path to a single garment photo")
    parser.add_argument("--category", choices=VALID_CATEGORIES, help="Category for --garment")
    parser.add_argument(
        "--passes",
        nargs="+",
        metavar="IMAGE_OR_CATEGORY",
        help="Two or more garments applied in sequence, as pairs: "
        "IMAGE1 CATEGORY1 IMAGE2 CATEGORY2 ... (e.g. for a two-piece suit: "
        "trousers.jpg bottoms jacket.jpg tops)",
    )
    parser.add_argument("--output", type=Path, default=Path("test_output.jpg"), help="Where to save the result image")
    parser.add_argument(
        "--env-file", type=Path, default=DEFAULT_ENV_PATH, help="Path to the .env file (default: backend/.env)"
    )
    args = parser.parse_args()

    if bool(args.garment) == bool(args.passes):
        parser.error("provide exactly one of --garment/--category or --passes")
    if args.garment and not args.category:
        parser.error("--garment requires --category")

    env = load_env(args.env_file)
    base_url = env.get("TRYON_BASE_URL", "").rstrip("/")
    token = env.get("KIOSK_TOKEN", "")
    if not base_url or not token:
        print(f"error: {args.env_file} must set TRYON_BASE_URL and KIOSK_TOKEN", file=sys.stderr)
        sys.exit(1)

    print(f"Warming up {base_url} ...")
    _, warmup_time = post_json(f"{base_url}/warmup", token, {})

    person_b64 = encode_image(args.person)
    if args.passes:
        pass_list = parse_passes(args.passes)
        payload = {
            "person_image": person_b64,
            "passes": [
                {"garment_image": encode_image(image_path), "category": category}
                for image_path, category in pass_list
            ],
        }
        print(f"Running {len(pass_list)}-pass try-on ...")
    else:
        payload = {
            "person_image": person_b64,
            "garment_image": encode_image(args.garment),
            "category": args.category,
        }
        print("Running try-on ...")

    result, wall_clock_time = post_json(f"{base_url}/tryon", token, payload)

    inference_time = result["processing_time_seconds"]
    estimated_cost = inference_time * GPU_PRICE_PER_SECOND

    args.output.write_bytes(base64.b64decode(result["result_image"]))

    print()
    print(f"Cold-start (warmup) time: {warmup_time:.2f}s (a warm container would respond in under ~1s)")
    print(f"Inference time (server-reported): {inference_time:.2f}s")
    print(f"Total /tryon request time (incl. network): {wall_clock_time:.2f}s")
    print(
        f"Estimated cost for this try-on: ${estimated_cost:.6f} "
        f"(inference time x ${GPU_PRICE_PER_SECOND}/s GPU rate - excludes cold-start "
        f"and idle time before scale-down, which are shared across all try-ons in a session)"
    )
    print(f"Result saved to: {args.output}")


if __name__ == "__main__":
    main()
