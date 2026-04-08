import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from app.analyzer import classify_page as classify_page_metadata


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


def infer_rule_page_type(url: str, text: str) -> str:
    url_lower = url.lower()
    t = text.lower()
    word_count = len(text.split())

    # STRONG PRODUCT SIGNALS (override everything else)
    if any(
        x in url_lower
        for x in [
            "/our-policies",
            "/policies",
            "/plans",
            "/insurance",
            "/cover",
        ]
    ):
        return "product"

    # Strong URL signals
    if "faq" in url_lower:
        return "faq"
    if "policy" in url_lower or "cover" in url_lower or "insurance" in url_lower:
        return "product"
    if "help" in url_lower or "support" in url_lower or "contact" in url_lower:
        return "support"
    if "about" in url_lower or "careers" in url_lower:
        return "brand"

    product_keywords = [
        "coverage",
        "premium",
        "claim",
        "benefit",
        "excess",
        "deductible",
        "policy",
        "included",
        "exclusion",
    ]
    if sum(1 for kw in product_keywords if kw in t) >= 3:
        return "product"

    # Content-based guide (stricter)
    if (
        ("what is" in t[:500] or "how does" in t[:500])
        and word_count > 800
    ):
        return "guide"

    if "we are" in t[:300] or "our mission" in t[:300]:
        return "brand"

    if "claim" in t and "policy" in t:
        return "product"

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

        soup = BeautifulSoup(response.text, "html.parser")
        title_el = soup.find("title")
        title = (title_el.get_text(strip=True) if title_el else "") or ""
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else ""

        path = url.replace(base_url, "")
        word_count = len(text.split())
        rule_type = infer_rule_page_type(url, text)
        print(f"CLASSIFIED: {url} → {rule_type}")
        classification = classify_page_metadata(url, title, text)
        page = {
            "url": url,
            "path": path,
            "domain": get_domain(url),
            "text": text,
            "title": title,
            "word_count": word_count,
            "type": rule_type,
            "content": text,
            "classification": classification,
        }
        pages.append(page)

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
