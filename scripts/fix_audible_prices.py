"""
Override Audible Premium Plus prices across all locales. The generic
category-tier pricing in backfill_prices_and_merchants.py treats it like a
flagship Kindle/ebook product (e.g. €279 for "3 Monate") which doesn't match
real-world Audible pricing.

Realistic Premium Plus pricing the demo should mirror:
  - Monthly: $14.95 / €9.95 / £7.99 (rounded for demo)
  - Annual:  ~$149 / ~€99   / ~£79
  - 3-month: 3 × monthly (~$45 / €29 / £24)

Best Buy doesn't sell Audible, so alt_price is also cleared.

Idempotent: re-running re-applies the same prices, no state drift.

Usage:  venv/bin/python scripts/fix_audible_prices.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402

# (locale, variant) -> price string. Variants matched by title keywords below.
PRICES = {
    ("en",    "monthly"): "$15/mo",
    ("en-US", "monthly"): "$15/mo",
    ("en-GB", "monthly"): "£8/mo",
    ("en-IE", "monthly"): "€10/mo",
    ("de",    "monthly"): "€10/Monat",
    ("de-DE", "monthly"): "€10/Monat",

    ("en",    "annual"):  "$149",
    ("en-US", "annual"):  "$149",
    ("en-GB", "annual"):  "£79",
    ("en-IE", "annual"):  "€99",
    ("de",    "annual"):  "€99",
    ("de-DE", "annual"):  "€99",

    ("en",    "3month"):  "$45",
    ("en-US", "3month"):  "$45",
    ("en-GB", "3month"):  "£24",
    ("en-IE", "3month"):  "€29",
    ("de",    "3month"):  "€29",
    ("de-DE", "3month"):  "€29",
}


def variant_for(title: str) -> str:
    t = title.lower()
    if "jahresabo" in t or "annual" in t or "yearly" in t:
        return "annual"
    if "3 monate" in t or "3 month" in t or "(3 mo" in t:
        return "3month"
    # Trial converts to monthly billing — show monthly price so the demo CTA
    # makes sense rather than "kostenlos / Bestpreis" looking confusing.
    return "monthly"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = get_db()
    recs = db.table("recommendations").select("id,locale,products").execute().data or []
    touched = 0
    for rec in recs:
        changed = False
        for p in rec["products"]:
            if "audible" not in p["title"].lower():
                continue
            variant = variant_for(p["title"])
            new_price = PRICES.get((rec["locale"], variant))
            if not new_price:
                continue
            old_price = p.get("price")
            old_alt = p.get("alt_price")
            if old_price != new_price or old_alt is not None:
                print(f"  {rec['locale']:6s} {variant:7s} | {p['title'][:48]:48s} | {old_price!r:10s} → {new_price!r}{' (clear alt_price)' if old_alt else ''}")
                p["price"] = new_price
                p["alt_price"] = None
                changed = True
        if changed:
            touched += 1
            if not args.dry_run:
                db.table("recommendations").update({"products": rec["products"]}).eq("id", rec["id"]).execute()
    print(f"\nDone. Updated {touched} recommendation rows.{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
