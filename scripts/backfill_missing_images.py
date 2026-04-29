"""
Retry pass over `image_url`: only touches products that still carry the
loremflickr placeholder URL after the initial backfill_real_images run.

Improvements vs the first-pass script:
- Skips anything that already has an m.media-amazon.com image (idempotent
  on repeat runs).
- Uses amazon.de for products in `de`/`de-DE` rec rows (German titles like
  "Trockenfutter" don't search well on amazon.com).
- 1.5s sleep between unique requests to dodge the 503 wall the first run
  hit toward the end.
- Title-keyed cache shared across en/de — Amazon's CDN URLs are the same
  product image regardless of marketplace, so resolving once is fine.

Usage: venv/bin/python scripts/backfill_missing_images.py
"""

from __future__ import annotations

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
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

OG_RE = re.compile(r'<meta\s+[^>]*property="og:image"[^>]*content="([^"]+)"')
HIRES_RE = re.compile(r'"hiRes":"(https://m\.media-amazon\.com[^"]+)"')
LARGE_RE = re.compile(r'"large":"(https://m\.media-amazon\.com[^"]+)"')
SEARCH_IMG_RE = re.compile(
    r'<img[^>]+class="s-image"[^>]*src="(https://m\.media-amazon\.com/images/[^"]+)"'
)


def fetch(url: str, accept_lang: str, timeout: int = 20) -> Optional[str]:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": accept_lang}
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    !! fetch failed: {e}")
        return None


def image_from_dp(asin: str, tld: str, accept_lang: str) -> Optional[str]:
    html = fetch(f"https://www.amazon.{tld}/dp/{asin}", accept_lang)
    if not html:
        return None
    for regex in (HIRES_RE, LARGE_RE, OG_RE):
        m = regex.search(html)
        if m:
            return m.group(1)
    return None


def image_from_search(query: str, tld: str, accept_lang: str) -> Optional[str]:
    html = fetch(
        f"https://www.amazon.{tld}/s?k={urllib.parse.quote_plus(query)}",
        accept_lang,
    )
    if not html:
        return None
    m = SEARCH_IMG_RE.search(html)
    return m.group(1) if m else None


def tld_for_locale(locale: str) -> tuple[str, str]:
    """Return (amazon TLD, Accept-Language header) for a stored locale."""
    if locale.startswith("de"):
        return "de", "de-DE,de;q=0.9,en;q=0.5"
    if locale == "en-GB":
        return "co.uk", "en-GB,en;q=0.9"
    if locale == "en-IE":
        return "co.uk", "en-IE,en;q=0.9"  # Amazon Ireland routes through .co.uk
    return "com", "en-US,en;q=0.9"


def is_placeholder(image_url: Optional[str]) -> bool:
    return not image_url or "m.media-amazon.com" not in image_url


def main() -> None:
    db = get_db()
    recs = db.table("recommendations").select("*").execute().data or []

    # Prefer scraping each title against the marketplace it natively belongs to
    # (German title on amazon.de, English title on amazon.com). Cache the result
    # globally — if a real image is found, every locale's row for that product
    # gets it.
    cache: dict[str, Optional[str]] = {}
    todo = []  # (title, asin, query, tld, accept_lang)
    for rec in recs:
        tld, lang = tld_for_locale(rec["locale"])
        for p in rec.get("products") or []:
            if not is_placeholder(p.get("image_url")):
                continue
            title = (p.get("title") or "").strip()
            if not title or title in cache:
                continue
            todo.append((title, p.get("amazon_asin"), p.get("query"), tld, lang))
            cache[title] = None  # mark as queued

    print(f"Found {len(todo)} unique placeholder titles to retry...\n")

    for i, (title, asin, query, tld, lang) in enumerate(todo, 1):
        print(f"  [{i:3d}/{len(todo)}] ({tld}) {title[:55]:57s} ", end="", flush=True)
        img = None
        if asin:
            img = image_from_dp(asin, tld, lang)
        if not img and query:
            img = image_from_search(query, tld, lang)
        cache[title] = img
        print(f"=> {img[:55] + '…' if img and len(img) > 55 else img or 'STILL NOT FOUND'}")
        time.sleep(1.5)

    # Apply: for each rec, swap in the resolved image for any placeholder product.
    rows_updated = 0
    for rec in recs:
        changed = False
        for p in rec.get("products") or []:
            if not is_placeholder(p.get("image_url")):
                continue
            img = cache.get((p.get("title") or "").strip())
            if img:
                p["image_url"] = img
                changed = True
        if changed:
            db.table("recommendations").update({"products": rec["products"]}).eq("id", rec["id"]).execute()
            rows_updated += 1

    resolved = sum(1 for v in cache.values() if v)
    print(f"\nDone. Filled {resolved}/{len(cache)} previously-missing titles. {rows_updated} rec rows updated.")


if __name__ == "__main__":
    main()
