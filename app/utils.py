"""URL normalization for audit decisions (distinct from form URL helpers in main)."""

from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Normalize for identity comparison: https scheme, lowercase host and path,
    no fragment, no query, trailing slashes removed from path (root stays /).
    """
    if not url or not isinstance(url, str):
        return ""
    p = urlparse(url.strip())
    netloc = (p.netloc or "").lower()
    path = p.path or ""
    path = path.lower()
    if path != "/":
        path = path.rstrip("/") or "/"
    else:
        path = "/"
    if not netloc:
        return ""
    return urlunparse(("https", netloc, path, "", "", ""))


def canonical_resource_key(url: str) -> str:
    """
    Collapses www, /index.html, and homepage variants so SEO-duplicate URLs
    map to one key even when normalize_url still differs (e.g. www host).
    """
    if not url or not isinstance(url, str):
        return ""
    p = urlparse(url.strip())
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (p.path or "/").lower()
    if path.endswith("/index.html"):
        path = path[: -len("/index.html")] or "/"
    elif path.endswith("/index.htm"):
        path = path[: -len("/index.htm")] or "/"
    path = path.rstrip("/") or "/"
    return f"{host}{path}"


def urls_equivalent(a: str, b: str) -> bool:
    return normalize_url(a) == normalize_url(b)


def infer_technical_issue(urls: list[str]) -> str:
    """Short label for technical_fix clusters."""
    if len(urls) < 2:
        return "canonical duplication"
    a, b = urlparse(urls[0]), urlparse(urls[1])
    la, lb = (a.path or "").lower(), (b.path or "").lower()
    if la.rstrip("/") == lb.rstrip("/") and la != lb:
        return "trailing slash / path variant"
    if "index.html" in la or "index.html" in lb or "index.htm" in la or "index.htm" in lb:
        return "homepage variants"
    ha, hb = (a.netloc or "").lower(), (b.netloc or "").lower()
    ha_c = ha[4:] if ha.startswith("www.") else ha
    hb_c = hb[4:] if hb.startswith("www.") else hb
    if ha_c == hb_c and ha != hb:
        return "hostname / www variant"
    if (a.scheme or "").lower() != (b.scheme or "").lower():
        return "canonical duplication (scheme)"
    return "canonical duplication"
