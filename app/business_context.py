"""
Business constraints injected before AI decisions (not chat).
"""

import json
import os
from urllib.parse import urlparse


def default_allowed_actions() -> dict:
    return {
        "delete": True,
        "merge": True,
        "redirect": True,
        "consolidate": True,
        "split": True,
        "rewrite": True,
        "differentiate": True,
        "reposition": True,
    }


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


def url_path(url: str) -> str:
    return _normalize_path(urlparse(url or "").path)


def path_matches_protected(url: str, protected_paths: list) -> bool:
    p = url_path(url)
    for raw in protected_paths or []:
        pr = _normalize_path(str(raw))
        if p == pr or p.startswith(pr + "/"):
            return True
    return False


def role_for_url(url: str, page_roles: dict) -> str | None:
    p = url_path(url)
    roles = page_roles or {}
    if p in roles:
        return roles[p]
    for key, role in roles.items():
        k = _normalize_path(str(key))
        if p == k or p.startswith(k + "/"):
            return role
    return None


def infer_market_context(pages: list) -> dict:
    domains = sorted({p.get("domain") for p in (pages or []) if p.get("domain")})
    regions = []
    for d in domains:
        dl = (d or "").lower()
        if ".co.nz" in dl or dl.endswith(".nz"):
            regions.append("NZ")
        elif ".com.au" in dl or dl.endswith(".au"):
            regions.append("AU")
        elif ".co.uk" in dl:
            regions.append("UK")
    regions = sorted(set(regions))
    separate = len(domains) > 1
    return {
        "separate_regions": separate,
        "regions": regions,
        "domains_in_crawl": domains,
    }


def _parse_protected_paths() -> list:
    raw = os.getenv("SITE_AUDITOR_PROTECTED_PATHS", "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_page_roles() -> dict:
    raw = os.getenv("SITE_AUDITOR_PAGE_ROLES_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {_normalize_path(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        pass
    return {}


def _parse_allowed_actions() -> dict | None:
    raw = os.getenv("SITE_AUDITOR_ALLOWED_ACTIONS_JSON", "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            base = default_allowed_actions()
            base.update({k: bool(v) for k, v in data.items()})
            return base
    except json.JSONDecodeError:
        pass
    return None


def build_business_context(pages: list) -> dict:
    mc = infer_market_context(pages)
    aa = _parse_allowed_actions() or default_allowed_actions()
    return {
        "protected_paths": _parse_protected_paths(),
        "page_roles": _parse_page_roles(),
        "market_context": {
            "separate_regions": mc["separate_regions"],
            "regions": mc["regions"],
        },
        "allowed_actions": aa,
    }


def is_cross_domain(url_a: str, url_b: str) -> bool:
    try:
        return urlparse(url_a).netloc != urlparse(url_b).netloc
    except Exception:
        return False


def url_requires_preservation(url: str, bc: dict) -> bool:
    if path_matches_protected(url, bc.get("protected_paths") or []):
        return True
    if role_for_url(url, bc.get("page_roles") or {}) == "core_product":
        return True
    return False


def effective_allowed_actions(bc: dict | None) -> dict:
    merged = default_allowed_actions()
    if bc and isinstance(bc.get("allowed_actions"), dict):
        merged.update(bc["allowed_actions"])
    return merged


def roadmap_step_allowed(step: dict, bc: dict | None) -> bool:
    if not isinstance(step, dict):
        return False
    bc = bc or {}
    allowed = effective_allowed_actions(bc)
    at = (step.get("action_type") or "").lower().strip()
    if at not in allowed or not allowed.get(at, False):
        return False
    urls = step.get("target_urls") or []
    if not isinstance(urls, list):
        return False

    if at == "delete":
        for u in urls:
            if url_requires_preservation(str(u), bc):
                return False

    if at in ("merge", "consolidate"):
        for u in urls:
            if url_requires_preservation(str(u), bc):
                return False

    if at == "redirect" and len(urls) >= 2:
        src = str(urls[0])
        if url_requires_preservation(src, bc):
            return False

    if at in ("merge", "consolidate", "redirect") and len(urls) >= 2:
        if (bc.get("market_context") or {}).get("separate_regions"):
            if is_cross_domain(str(urls[0]), str(urls[1])):
                return False

    return True
