"""URL helpers for audits — use canonicalize_url() for all identity comparisons."""

from urllib.parse import urlparse

from app.utils.url_utils import canonicalize_url


def urls_equivalent(a: str, b: str) -> bool:
    return canonicalize_url(a) == canonicalize_url(b)


def infer_technical_issue(urls: list[str]) -> str:
    """Short label for technical_fix clusters (diagnostic wording only)."""
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


__all__ = ["canonicalize_url", "urls_equivalent", "infer_technical_issue"]
