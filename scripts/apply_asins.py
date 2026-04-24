"""Attach verified Amazon ASINs to seeded flagship products.

Matches on substring (case-insensitive) against product title, so the map can
use a canonical core name. Where a match is found, sets `amazon_asin` so the
widget CTA links to `/dp/<asin>` instead of a search URL.

Every ASIN here was verified via Amazon search results (see scripts/
README_ASINS.md). Products not in this map fall back to search URLs.

Usage: venv/bin/python scripts/apply_asins.py
Idempotent.
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402


# title-substring (lowercase) -> verified ASIN
ASINS = {
    "sony wh-1000xm5":                  "B09XS7JWHH",
    "bose quietcomfort ultra":          "B0CCZ1L489",
    "irobot roomba j7+":                "B094NYHTMF",
    "garmin forerunner 265":            "B0BS1T9J4Y",
    "dyson purifier hp07":              "B09LSMRKFD",
    "breville barista express":         "B00CH9QWOU",
    "nest learning thermostat":         "B0D5BBYRJM",
    "coros pace 3":                     "B0CFQQ9FDL",
    "ecobee premium":                   "B09XXS48P8",
    "ring video doorbell pro 2":        "B086Q54K53",
    "roborock s8 pro ultra":            "B0BVB5PTDK",
    "weber performer deluxe":           "B00MKB5V1A",
    "bowflex selecttech 552":           "B001ARYU58",
    "concept2 rowerg":                  "B0DQGNHJQ7",
}


def asin_for(title: str) -> Optional[str]:
    t = title.lower()
    for needle, asin in ASINS.items():
        if needle in t:
            return asin
    return None


def main() -> None:
    db = get_db()
    recs = db.table("recommendations").select("*").execute().data or []
    updated_rows = 0
    updated_products = 0
    for rec in recs:
        products = rec.get("products") or []
        changed = False
        for p in products:
            asin = asin_for(p["title"])
            if asin and p.get("amazon_asin") != asin:
                p["amazon_asin"] = asin
                changed = True
                updated_products += 1
        if changed:
            db.table("recommendations").update({"products": products}).eq("id", rec["id"]).execute()
            updated_rows += 1
    print(f"Done. Stamped ASIN on {updated_products} product(s) across {updated_rows} row(s).")


if __name__ == "__main__":
    main()
