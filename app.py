# blog_scraper_clean.py
# -*- coding: utf-8 -*-

import os
import re
import json
import logging
import requests
from flask import Flask, request, Response
from flask_cors import CORS
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app)

# ------------------------------
# Helper: სურათების ამოღება
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

# ------------------------------
# Helper: HTML გაწმენდა
# ------------------------------
def clean_article(article):
    for tag in article(["script", "style", "svg", "noscript"]):
        tag.decompose()

    for tag in article.find_all(True):
        if tag.name not in ["p", "h1", "h2", "h3", "ul", "ol", "li",
                            "img", "strong", "em", "b", "i", "a"]:
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
            alt = tag.get("alt", "").strip() or "Image"
            tag.attrs = {"src": src or "", "alt": alt}
        else:
            tag.attrs = {}

    return article

# ------------------------------
# Blog content extraction (Deel)
# ------------------------------
def extract_blog_content(html: str):
    soup = BeautifulSoup(html, "html.parser")

    # Title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Main article
    article = soup.find("article")
    if not article:
        return title, ""

    article = clean_article(article)
    return title, str(article)

# ------------------------------
# API
# ------------------------------
@app.route("/scrape-blog", methods=["POST"])
def scrape_blog():
    try:
        data = request.get_json(force=True)
        url = data.get("url")
        if not url:
            return Response("Missing 'url' field", status=400)

        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        title, article_html = extract_blog_content(html)
        if not article_html:
            return Response("Could not extract blog content", status=422)

        images = []
        banner_url = None

        # Banner (og:image)
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            banner_url = og["content"].strip()
            if banner_url:
                images.append(banner_url)

        # Article images
        article_soup = BeautifulSoup(article_html, "html.parser")
        article_images = extract_images(article_soup)
        for img in article_images:
            if img not in images:
                images.append(img)

        image_names = [f"image{i+1}.png" for i in range(len(images))]

        # Final HTML
        banner_html = f'<p><img src="{banner_url}" alt="Banner"/></p>\n' if banner_url else ""
        content_html = f"<h1>{title}</h1>\n{banner_html}{article_html.strip()}"

        result = {
            "title": title,
            "content_html": content_html,
            "images": images,
            "image_names": image_names,
        }
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json")

    except Exception as e:
        logging.exception("Error scraping blog")
        return Response(f"Error: {str(e)}", status=500)

# ------------------------------
# Run (local only)
# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
