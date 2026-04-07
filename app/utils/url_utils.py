from urllib.parse import urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""

    parsed = urlparse(url.strip())

    scheme = "https"
    netloc = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")

    # Remove empty path edge case
    if path == "":
        path = ""

    return urlunparse((scheme, netloc, path, "", "", ""))
