"""Stage 1 (offline): turn fabric swatch photos into catalogue garment images.

For every fabric photo in catalogue/fabrics/ and every style in
config.yaml whose fabric_prefixes match that fabric's code, this calls a
fal.ai image-editing model with the style's template photo + the fabric
swatch photo + the style's prompt, and saves a few variant images under
catalogue/output_review/<fabric_code>/<style_id>/ for a human to review
with review.py.

Run with: python catalogue/generate.py
See catalogue/README.md for the full setup + workflow.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fal_client
import requests
import yaml

CATALOGUE_DIR = Path(__file__).parent
REPO_ROOT = CATALOGUE_DIR.parent
CONFIG_PATH = CATALOGUE_DIR / "config.yaml"
FABRICS_DIR = CATALOGUE_DIR / "fabrics"
OUTPUT_DIR = CATALOGUE_DIR / "output_review"
ENV_PATH = CATALOGUE_DIR / ".env"

VARIANTS_PER_COMBO = 2  # how many different variants to generate per fabric x style
COST_CONFIRMATION_THRESHOLD_USD = 5.00
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def load_env(path: Path) -> Dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, '#' comments. No external deps."""
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_config(path: Path) -> dict:
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        sys.exit(1)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_fabric_photos(fabrics_dir: Path) -> List[Path]:
    if not fabrics_dir.exists():
        print(f"error: {fabrics_dir} not found - add fabric photos there first", file=sys.stderr)
        sys.exit(1)
    return sorted(p for p in fabrics_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)


def fabric_prefix(fabric_path: Path) -> str:
    """SU-01.jpeg -> 'SU'. Case-insensitive, so 'Su-03.jpeg' also works."""
    code = fabric_path.stem
    return code.split("-")[0].upper()


def matching_styles(fabric_path: Path, styles: List[dict]) -> List[dict]:
    prefix = fabric_prefix(fabric_path)
    return [s for s in styles if prefix in [p.upper() for p in s["fabric_prefixes"]]]


def missing_variant_indices(target_dir: Path, count: int) -> List[int]:
    """Which of variant_01..variant_NN don't exist yet under target_dir."""
    missing = []
    for i in range(1, count + 1):
        if not (target_dir / f"variant_{i:02d}.jpg").exists():
            missing.append(i)
    return missing


def upload_cached(path: Path, cache: Dict[Path, str]) -> str:
    """Upload a local file to fal's CDN once, reuse the URL for every later call."""
    if path not in cache:
        cache[path] = fal_client.upload_file(str(path))
    return cache[path]


def generate_one_image(endpoint: str, prompt: str, template_url: str, swatch_url: str) -> Optional[bytes]:
    """Call the fal.ai endpoint and return the raw image bytes, or None on failure."""
    try:
        result = fal_client.run(
            endpoint,
            arguments={
                "prompt": prompt,
                "image_urls": [template_url, swatch_url],
                "output_format": "jpeg",
            },
        )
    except Exception as exc:  # noqa: BLE001 - a batch job must not die on one bad call
        print(f"    error calling {endpoint}: {exc}", file=sys.stderr)
        return None

    images = result.get("images") or []
    if not images:
        print(f"    error: {endpoint} returned no images", file=sys.stderr)
        return None

    image_url = images[0]["url"]
    try:
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"    error downloading result image: {exc}", file=sys.stderr)
        return None
    return response.content


def plan_work(
    fabrics: List[Path], styles: List[dict], models: Dict[str, dict]
) -> Tuple[List[dict], float, List[str]]:
    """Work out every (fabric, style, variant) still to generate, and its estimated cost."""
    jobs: List[dict] = []
    warnings: List[str] = []
    warned_styles = set()  # avoid repeating the same "no template" warning per fabric
    total_cost = 0.0

    for fabric_path in fabrics:
        matches = matching_styles(fabric_path, styles)
        if not matches:
            warnings.append(
                f"no style matches fabric prefix '{fabric_prefix(fabric_path)}' "
                f"({fabric_path.name}) - check config.yaml's fabric_prefixes"
            )
            continue

        for style in matches:
            template_path = REPO_ROOT / style["template"]
            if not template_path.exists():
                if style["id"] not in warned_styles:
                    warnings.append(
                        f"skipping style '{style['id']}': template image not found at "
                        f"{style['template']} - add one to generate this style"
                    )
                    warned_styles.add(style["id"])
                continue

            model = models.get(style["department"])
            if model is None:
                if style["id"] not in warned_styles:
                    warnings.append(
                        f"skipping style '{style['id']}': no models.{style['department']} entry in config.yaml"
                    )
                    warned_styles.add(style["id"])
                continue

            target_dir = OUTPUT_DIR / fabric_path.stem / style["id"]
            for variant_index in missing_variant_indices(target_dir, VARIANTS_PER_COMBO):
                jobs.append(
                    {
                        "fabric_path": fabric_path,
                        "style": style,
                        "template_path": template_path,
                        "endpoint": model["endpoint"],
                        "cost": float(model["approx_cost_usd"]),
                        "target_dir": target_dir,
                        "variant_index": variant_index,
                    }
                )
                total_cost += float(model["approx_cost_usd"])

    return jobs, total_cost, warnings


def main() -> None:
    env = load_env(ENV_PATH)
    fal_key = env.get("FAL_KEY") or ""
    if not fal_key:
        print("error: FAL_KEY not set - copy catalogue/.env.example to catalogue/.env and fill it in", file=sys.stderr)
        sys.exit(1)
    os.environ["FAL_KEY"] = fal_key

    config = load_config(CONFIG_PATH)
    styles = config["styles"]
    models = config["models"]

    fabrics = find_fabric_photos(FABRICS_DIR)
    if not fabrics:
        print(f"No fabric photos found in {FABRICS_DIR} - add some and run again.")
        return

    jobs, total_cost, warnings = plan_work(fabrics, styles, models)

    for warning in warnings:
        print(f"warning: {warning}")

    if not jobs:
        print("Nothing to generate - every fabric x style combination already has its variants.")
        return

    print(f"\n{len(jobs)} image(s) to generate, estimated cost: ${total_cost:.2f}")
    if total_cost > COST_CONFIRMATION_THRESHOLD_USD:
        answer = input(f"This exceeds ${COST_CONFIRMATION_THRESHOLD_USD:.2f} - continue? [y/N] ").strip().lower()
        if answer != "y":
            print("Cancelled.")
            return

    upload_cache: Dict[Path, str] = {}
    running_cost = 0.0
    generated = 0
    failed = 0

    for job in jobs:
        fabric_path = job["fabric_path"]
        style = job["style"]
        target_dir = job["target_dir"]
        variant_path = target_dir / f"variant_{job['variant_index']:02d}.jpg"

        print(f"[{fabric_path.stem} / {style['id']}] generating {variant_path.name} ...")

        template_url = upload_cached(job["template_path"], upload_cache)
        swatch_url = upload_cached(fabric_path, upload_cache)

        image_bytes = generate_one_image(job["endpoint"], style["prompt"], template_url, swatch_url)
        if image_bytes is None:
            failed += 1
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        variant_path.write_bytes(image_bytes)

        running_cost += job["cost"]
        generated += 1
        print(f"    saved (running total: ${running_cost:.2f})")

    print(f"\nDone. Generated {generated} image(s), {failed} failed. Estimated spend: ${running_cost:.2f}")
    if generated:
        print("Run `python catalogue/review.py` to review and approve the results.")


if __name__ == "__main__":
    main()
