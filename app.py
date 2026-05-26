import io
import re
import textwrap
import xml.etree.ElementTree as ET

import requests
from flask import Flask, Response, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WP_RSS_URL = "https://cms.mia937.com/feed/"
WP_API_BASE = "https://cms.mia937.com/wp-json/wp/v2"
LOGO_URL = "https://www.mia937.com/logos/logo_mia.svg"

# Brand colors for MIA (pink/magenta accent — feminine radio brand)
ACCENT_COLOR = (200, 50, 120)  # pinkish-magenta for bracket decorations
TITLE_BG = (255, 255, 255, 210)  # semi-transparent white
TITLE_TEXT_COLOR = (30, 30, 30)
OUTPUT_W, OUTPUT_H = 1080, 1350

# Cache logo in memory
_logo_img = None


def get_logo():
    """Download and cache the MIA logo as a PIL Image (PNG)."""
    global _logo_img
    if _logo_img is not None:
        return _logo_img
    try:
        import cairosvg
        svg_data = requests.get(LOGO_URL, timeout=10).content
        png_data = cairosvg.svg2png(bytestring=svg_data, output_width=280)
        _logo_img = Image.open(io.BytesIO(png_data)).convert("RGBA")
    except Exception as e:
        print(f"Logo load error: {e}")
        # Create a placeholder
        _logo_img = Image.new("RGBA", (280, 120), (0, 0, 0, 0))
    return _logo_img


# ---------------------------------------------------------------------------
# /  — Health check
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return jsonify({"servicio": "Mia 93.7 - Generador de Imágenes", "status": "ok"})


# ---------------------------------------------------------------------------
# /rss-proxy  — Enriched RSS feed with media:content tags
# ---------------------------------------------------------------------------
@app.route("/rss-proxy")
def rss_proxy():
    """Fetch MIA's WordPress RSS, enrich each item with media:content
    pointing to the full-resolution featured image."""
    try:
        resp = requests.get(WP_RSS_URL, timeout=15)
        resp.raise_for_status()
        rss_text = resp.text
    except Exception as e:
        return Response(f"Error fetching RSS: {e}", status=502, mimetype="text/plain")

    # Strategy: parse the RSS XML, for each <item> extract the largest image
    # from the <description> srcset, and inject a <media:content> element.
    MEDIA_NS = "http://search.yahoo.com/mrss/"
    ET.register_namespace("media", MEDIA_NS)
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
    ET.register_namespace("wfw", "http://wellformedweb.org/CommentAPI/")
    ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace("sy", "http://purl.org/rss/1.0/modules/syndication/")
    ET.register_namespace("slash", "http://purl.org/rss/1.0/modules/slash/")

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as e:
        return Response(f"XML parse error: {e}", status=502, mimetype="text/plain")

    channel = root.find("channel")
    if channel is None:
        return Response("No <channel> in RSS", status=502, mimetype="text/plain")

    for item in channel.findall("item"):
        # Check if media:content already exists
        existing = item.find(f"{{{MEDIA_NS}}}content")
        if existing is not None:
            continue

        # Extract best image URL from description HTML
        desc_el = item.find("description")
        if desc_el is None or desc_el.text is None:
            continue

        desc_html = desc_el.text
        best_url = _extract_best_image(desc_html)
        if best_url:
            media_el = ET.SubElement(item, f"{{{MEDIA_NS}}}content")
            media_el.set("url", best_url)
            media_el.set("type", _guess_mime(best_url))
            media_el.set("medium", "image")

    # Also update link references: map cms.mia937.com → www.mia937.com
    for item in channel.findall("item"):
        link_el = item.find("link")
        if link_el is not None and link_el.text:
            link_el.text = _rewrite_link(link_el.text)
        guid_el = item.find("guid")
        if guid_el is not None and guid_el.text:
            guid_el.text = _rewrite_link(guid_el.text)

    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return Response(xml_str, mimetype="application/rss+xml; charset=utf-8")


def _rewrite_link(url: str) -> str:
    """Keep CMS URLs as-is since the public site doesn't have article pages yet.
    When mia937.com adds article routing, change this."""
    # No rewrite for now — cms.mia937.com URLs are the working public links
    return url


def _extract_best_image(html: str) -> str | None:
    """Extract the highest-resolution image URL from description HTML.
    Looks at srcset first, then src attribute."""
    # Try srcset — pick the widest image
    srcset_matches = re.findall(r'(https?://[^\s"]+)\s+(\d+)w', html)
    if srcset_matches:
        # Sort by width descending, pick largest
        srcset_matches.sort(key=lambda x: int(x[1]), reverse=True)
        return srcset_matches[0][0]

    # Fallback: first src attribute (usually 300px thumbnail)
    src_match = re.search(r'src="(https?://[^\s"]+)"', html)
    if src_match:
        url = src_match.group(1)
        # Try to get full-res by stripping WP size suffix (-300x200, etc.)
        full_url = re.sub(r'-\d+x\d+(\.\w+)$', r'\1', url)
        return full_url

    return None


def _guess_mime(url: str) -> str:
    if url.lower().endswith(".png"):
        return "image/png"
    if url.lower().endswith(".gif"):
        return "image/gif"
    if url.lower().endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


# ---------------------------------------------------------------------------
# /generar-imagen  — Generate branded 1080x1350 news image
# ---------------------------------------------------------------------------
@app.route("/generar-imagen")
def generar_imagen():
    titulo = request.args.get("titulo", "")
    foto_url = request.args.get("foto_url", "")

    if not titulo or not foto_url:
        return Response("Faltan parámetros: titulo, foto_url", status=400)

    try:
        img = _generate_branded_image(titulo, foto_url)
    except Exception as e:
        return Response(f"Error generando imagen: {e}", status=500)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/jpeg",
        as_attachment=False,
        download_name="mia_noticia.jpg",
    )


def _generate_branded_image(titulo: str, foto_url: str) -> Image.Image:
    """Create a 1080x1350 branded image with:
    - Background photo (cover-fit)
    - Semi-transparent white title bar in lower third
    - Title text in dark color
    - MIA logo below title
    - Pink/magenta decorative corner brackets
    """
    # Download photo
    resp = requests.get(foto_url, timeout=15)
    resp.raise_for_status()
    photo = Image.open(io.BytesIO(resp.content)).convert("RGB")

    # Create canvas
    canvas = Image.new("RGB", (OUTPUT_W, OUTPUT_H), (0, 0, 0))

    # Cover-fit the photo
    photo_ratio = photo.width / photo.height
    target_ratio = OUTPUT_W / OUTPUT_H
    if photo_ratio > target_ratio:
        # Photo is wider — fit height, crop width
        new_h = OUTPUT_H
        new_w = int(new_h * photo_ratio)
    else:
        # Photo is taller — fit width, crop height
        new_w = OUTPUT_W
        new_h = int(new_w / photo_ratio)
    photo = photo.resize((new_w, new_h), Image.LANCZOS)
    # Center crop
    left = (new_w - OUTPUT_W) // 2
    top = (new_h - OUTPUT_H) // 2
    photo = photo.crop((left, top, left + OUTPUT_W, top + OUTPUT_H))
    canvas.paste(photo)

    # Create overlay layer for transparency effects
    overlay = Image.new("RGBA", (OUTPUT_W, OUTPUT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Title bar dimensions
    bar_margin = 60
    bar_top = OUTPUT_H - 480
    bar_bottom = OUTPUT_H - 200
    bar_left = bar_margin
    bar_right = OUTPUT_W - bar_margin

    # Draw semi-transparent white rectangle for title
    draw.rectangle(
        [bar_left, bar_top, bar_right, bar_bottom],
        fill=TITLE_BG,
    )

    # Load font (try system fonts)
    font_size = 42
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    # Wrap text to fit within the bar
    max_chars = 30
    wrapped = textwrap.fill(titulo, width=max_chars)
    lines = wrapped.split("\n")

    # Calculate text position (centered in bar)
    total_text_height = len(lines) * (font_size + 10)
    text_y = bar_top + (bar_bottom - bar_top - total_text_height) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        text_x = (OUTPUT_W - tw) // 2
        draw.text((text_x, text_y), line, fill=TITLE_TEXT_COLOR, font=font)
        text_y += font_size + 10

    # Draw decorative corner brackets (pink/magenta)
    bracket_len = 40
    bracket_w = 4
    bx1, by1 = bar_left - 10, bar_top - 10
    bx2, by2 = bar_right + 10, bar_bottom + 10

    # Top-left bracket
    draw.line([(bx1, by1), (bx1 + bracket_len, by1)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    draw.line([(bx1, by1), (bx1, by1 + bracket_len)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    # Top-right bracket
    draw.line([(bx2, by1), (bx2 - bracket_len, by1)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    draw.line([(bx2, by1), (bx2, by1 + bracket_len)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    # Bottom-left bracket
    draw.line([(bx1, by2), (bx1 + bracket_len, by2)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    draw.line([(bx1, by2), (bx1, by2 - bracket_len)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    # Bottom-right bracket
    draw.line([(bx2, by2), (bx2 - bracket_len, by2)], fill=ACCENT_COLOR + (255,), width=bracket_w)
    draw.line([(bx2, by2), (bx2, by2 - bracket_len)], fill=ACCENT_COLOR + (255,), width=bracket_w)

    # Composite overlay onto canvas
    canvas = canvas.convert("RGBA")
    canvas = Image.alpha_composite(canvas, overlay)

    # Paste logo below the title bar, centered
    logo = get_logo()
    logo_x = (OUTPUT_W - logo.width) // 2
    logo_y = bar_bottom + 20
    canvas.paste(logo, (logo_x, logo_y), logo)

    return canvas.convert("RGB")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
