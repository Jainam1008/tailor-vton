"""Stage 1 review tool: approve or reject generated catalogue images.

Starts a small local web page showing each fabric x style with its
generated variants next to the original swatch photo. Approving a variant
optimises it and publishes it (plus a swatch thumbnail) into
kiosk/catalogue/images/, and records it in kiosk/catalogue/catalogue.json
for the kiosk to read. Rejecting removes any previously published/approved
image for that fabric x style.

Multi-piece styles (tryon_plan is a list in config.yaml, e.g. a two-piece
suit's [bottoms, tops] - see config.yaml's comment on `pieces` for why)
need one variant CHOSEN per piece before the style counts as complete for
a fabric - the page shows each piece as its own row of variants, tracks
your in-progress choices locally, and only publishes to catalogue.json
once every piece has a choice.

Run with: python catalogue/review.py
Then open the printed http://127.0.0.1:5050 URL in your browser.
"""

import json
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from flask import Flask, abort, redirect, request, send_from_directory, url_for
from PIL import Image

CATALOGUE_DIR = Path(__file__).parent
REPO_ROOT = CATALOGUE_DIR.parent
CONFIG_PATH = CATALOGUE_DIR / "config.yaml"
FABRICS_DIR = CATALOGUE_DIR / "fabrics"
OUTPUT_DIR = CATALOGUE_DIR / "output_review"
FABRIC_NAMES_PATH = OUTPUT_DIR / "_fabric_names.json"
PIECE_CHOICES_PATH = OUTPUT_DIR / "_piece_choices.json"

KIOSK_CATALOGUE_DIR = REPO_ROOT / "kiosk" / "catalogue"
KIOSK_IMAGES_DIR = KIOSK_CATALOGUE_DIR / "images"
KIOSK_SWATCHES_DIR = KIOSK_IMAGES_DIR / "swatches"
CATALOGUE_JSON_PATH = KIOSK_CATALOGUE_DIR / "catalogue.json"

MAX_GARMENT_IMAGE_HEIGHT = 1200
SWATCH_THUMBNAIL_MAX_DIMENSION = 300
JPEG_QUALITY = 85

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

with CONFIG_PATH.open("r", encoding="utf-8") as _f:
    _config = yaml.safe_load(_f)
STYLES_BY_ID: Dict[str, dict] = {s["id"]: s for s in _config["styles"]}

app = Flask(__name__)


# --- small local JSON stores ------------------------------------------------


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_fabric_names() -> Dict[str, str]:
    return load_json(FABRIC_NAMES_PATH, {})


def save_fabric_name(fabric_code: str, name: str) -> None:
    names = load_fabric_names()
    names[fabric_code] = name
    save_json(FABRIC_NAMES_PATH, names)


def load_catalogue() -> dict:
    return load_json(CATALOGUE_JSON_PATH, {"items": []})


def save_catalogue(data: dict) -> None:
    save_json(CATALOGUE_JSON_PATH, data)


def load_piece_choices() -> dict:
    """{fabric_code: {style_id: {piece_name: variant_filename}}} - which
    variant you've picked so far for each piece of a multi-piece style,
    kept even before every piece has a choice (so partial progress across
    browser visits isn't lost)."""
    return load_json(PIECE_CHOICES_PATH, {})


def get_piece_choices(fabric_code: str, style_id: str) -> Dict[str, str]:
    return load_piece_choices().get(fabric_code, {}).get(style_id, {})


def save_piece_choice(fabric_code: str, style_id: str, piece_name: str, variant_filename: str) -> None:
    choices = load_piece_choices()
    choices.setdefault(fabric_code, {}).setdefault(style_id, {})[piece_name] = variant_filename
    save_json(PIECE_CHOICES_PATH, choices)


def clear_piece_choice(fabric_code: str, style_id: str, piece_name: str) -> None:
    choices = load_piece_choices()
    if fabric_code in choices and style_id in choices[fabric_code]:
        choices[fabric_code][style_id].pop(piece_name, None)
        save_json(PIECE_CHOICES_PATH, choices)


# --- image helpers -----------------------------------------------------------


def find_fabric_photo(fabric_code: str) -> Optional[Path]:
    if not FABRICS_DIR.exists():
        return None
    for path in FABRICS_DIR.iterdir():
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.upper() == fabric_code.upper():
            return path
    return None


def resize_and_save_jpeg(
    src_path: Path, dest_path: Path, *, max_height: Optional[int] = None, max_dimension: Optional[int] = None
) -> None:
    with Image.open(src_path) as img:
        img = img.convert("RGB")
        width, height = img.size
        if max_height and height > max_height:
            scale = max_height / height
            img = img.resize((max(1, round(width * scale)), max_height), Image.LANCZOS)
        elif max_dimension and max(width, height) > max_dimension:
            scale = max_dimension / max(width, height)
            img = img.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)


# --- scanning generated variants ---------------------------------------------


def scan_review_items() -> List[dict]:
    if not OUTPUT_DIR.exists():
        return []

    fabric_names = load_fabric_names()
    approved_ids = {item["id"] for item in load_catalogue()["items"]}

    fabrics = []
    for fabric_dir in sorted(p for p in OUTPUT_DIR.iterdir() if p.is_dir()):
        fabric_code = fabric_dir.name
        styles_for_fabric = []
        for style_dir in sorted(p for p in fabric_dir.iterdir() if p.is_dir()):
            style = STYLES_BY_ID.get(style_dir.name)
            if style is None:
                continue

            if "pieces" in style:
                piece_choices = get_piece_choices(fabric_code, style["id"])
                pieces_data = []
                for piece_name in style["pieces"].keys():
                    piece_dir = style_dir / piece_name
                    if not piece_dir.is_dir():
                        continue
                    variants = sorted(p.name for p in piece_dir.iterdir() if p.suffix.lower() == ".jpg")
                    if not variants:
                        continue
                    pieces_data.append(
                        {
                            "piece_name": piece_name,
                            "variants": variants,
                            "chosen_variant": piece_choices.get(piece_name),
                        }
                    )
                if not pieces_data:
                    continue
                styles_for_fabric.append(
                    {
                        "style": style,
                        "is_multi_piece": True,
                        "pieces": pieces_data,
                        "approved": f"{fabric_code}__{style['id']}" in approved_ids,
                    }
                )
            else:
                variants = sorted(p.name for p in style_dir.iterdir() if p.suffix.lower() == ".jpg")
                if not variants:
                    continue
                styles_for_fabric.append(
                    {
                        "style": style,
                        "is_multi_piece": False,
                        "variants": variants,
                        "approved": f"{fabric_code}__{style['id']}" in approved_ids,
                    }
                )

        if styles_for_fabric:
            fabrics.append(
                {
                    "fabric_code": fabric_code,
                    "fabric_name": fabric_names.get(fabric_code, fabric_code),
                    "has_swatch_photo": find_fabric_photo(fabric_code) is not None,
                    "styles": styles_for_fabric,
                }
            )
    return fabrics


# --- approve / reject actions (single-template styles) -----------------------


def approve(fabric_code: str, style_id: str, variant_filename: str, fabric_name: str) -> None:
    style = STYLES_BY_ID.get(style_id)
    if style is None:
        return
    variant_path = OUTPUT_DIR / fabric_code / style_id / variant_filename
    if not variant_path.exists():
        return

    item_id = f"{fabric_code}__{style_id}"

    image_dest = KIOSK_IMAGES_DIR / f"{item_id}.jpg"
    resize_and_save_jpeg(variant_path, image_dest, max_height=MAX_GARMENT_IMAGE_HEIGHT)

    swatch_dest = KIOSK_SWATCHES_DIR / f"{fabric_code}.jpg"
    fabric_photo = find_fabric_photo(fabric_code)
    if fabric_photo is not None:
        resize_and_save_jpeg(fabric_photo, swatch_dest, max_dimension=SWATCH_THUMBNAIL_MAX_DIMENSION)

    catalogue = load_catalogue()
    catalogue["items"] = [item for item in catalogue["items"] if item["id"] != item_id]
    catalogue["items"].append(
        {
            "id": item_id,
            "fabric_code": fabric_code,
            "fabric_name": fabric_name,
            "department": style["department"],
            "style_id": style_id,
            "style_name": style["name"],
            "image": f"catalogue/images/{item_id}.jpg",
            "swatch": f"catalogue/images/swatches/{fabric_code}.jpg",
            "tryon_plan": style["tryon_plan"],
        }
    )
    save_catalogue(catalogue)


def reject(fabric_code: str, style_id: str) -> None:
    item_id = f"{fabric_code}__{style_id}"

    catalogue = load_catalogue()
    remaining = [item for item in catalogue["items"] if item["id"] != item_id]
    if len(remaining) != len(catalogue["items"]):
        catalogue["items"] = remaining
        save_catalogue(catalogue)

    published_image = KIOSK_IMAGES_DIR / f"{item_id}.jpg"
    if published_image.exists():
        published_image.unlink()


# --- choose / clear actions (multi-piece styles) ------------------------------


def choose_piece(fabric_code: str, style_id: str, piece_name: str, variant_filename: str, fabric_name: str) -> None:
    style = STYLES_BY_ID.get(style_id)
    if style is None or "pieces" not in style:
        return
    variant_path = OUTPUT_DIR / fabric_code / style_id / piece_name / variant_filename
    if not variant_path.exists():
        return

    save_piece_choice(fabric_code, style_id, piece_name, variant_filename)
    _publish_if_complete(fabric_code, style_id, fabric_name)


def reject_piece(fabric_code: str, style_id: str, piece_name: str) -> None:
    clear_piece_choice(fabric_code, style_id, piece_name)

    # This style was previously fully published but is now missing a piece -
    # unpublish it rather than leave a stale/incomplete entry live.
    style = STYLES_BY_ID.get(style_id) or {}
    item_id = f"{fabric_code}__{style_id}"
    catalogue = load_catalogue()
    remaining = [item for item in catalogue["items"] if item["id"] != item_id]
    if len(remaining) != len(catalogue["items"]):
        catalogue["items"] = remaining
        save_catalogue(catalogue)
    for pname in style.get("pieces", {}).keys():
        published = KIOSK_IMAGES_DIR / f"{item_id}__{pname}.jpg"
        if published.exists():
            published.unlink()


def _publish_if_complete(fabric_code: str, style_id: str, fabric_name: str) -> None:
    """If every piece of this style now has a chosen variant, publish all of
    them and write/update the catalogue.json entry. Does nothing (silently)
    if choices are still incomplete - that's the normal in-progress state."""
    style = STYLES_BY_ID.get(style_id)
    if style is None or "pieces" not in style:
        return

    piece_names = list(style["pieces"].keys())
    choices = get_piece_choices(fabric_code, style_id)
    if not all(name in choices for name in piece_names):
        return

    item_id = f"{fabric_code}__{style_id}"
    images = {}
    for piece_name in piece_names:
        variant_filename = choices[piece_name]
        variant_path = OUTPUT_DIR / fabric_code / style_id / piece_name / variant_filename
        if not variant_path.exists():
            return  # a chosen file went missing somehow - don't publish a broken entry
        image_dest = KIOSK_IMAGES_DIR / f"{item_id}__{piece_name}.jpg"
        resize_and_save_jpeg(variant_path, image_dest, max_height=MAX_GARMENT_IMAGE_HEIGHT)
        images[piece_name] = f"catalogue/images/{item_id}__{piece_name}.jpg"

    swatch_dest = KIOSK_SWATCHES_DIR / f"{fabric_code}.jpg"
    fabric_photo = find_fabric_photo(fabric_code)
    if fabric_photo is not None:
        resize_and_save_jpeg(fabric_photo, swatch_dest, max_dimension=SWATCH_THUMBNAIL_MAX_DIMENSION)

    catalogue = load_catalogue()
    catalogue["items"] = [item for item in catalogue["items"] if item["id"] != item_id]
    catalogue["items"].append(
        {
            "id": item_id,
            "fabric_code": fabric_code,
            "fabric_name": fabric_name,
            "department": style["department"],
            "style_id": style_id,
            "style_name": style["name"],
            "images": images,
            "swatch": f"catalogue/images/swatches/{fabric_code}.jpg",
            "tryon_plan": style["tryon_plan"],
        }
    )
    save_catalogue(catalogue)


# --- HTML rendering ------------------------------------------------------------

PAGE_STYLE = """
body { font-family: system-ui, sans-serif; background: #f4f4f4; margin: 0; padding: 24px; }
h1 { margin-top: 0; }
.fabric-card { background: #fff; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;
               box-shadow: 0 1px 3px rgba(0,0,0,0.15); }
.fabric-header { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.fabric-header input[type=text] { font-size: 1.1em; padding: 6px 8px; border: 1px solid #ccc; border-radius: 4px; }
.fabric-code { color: #888; font-size: 0.9em; }
.style-row { border-top: 1px solid #eee; padding: 14px 0; }
.style-row h3 { margin: 0 0 8px 0; display: flex; align-items: center; gap: 10px; }
.piece-section { margin: 10px 0 10px 12px; padding-left: 12px; border-left: 3px solid #eee; }
.piece-section h4 { margin: 0 0 6px 0; font-size: 0.95em; color: #555; }
.badge { font-size: 0.75em; padding: 2px 8px; border-radius: 10px; background: #e0e0e0; color: #444; }
.badge.approved { background: #d4edda; color: #1e6b30; }
.badge.in-progress { background: #fff3cd; color: #8a6500; }
.variants { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-start; }
.variant { text-align: center; }
.variant img { width: 160px; height: auto; border-radius: 4px; border: 1px solid #ddd; display: block; }
.variant.chosen img { border: 3px solid #2e7d32; }
.variant button { margin-top: 6px; }
button { cursor: pointer; padding: 6px 12px; border-radius: 4px; border: 1px solid #ccc; background: #fafafa; }
button.approve { background: #2e7d32; color: #fff; border-color: #2e7d32; }
button.reject { background: #c62828; color: #fff; border-color: #c62828; margin-left: 12px; }
.empty { color: #666; }
"""


def render_page(fabrics: List[dict]) -> str:
    if not fabrics:
        body = '<p class="empty">Nothing to review yet. Run <code>python catalogue/generate.py</code> first.</p>'
    else:
        body = "".join(render_fabric_card(f) for f in fabrics)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Catalogue Review</title>
<style>{PAGE_STYLE}</style>
</head>
<body>
<h1>Catalogue Review</h1>
{body}
</body>
</html>"""


def render_fabric_card(fabric: dict) -> str:
    fabric_code = fabric["fabric_code"]
    swatch_img = (
        f'<img src="/media/fabrics/{escape(fabric_code)}" alt="swatch" style="width:80px;border-radius:4px;">'
        if fabric["has_swatch_photo"]
        else ""
    )
    # find_fabric_photo() resolves the real filename; the /media route below
    # looks it up the same way so this works regardless of extension.
    rows = "".join(render_style_row(fabric_code, s) for s in fabric["styles"])
    return f"""<div class="fabric-card">
  <div class="fabric-header">
    {swatch_img}
    <div>
      <div class="fabric-code">{escape(fabric_code)}</div>
      <form method="post" action="/rename" style="display:inline">
        <input type="hidden" name="fabric_code" value="{escape(fabric_code)}">
        <input type="text" name="fabric_name" value="{escape(fabric["fabric_name"])}">
        <button type="submit">Save name</button>
      </form>
    </div>
  </div>
  {rows}
</div>"""


def render_style_row(fabric_code: str, entry: dict) -> str:
    style = entry["style"]
    if entry["is_multi_piece"]:
        chosen_count = sum(1 for p in entry["pieces"] if p["chosen_variant"])
        total = len(entry["pieces"])
        if entry["approved"]:
            badge = '<span class="badge approved">Approved</span>'
        elif chosen_count:
            badge = f'<span class="badge in-progress">{chosen_count}/{total} pieces chosen</span>'
        else:
            badge = '<span class="badge">Pending</span>'
        pieces_html = "".join(render_piece_section(fabric_code, style["id"], p) for p in entry["pieces"])
        return f"""<div class="style-row">
    <h3>{escape(style["name"])} {badge}</h3>
    {pieces_html}
  </div>"""

    badge = '<span class="badge approved">Approved</span>' if entry["approved"] else '<span class="badge">Pending</span>'
    variants_html = "".join(render_variant(fabric_code, style["id"], filename) for filename in entry["variants"])
    return f"""<div class="style-row">
    <h3>{escape(style["name"])} {badge}</h3>
    <div class="variants">
      {variants_html}
      <form method="post" action="/action" style="align-self:center;">
        <input type="hidden" name="action" value="reject:{escape(fabric_code)}:{escape(style["id"])}">
        <button type="submit" class="reject">Reject all</button>
      </form>
    </div>
  </div>"""


def render_piece_section(fabric_code: str, style_id: str, piece: dict) -> str:
    piece_name = piece["piece_name"]
    chosen = piece["chosen_variant"]
    variants_html = "".join(
        render_piece_variant(fabric_code, style_id, piece_name, filename, filename == chosen)
        for filename in piece["variants"]
    )
    reject_action = f"reject_piece:{fabric_code}:{style_id}:{piece_name}"
    chosen_label = f" - chosen: {escape(chosen)}" if chosen else ""
    return f"""<div class="piece-section">
      <h4>{escape(piece_name.capitalize())}{chosen_label}</h4>
      <div class="variants">
        {variants_html}
        <form method="post" action="/action" style="align-self:center;">
          <input type="hidden" name="action" value="{escape(reject_action)}">
          <button type="submit" class="reject">Clear choice</button>
        </form>
      </div>
    </div>"""


def render_piece_variant(fabric_code: str, style_id: str, piece_name: str, filename: str, is_chosen: bool) -> str:
    img_url = f"/media/output_review/{fabric_code}/{style_id}/{piece_name}/{filename}"
    action_value = f"choose_piece:{fabric_code}:{style_id}:{piece_name}:{filename}"
    css_class = "variant chosen" if is_chosen else "variant"
    label = "Chosen" if is_chosen else "Choose this one"
    return f"""<div class="{css_class}">
        <img src="{escape(img_url)}" alt="{escape(filename)}">
        <form method="post" action="/action">
          <input type="hidden" name="action" value="{escape(action_value)}">
          <button type="submit" class="approve">{label}</button>
        </form>
      </div>"""


def render_variant(fabric_code: str, style_id: str, filename: str) -> str:
    img_url = f"/media/output_review/{fabric_code}/{style_id}/{filename}"
    action_value = f"approve:{fabric_code}:{style_id}:{filename}"
    return f"""<div class="variant">
        <img src="{escape(img_url)}" alt="{escape(filename)}">
        <form method="post" action="/action">
          <input type="hidden" name="action" value="{escape(action_value)}">
          <button type="submit" class="approve">Approve</button>
        </form>
      </div>"""


# --- routes --------------------------------------------------------------------


@app.route("/")
def index():
    return render_page(scan_review_items())


@app.route("/media/fabrics/<fabric_code>")
def media_fabric(fabric_code: str):
    photo = find_fabric_photo(fabric_code)
    if photo is None:
        abort(404)
    return send_from_directory(photo.parent, photo.name)


@app.route("/media/output_review/<path:relpath>")
def media_output_review(relpath: str):
    return send_from_directory(OUTPUT_DIR, relpath)


@app.route("/rename", methods=["POST"])
def rename():
    fabric_code = request.form.get("fabric_code", "")
    fabric_name = request.form.get("fabric_name", "").strip()
    if fabric_code and fabric_name:
        save_fabric_name(fabric_code, fabric_name)
    return redirect(url_for("index"))


@app.route("/action", methods=["POST"])
def action():
    raw = request.form.get("action", "")
    parts = raw.split(":")
    if len(parts) < 3:
        abort(400)
    verb, fabric_code, style_id = parts[0], parts[1], parts[2]

    fabric_name = load_fabric_names().get(fabric_code, fabric_code)

    if verb == "approve" and len(parts) == 4:
        approve(fabric_code, style_id, parts[3], fabric_name)
    elif verb == "reject" and len(parts) == 3:
        reject(fabric_code, style_id)
    elif verb == "choose_piece" and len(parts) == 5:
        choose_piece(fabric_code, style_id, parts[3], parts[4], fabric_name)
    elif verb == "reject_piece" and len(parts) == 4:
        reject_piece(fabric_code, style_id, parts[3])
    else:
        abort(400)

    return redirect(url_for("index"))


if __name__ == "__main__":
    print("Catalogue review server starting at http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
