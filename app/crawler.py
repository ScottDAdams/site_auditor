import requests
from bs4 import BeautifulSoup

def extract_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def crawl_site(base_url, max_pages=20):
    visited = set()
    to_visit = [base_url]
    pages = []

    while to_visit and len(pages) < max_pages:
        url = to_visit.pop(0)

        if url in visited:
            continue

        try:
            res = requests.get(url, timeout=5)
            visited.add(url)

            text = extract_text(res.text)

            pages.append({
                "url": url,
                "content": text,
                "site": base_url
            })

            soup = BeautifulSoup(res.text, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link["href"]

                if href.startswith("/") and base_url in url:
                    full = base_url.rstrip("/") + href
                    to_visit.append(full)

        except:
            continue

    return pages


def crawl_sites(sites):
    all_pages = []
    for site in sites:
        all_pages.extend(crawl_site(site))
    return all_pages
