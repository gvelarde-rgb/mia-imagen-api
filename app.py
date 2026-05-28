import hashlib
import io
import re
import struct
import textwrap
import time
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

# Browser-like headers to bypass Siteground captcha/bot-detection
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "es-GT,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Brand colors for MIA (purple accent — matches MIA's brand purple)
ACCENT_COLOR = (148, 50, 120)  # purple matching MIA's brand
TITLE_BG = (255, 255, 255, 210)  # semi-transparent white
TITLE_TEXT_COLOR = (30, 30, 30)
OUTPUT_W, OUTPUT_H = 1080, 1350

# ---------------------------------------------------------------------------
# SiteGround Captcha Solver — solves JS proof-of-work challenge
# ---------------------------------------------------------------------------
_sg_session = None  # Reusable session with solved captcha cookie


def _solve_sg_challenge(challenge_str: str) -> str | None:
    """Solve SiteGround's SHA-1 proof-of-work challenge.

    Challenge format: 'difficulty:timestamp:salt:hash:'
    Must find a counter N such that SHA1(challenge_bytes + counter_bytes)
    has `difficulty` leading zero bits.

    The JS worker encodes the counter as variable-length big-endian bytes
    (1-4 bytes depending on magnitude), appends to the UTF-8 challenge
    string, and hashes with SHA-1. The byte-swap helper in the JS worker
    merely converts platform-LE Int32Array back to big-endian for CryptoJS,
    so the net effect is standard SHA-1 on the raw byte sequence.
    """
    import base64

    difficulty = int(challenge_str.split(":", 1)[0])
    challenge_bytes = challenge_str.encode("utf-8")
    shift = 32 - difficulty

    counter = 0
    max_attempts = 10_000_000

    while counter < max_attempts:
        # Variable-length big-endian encoding — matches JS worker exactly
        if counter == 0:
            counter_bytes = b'\x00'
        else:
            if counter > 16777215:
                byte_count = 4
            elif counter > 65535:
                byte_count = 3
            elif counter > 255:
                byte_count = 2
            else:
                byte_count = 1
            counter_bytes = counter.to_bytes(byte_count, 'big')

        combined = challenge_bytes + counter_bytes
        h = hashlib.sha1(combined).digest()

        # Check leading `difficulty` zero bits via first 4-byte word (big-endian)
        first_word = struct.unpack('>I', h[:4])[0]
        if (first_word >> shift) == 0:
            return base64.b64encode(combined).decode('ascii')

        counter += 1

    return None


def _get_sg_session() -> requests.Session:
    """Get a requests.Session that has solved the SiteGround captcha.
    Reuses the session if cookies are still valid."""
    global _sg_session
    
    if _sg_session is not None:
        # Test if session is still valid
        try:
            r = _sg_session.get(
                f"{WP_API_BASE}/posts?per_page=1&_fields=id",
                timeout=10
            )
            if r.status_code == 200 and 'sgcaptcha' not in r.text:
                return _sg_session
        except Exception:
            pass
    
    # Create new session and solve captcha
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    
    # First request — may trigger captcha
    r = session.get(f"{WP_API_BASE}/posts?per_page=1&_fields=id", timeout=15)
    
    if r.status_code == 200 and 'sgcaptcha' not in r.text:
        # No captcha needed
        _sg_session = session
        return session
    
    # Extract captcha redirect URL
    match = re.search(r'content="0;([^"]+)"', r.text)
    if not match:
        print("SG Captcha: Could not find redirect URL")
        _sg_session = session
        return session
    
    captcha_path = match.group(1)
    captcha_url = f"https://cms.mia937.com{captcha_path}"
    
    # Fetch the challenge page
    r2 = session.get(captcha_url, timeout=15)
    
    # Extract challenge string
    challenge_match = re.search(r'const sgchallenge="([^"]+)"', r2.text)
    submit_match = re.search(r'const sgsubmit_url="([^"]+)"', r2.text)
    
    if not challenge_match or not submit_match:
        print("SG Captcha: Could not extract challenge")
        _sg_session = session
        return session
    
    challenge = challenge_match.group(1)
    submit_url = submit_match.group(1)
    
    print(f"SG Captcha: Solving challenge (difficulty={challenge.split(':')[0]})...")
    start_time = time.time()
    
    solution = _solve_sg_challenge(challenge)
    elapsed = time.time() - start_time
    
    if not solution:
        print(f"SG Captcha: Failed to solve after {elapsed:.1f}s")
        _sg_session = session
        return session
    
    print(f"SG Captcha: Solved in {elapsed:.1f}s")
    
    # Submit solution
    from urllib.parse import quote
    sep = "&" if "?" in submit_url else "?"
    solve_url = f"https://cms.mia937.com{submit_url}{sep}sol={quote(solution)}&s={int(elapsed*1000)}:1"
    
    r3 = session.get(solve_url, timeout=15, allow_redirects=True)
    print(f"SG Captcha: Submit response {r3.status_code}, cookies: {dict(session.cookies)}")
    
    _sg_session = session
    return session


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


@app.route("/debug-fetch")
def debug_fetch():
    """Temporary debug endpoint to check what the server sees when fetching CMS."""
    url = request.args.get("url", f"{WP_API_BASE}/posts?per_page=1")
    try:
        session = _get_sg_session()
        resp = session.get(url, timeout=20)
        return jsonify({
            "status_code": resp.status_code,
            "content_type": resp.headers.get("content-type", ""),
            "body_preview": resp.text[:500],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ---------------------------------------------------------------------------
# /rss-proxy  — Enriched RSS feed with media:content tags
# ---------------------------------------------------------------------------
@app.route("/rss-proxy")
def rss_proxy():
    """Build an RSS feed from the WP REST API (bypasses Siteground captcha
    that blocks direct /feed/ access from cloud server IPs).
    Each item includes a <media:content> tag with the featured image."""
    import html as html_mod
    from datetime import datetime, timezone

    try:
        # Fetch recent posts with embedded featured media
        # Uses session with solved SiteGround captcha
        session = _get_sg_session()
        api_url = f"{WP_API_BASE}/posts?per_page=10&_embed"
        resp = session.get(api_url, timeout=20)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        posts = resp.json()
    except Exception as e:
        return Response(f"Error fetching WP API: {e}", status=502, mimetype="text/plain")

    # Build RSS XML manually
    now_rfc822 = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items_xml = []
    for post in posts:
        title = html_mod.unescape(post.get("title", {}).get("rendered", ""))
        link = post.get("link", "")
        excerpt = post.get("excerpt", {}).get("rendered", "")
        # Clean excerpt to plain text for description
        excerpt_text = re.sub(r"<[^>]+>", "", html_mod.unescape(excerpt)).strip()
        pub_date = ""
        if post.get("date_gmt"):
            try:
                dt = datetime.strptime(post["date_gmt"], "%Y-%m-%dT%H:%M:%S")
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except ValueError:
                pub_date = now_rfc822

        # Get featured image URL from _embedded
        img_url = ""
        try:
            media_list = post.get("_embedded", {}).get("wp:featuredmedia", [])
            if media_list:
                img_url = media_list[0].get("source_url", "")
        except (IndexError, KeyError, TypeError):
            pass

        # Escape XML special chars in title and excerpt
        title_escaped = (
            title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        excerpt_escaped = (
            excerpt_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

        media_tag = ""
        if img_url:
            mime = _guess_mime(img_url)
            media_tag = f'<media:content url="{img_url}" type="{mime}" medium="image" />'

        items_xml.append(f"""    <item>
      <title>{title_escaped}</title>
      <link>{link}</link>
      <guid isPermaLink="true">{link}</guid>
      <pubDate>{pub_date}</pubDate>
      <description>{excerpt_escaped}</description>
      {media_tag}
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Mia 937</title>
    <link>https://cms.mia937.com</link>
    <description>Noticias de Mia 93.7</description>
    <lastBuildDate>{now_rfc822}</lastBuildDate>
{chr(10).join(items_xml)}
  </channel>
</rss>"""

    return Response(rss, mimetype="application/rss+xml; charset=utf-8")


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
    # Download photo (use SG session for cms.mia937.com images, else plain request)
    if "cms.mia937.com" in foto_url:
        session = _get_sg_session()
        resp = session.get(foto_url, timeout=15)
    else:
        resp = requests.get(foto_url, headers=BROWSER_HEADERS, timeout=15)
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
