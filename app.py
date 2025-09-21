import os
import logging
import requests
from flask import Flask, request, Response
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

def clean_html(soup):
    # წავშალოთ <style>, <script>, <svg>, <noscript>
    for tag in soup(["style", "script", "svg", "noscript"]):
        tag.decompose()

    # base64 სურათების წაშლა
    for img in soup.find_all("img"):
        if img.get("src", "").startswith("data:image"):
            img.decompose()

    # მოვაშოროთ ყველაფერი "More resources"-ის მერე
    more_resources = soup.find("h3", string=lambda t: t and "More resources" in t)
    if more_resources:
        for elem in list(more_resources.parent.next_siblings):
            elem.extract()
        more_resources.parent.decompose()

    return soup

@app.route("/scrape-deel", methods=["POST"])
def scrape_deel():
    try:
        data = request.get_json()
        url = data.get("url")
        if not url:
            return Response("Missing URL", status=400)

        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return Response(f"Error fetching {url}", status=500)

        soup = BeautifulSoup(r.text, "html.parser")

        # ვამუშავებთ html-ს
        soup = clean_html(soup)

        # ამოვიღოთ სათაური
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""

        # ამოვიღოთ ბანერის სურათი
        banner_img = None
        if h1:
            banner_img = h1.find_next("img")
        banner_html = f'<p><img src="{banner_img["src"]}" alt="Banner" /></p>' if banner_img else ""

        # ამოვიღოთ მთავარი article
        # Deel-ის ბლოგზე article ხშირად იწყება <h2> ან <p> ჰედერის ქვემოთ
        article_body = []
        if h1:
            for sibling in h1.find_all_next():
                if sibling.name in ["h2", "p", "ul", "ol", "img", "blockquote"]:
                    article_body.append(str(sibling))
        article_html = "\n".join(article_body)

        content_html = f"<h1>{title}</h1>\n{banner_html}\n{article_html}"

        return {
            "title": title,
            "content_html": content_html
        }

    except Exception as e:
        logging.exception("Scraping error")
        return Response(f"Error: {str(e)}", status=500)
