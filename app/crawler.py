import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def get_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)

    word_count = len(text.split())
    # Skip thin content pages
    if word_count < 30:
        return ""

    return text


def classify_page(url: str, text: str) -> str:
    u = url.lower()
    t = text.lower()

    # Strong URL signals
    if "faq" in u:
        return "faq"
    if "policy" in u or "cover" in u or "insurance" in u:
        return "product"
    if "help" in u or "support" in u or "contact" in u:
        return "support"
    if "about" in u or "careers" in u:
        return "brand"

    # Content-based signals
    if "what is" in t[:500] or "how does" in t[:500]:
        return "guide"

    if "we are" in t[:300] or "our mission" in t[:300]:
        return "brand"

    if "claim" in t and "policy" in t:
        return "product"

    # Length-based fallback
    word_count = len(text.split())

    if word_count > 1000:
        return "guide"

    if word_count < 200:
        return "support"

    return "other"


def crawl_site(base_url, max_pages=20):
    visited = set()
    to_visit = [base_url]
    pages = []

    while to_visit and len(pages) < max_pages:
        url = to_visit.pop(0)

        if url in visited:
            continue

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"FAILED TO FETCH: {url} -> {e}")
            visited.add(url)
            continue

        print(f"Fetched: {url}")
        visited.add(url)

        text = extract_text(response.text)

        if not text:
            continue

        path = url.replace(base_url, "")
        word_count = len(text.split())
        page = {
            "url": url,
            "path": path,
            "domain": get_domain(url),
            "text": text,
            "word_count": word_count,
            "type": classify_page(url, text),
            "content": text,
        }
        pages.append(page)

        soup = BeautifulSoup(response.text, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if href.startswith("/") and base_url in url:
                full = base_url.rstrip("/") + href
                to_visit.append(full)

    return pages


def crawl_sites(sites):
    all_pages = []
    for site in sites:
        all_pages.extend(crawl_site(site))
    return all_pages
