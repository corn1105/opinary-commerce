"""Fetch real product images from Amazon's CDN and set them as each product's
`image_url`.

- Products with `amazon_asin`: scrape their `/dp/<asin>` page, extract hiRes or
  og:image meta tag.
- Products without ASIN: scrape `/s?k=<query>` and grab the first search-result
  thumbnail (the `<img class="s-image">` element).

Both sources return URLs on `m.media-amazon.com/images/...`, which is a public
CDN and hotlink-safe. Images are cached per title within a run so duplicate
products across options only trigger one request.

Best-effort: if scraping fails (Amazon blocked us, product not found, etc.) we
keep the existing loremflickr fallback image untouched.

Usage: venv/bin/python scripts/backfill_real_images.py
"""

import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}


def fetch(url: str, timeout: int = 15) -> Optional[str]:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    !! fetch failed: {e}")
        return None


OG_RE = re.compile(r'<meta\s+[^>]*property="og:image"[^>]*content="([^"]+)"')
HIRES_RE = re.compile(r'"hiRes":"(https://m\.media-amazon\.com[^"]+)"')
LARGE_RE = re.compile(r'"large":"(https://m\.media-amazon\.com[^"]+)"')
SEARCH_IMG_RE = re.compile(
    r'<img[^>]+class="s-image"[^>]*src="(https://m\.media-amazon\.com/images/[^"]+)"'
)


def image_from_dp(asin: str) -> Optional[str]:
    html = fetch(f"https://www.amazon.com/dp/{asin}")
    if not html:
        return None
    for regex in (HIRES_RE, LARGE_RE, OG_RE):
        m = regex.search(html)
        if m:
            return m.group(1)
    return None


def image_from_search(query: str) -> Optional[str]:
    html = fetch(f"https://www.amazon.com/s?k={urllib.parse.quote_plus(query)}")
    if not html:
        return None
    m = SEARCH_IMG_RE.search(html)
    return m.group(1) if m else None


def resolve_image(product: dict) -> Optional[str]:
    if product.get("amazon_asin"):
        return image_from_dp(product["amazon_asin"]) or image_from_search(product["query"])
    return image_from_search(product["query"])


def main() -> None:
    db = get_db()
    recs = db.table("recommendations").select("*").execute().data or []

    # Cache: title -> resolved image URL (or None if attempted and failed)
    cache: dict[str, Optional[str]] = {}

    total_rows = len(recs)
    total_products = sum(len(r.get("products") or []) for r in recs)
    print(f"Scanning {total_products} products across {total_rows} recs...\n")

    rows_updated = 0
    for i, rec in enumerate(recs, 1):
        products = rec.get("products") or []
        changed = False
        for p in products:
            title = p.get("title", "").strip()
            if not title:
                continue
            if title not in cache:
                print(f"  [{i:3d}/{total_rows}] {title[:50]:52s} ", end="", flush=True)
                img = resolve_image(p)
                cache[title] = img
                print(f"=> {img[:60] + '…' if img and len(img) > 60 else img or 'NOT FOUND'}")
                time.sleep(0.35)  # polite rate-limit
            img = cache[title]
            if img and p.get("image_url") != img:
                p["image_url"] = img
                changed = True
        if changed:
            db.table("recommendations").update({"products": products}).eq("id", rec["id"]).execute()
            rows_updated += 1

    resolved = sum(1 for v in cache.values() if v)
    print(f"\nDone. {resolved}/{len(cache)} unique products got real images. {rows_updated} recs updated.")


if __name__ == "__main__":
    main()
