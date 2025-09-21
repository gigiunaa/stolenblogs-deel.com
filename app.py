# -*- coding: utf-8 -*-
import os, re, json, logging, requests
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ------------------------------
# Helpers
# ------------------------------
def extract_images(container):
    image_urls = set()

    for img in container.find_all("img"):
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
            or img.get("data-background")
        )
        if not src and img.get("srcset"):
            src = img["srcset"].split(",")[0].split()[0]
        if src:
            if src.startswith("//"):
                src = "https:" + src
            if src.startswith(("http://", "https://")):
                image_urls.add(src)

    for source in container.find_all("source"):
        srcset = source.get("srcset")
        if srcset:
            first = srcset.split(",")[0].split()[0]
            if first.startswith("//"):
                first = "https:" + first
            if first.startswith(("http://", "https://")):
                image_urls.add(first)

    for tag in container.find_all(style=True):
        style = tag["style"]
        for match in re.findall(r"url\((.*?)\)", style):
            url = match.strip("\"' ")
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith(("http://", "https://")):
                image_urls.add(url)

    return list(image_urls)

def clean_article(article):
    for tag in article(["script", "style", "svg", "noscript"]):
        tag.decompose()

    for tag in article.find_all(True):
        if tag.name not in ["p","h1","h2","h3","ul","ol","li","img","strong","em","b","i","a"]:
            tag.unwrap()
            continue

        if tag.name == "img":
            src = (
                tag.get("src")
                or tag.get("data-src")
                or tag.get("data-lazy-src")
                or tag.get("data-original")
                or tag.get("data-background")
            )
            if not src and tag.get("srcset"):
                src = tag["srcset"].split(",")[0].split()[0]
            if src and src.startswith("//"):
                src = "https:" + src
            alt = (tag.get("alt") or "Image").strip()
            tag.attrs = {"src": src or "", "alt": alt}
        else:
            tag.attrs = {}
    return article

def extract_blog_content(html: str):
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article")
    if not article:
        for cls in ["blog-content","post-content","entry-content","content","article-body"]:
            article = soup.find("div", class_=cls)
            if article:
                break
    if not article and soup.body:
        article = soup.body
    return clean_article(article) if article else None

# ------------------------------
# Routes
# ------------------------------
@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "ok": True,
        "service": "stolenblogs scraper",
        "endpoints": {
            "POST /scrape-blog": {"body": {"url": "https://example.com/blog-post"}},
            "POST /html-to-image": {
                "requires_env": ["HCTI_USER_ID", "HCTI_API_KEY"],
                "body": {"html": "<div>...</div>", "css": "/* optional */", "width": 800}
            }
        }
    })

@app.route("/scrape-blog", methods=["POST"])
def scrape_blog():
    try:
        data = request.get_json(force=True)
        url = (data or {}).get("url")
        if not url:
            return Response("Missing 'url' field", status=400)

        resp = requests.get(url, timeout=25, headers={"User-Agent": UA})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        h1 = soup.find("h1")
        if h1 and not title:
            title = h1.get_text(strip=True)

        # Content
        article = extract_blog_content(resp.text)
        if not article:
            return Response("Could not extract blog content", status=422)

        # Images (og + article)
        images, banner_url = [], None
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            banner_url = og["content"].strip()
            if banner_url:
                images.append(banner_url)
        for img in extract_images(article):
            if img not in images:
                images.append(img)

        image_names = [f"image{i+1}.png" for i in range(len(images))]

        banner_html = f'<p><img src="{banner_url}" alt="Banner"/></p>\n' if banner_url else ""
        content_html = f"<h1>{title}</h1>\n{banner_html}{str(article).strip()}"

        result = {
            "title": title or "",
            "content_html": content_html,
            "images": images,
            "image_names": image_names,
        }
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json")
    except Exception as e:
        logging.exception("Error scraping blog")
        return Response(f"Error: {str(e)}", status=500)

@app.route("/html-to-image", methods=["POST"])
def html_to_image():
    """
    იყენებს htmlcsstoimage.com API-ს HTML -> PNG გენერაციაში.
    Env: HCTI_USER_ID, HCTI_API_KEY
    Body: { "html": "...", "css": "...(optional)...", "width": 800 (optional) }
    """
    HCTI_USER_ID = os.environ.get("HCTI_USER_ID")
    HCTI_API_KEY = os.environ.get("HCTI_API_KEY")
    if not HCTI_USER_ID or not HCTI_API_KEY:
        return jsonify({
            "ok": False,
            "error": "HCTI credentials not configured",
            "hint": "Set HCTI_USER_ID and HCTI_API_KEY in Render Environment Variables."
        }), 501

    data = request.get_json(force=True) or {}
    html = data.get("html", "")
    css = data.get("css", "")
    width = data.get("width")  # optional

    if not html:
        return jsonify({"ok": False, "error": "Missing 'html'"}), 400

    payload = {"html": html}
    if css: payload["css"] = css
    if width: payload["viewport_width"] = str(width)

    try:
        r = requests.post(
            "https://hcti.io/v1/image",
            data=payload,
            auth=(HCTI_USER_ID, HCTI_API_KEY),
            timeout=30,
        )
        r.raise_for_status()
        return jsonify({"ok": True, "hcti": r.json()})
    except Exception as e:
        logging.exception("HCTI error")
        return jsonify({"ok": False, "error": str(e)}), 502

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
