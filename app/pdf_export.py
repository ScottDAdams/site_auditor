"""
HTML fragment → PDF via headless Chromium (Playwright).

Requires: playwright install chromium
"""

from pathlib import Path

PRINT_CSS = """
@page { size: A4; margin: 14mm; }
body {
  font-family: system-ui, -apple-system, Segoe UI, sans-serif;
  color: #1a1a1a;
  line-height: 1.5;
}
.audit-section {
  page-break-inside: avoid;
  break-inside: avoid;
  margin-bottom: 1.25rem;
}
h1, h2 { page-break-after: avoid; }
ul, ol { page-break-inside: avoid; }
"""


def wrap_html_fragment(fragment: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8"/>'
        f"<style>{PRINT_CSS}</style>"
        '<style media="print">'
        ".audit-section { page-break-inside: avoid; }"
        "h2 { page-break-after: avoid; }"
        "</style>"
        "</head><body>"
        f"{fragment}"
        "</body></html>"
    )


def export_report_pdf(html_path: str, output_path: str) -> None:
    """
    Load HTML from disk. If the file is a fragment (no doctype), wrap it with
    print-friendly CSS, then render to PDF.
    """
    from playwright.sync_api import sync_playwright

    path = Path(html_path)
    raw = path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if not stripped.lower().startswith("<!doctype"):
        raw = wrap_html_fragment(raw)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(raw, wait_until="load")
        page.pdf(
            path=str(out.resolve()),
            format="A4",
            print_background=True,
            margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
        )
        browser.close()
