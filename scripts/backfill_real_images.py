"""Fetch real product images AND ASINs from Amazon and store them on each
cached product (`image_url`, `amazon_asin`).

- Products with `amazon_asin`: scrape their `/dp/<asin>` page for the image.
- Products without ASIN: scrape `/s?k=<query>` and grab the first search result's
  thumbnail (`<img class="s-image">`) and its `data-asin` — so the widget can
  deep-link to `/dp/<asin>` instead of falling back to a search URL.

Locale-aware: `de`/`de-DE` rec rows are scraped on amazon.de (German titles search
poorly on amazon.com); everything else on amazon.com.

Images come back on `m.media-amazon.com/images/...`, a public hotlink-safe CDN.
Results are cached per (title, tld) within a run so duplicate products only trigger
one request.

Best-effort: if scraping fails (Amazon blocked us, product not found, etc.) we
leave the existing image/asin untouched.

Usage: venv/bin/python scripts/backfill_real_images.py
"""

import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _tld_for(locale: str) -> str:
    return "de" if (locale or "").lower().startswith("de") else "com"


def fetch(url: str, tld: str, timeout: int = 15) -> Optional[str]:
    accept_lang = "de-DE,de;q=0.9" if tld == "de" else "en-US,en;q=0.9"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": accept_lang})
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
# First organic search result's ASIN (10-char alphanumeric on a search-result tile).
SEARCH_ASIN_RE = re.compile(r'data-asin="([A-Z0-9]{10})"')


def image_from_dp(asin: str, tld: str) -> Optional[str]:
    html = fetch(f"https://www.amazon.{tld}/dp/{asin}", tld)
    if not html:
        return None
    for regex in (HIRES_RE, LARGE_RE, OG_RE):
        m = regex.search(html)
        if m:
            return m.group(1)
    return None


def from_search(query: str, tld: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (image_url, asin) from the first search result, best-effort."""
    html = fetch(f"https://www.amazon.{tld}/s?k={urllib.parse.quote_plus(query)}", tld)
    if not html:
        return (None, None)
    img = SEARCH_IMG_RE.search(html)
    asin = SEARCH_ASIN_RE.search(html)
    return (img.group(1) if img else None, asin.group(1) if asin else None)


def resolve(product: dict, tld: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (image_url, asin) for a product. Keeps any existing ASIN."""
    existing_asin = (product.get("amazon_asin") or "").strip() or None
    if existing_asin:
        img = image_from_dp(existing_asin, tld)
        if img:
            return (img, existing_asin)
        # dp page didn't yield an image — fall back to search for the image only
        img, _ = from_search(product["query"], tld)
        return (img, existing_asin)
    return from_search(product["query"], tld)


def main() -> None:
    db = get_db()
    recs = db.table("recommendations").select("*").execute().data or []

    # Cache: (title, tld) -> (image_url, asin). Same product image/asin regardless
    # of which rec row it appears in, so resolve once per marketplace.
    cache: dict[Tuple[str, str], Tuple[Optional[str], Optional[str]]] = {}

    total_rows = len(recs)
    total_products = sum(len(r.get("products") or []) for r in recs)
    print(f"Scanning {total_products} products across {total_rows} recs...\n")

    rows_updated = 0
    for i, rec in enumerate(recs, 1):
        tld = _tld_for(rec.get("locale", "en"))
        products = rec.get("products") or []
        changed = False
        for p in products:
            title = p.get("title", "").strip()
            if not title:
                continue
            key = (title, tld)
            # Skip products that already have both a real CDN image and an ASIN.
            already = "m.media-amazon.com" in (p.get("image_url") or "") and (p.get("amazon_asin") or "").strip()
            if key not in cache and not already:
                print(f"  [{i:3d}/{total_rows}] [{tld}] {title[:46]:48s} ", end="", flush=True)
                img, asin = resolve(p, tld)
                cache[key] = (img, asin)
                print(f"=> img:{'ok' if img else '—'} asin:{asin or '—'}")
                time.sleep(0.35)  # polite rate-limit
            img, asin = cache.get(key, (None, None))
            if img and p.get("image_url") != img:
                p["image_url"] = img
                changed = True
            if asin and not (p.get("amazon_asin") or "").strip():
                p["amazon_asin"] = asin
                changed = True
        if changed:
            db.table("recommendations").update({"products": products}).eq("id", rec["id"]).execute()
            rows_updated += 1

    img_ok = sum(1 for img, _ in cache.values() if img)
    asin_ok = sum(1 for _, a in cache.values() if a)
    print(f"\nDone. {img_ok}/{len(cache)} got images, {asin_ok}/{len(cache)} got ASINs. {rows_updated} recs updated.")


if __name__ == "__main__":
    main()
