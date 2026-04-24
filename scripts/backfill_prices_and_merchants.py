"""Backfill `price`, `alt_price`, and trim descriptions on every cached product.

- `price`: primary (Amazon) price. Filled from hardcoded category × badge tier if
  the product doesn't already have one (seeded flagship products keep theirs).
- `alt_price`: simulated secondary (Best Buy) price = round(price * 1.08) to a
  tidy $-ending value. Always computed from price so the two merchants show a
  consistent-looking comparison.
- description: clamped to 110 chars at a word boundary. CSS also line-clamps at
  3 lines as a safety net.

Usage:  venv/bin/python scripts/backfill_prices_and_merchants.py
Idempotent: re-running leaves already-stamped products untouched.
"""

import hashlib
import random
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402


# (low_tier, mid_tier, premium_tier) in USD
# low = BEST VALUE, mid = MOST POPULAR/NEW RELEASE, premium = TOP RATED/EDITOR'S PICK
PRICE_RANGES = {
    "running,shoes,sneakers":      (95, 140, 180),
    "mattress,bed,bedroom":        (795, 1395, 2295),
    "headphones,audio,music":      (149, 299, 399),
    "espresso,coffee,machine":     (499, 899, 1499),
    "suitcase,luggage,travel":     (199, 395, 725),
    "office,chair,desk":           (399, 899, 1795),
    "doorbell,camera,security":    (149, 229, 349),
    "knife,chef,kitchen":          (49, 129, 195),
    "vacuum,cleaner,floor":        (399, 699, 1099),
    "thermostat,wall,smart":       (149, 249, 329),
    "television,tv,livingroom":    (699, 1499, 2499),
    "smartwatch,running,watch":    (229, 399, 699),
    "grill,bbq,barbecue":          (349, 799, 1499),
    "sunglasses,summer,beach":     (29, 95, 199),
    "kindle,ebook,reader":         (99, 159, 279),
    "air,purifier,bedroom":        (199, 329, 699),
    "sunscreen,skincare,beach":    (21, 38, 58),
    "bicycle,bike,cycling":        (799, 1799, 3499),
    "dog,cat,pet":                 (49, 129, 249),
    "dumbbells,fitness,gym":       (199, 499, 1199),
}

POLL_TO_CATEGORY = [
    ("kilometres do you actually run",              "running,shoes,sneakers"),
    ("old is your current mattress",                "mattress,bed,bedroom"),
    ("upgrade your headphones",                     "headphones,audio,music"),
    ("Home coffee or café coffee",                  "espresso,coffee,machine"),
    ("Carry-on only",                               "suitcase,luggage,travel"),
    ("How's your back at the end",                  "office,chair,desk"),
    ("package stolen from your porch",              "doorbell,camera,security"),
    ("sharp is the chef's knife",                   "knife,chef,kitchen"),
    ("How often do you actually vacuum",            "vacuum,cleaner,floor"),
    ("energy bill shock moment",                    "thermostat,wall,smart"),
    ("What size is the TV",                         "television,tv,livingroom"),
    ("training for something right now",            "smartwatch,running,watch"),
    ("Gas, charcoal, or pellet grill",              "grill,bbq,barbecue"),
    ("lose or break your last pair of sunglasses",  "sunglasses,summer,beach"),
    ("unread books are on your nightstand",         "kindle,ebook,reader"),
    ("air in your bedroom honestly",                "air,purifier,bedroom"),
    ("Do you wear SPF daily",                       "sunscreen,skincare,beach"),
    ("last replace your main bike",                 "bicycle,bike,cycling"),
    ("dog or cat actually eat",                     "dog,cat,pet"),
    ("Gym or home workouts",                        "dumbbells,fitness,gym"),
]

BADGE_TIER = {
    "BEST VALUE": 0,
    "NEW RELEASE": 1,
    "MOST POPULAR": 1,
    "TOP RATED": 2,
    "EDITOR'S PICK": 2,
}


def category_for(question: str) -> Optional[str]:
    for needle, cat in POLL_TO_CATEGORY:
        if needle.lower() in question.lower():
            return cat
    return None


def _pretty_round(n: float) -> int:
    """Round to a plausible shelf price ending (e.g. $29, $149, $1,295)."""
    if n < 50:
        return max(5, round(n))
    if n < 200:
        return round(n / 5) * 5 - 1 if round(n / 5) * 5 > n else round(n / 5) * 5
    if n < 1000:
        # round to nearest $X9 or $X5
        base = round(n / 10) * 10
        return base - 1 if base - 1 >= 50 else base
    return round(n / 50) * 50 - 5


def estimate_price(title: str, badge: str, category: str) -> str:
    low, mid, high = PRICE_RANGES[category]
    tier = BADGE_TIER.get(badge, 1)
    base = [low, mid, high][tier]
    # deterministic jitter ±12% based on product title
    h = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    jittered = base * (0.88 + 0.24 * h)
    return f"${_pretty_round(jittered):,}"


def parse_money(s: str) -> Optional[float]:
    m = re.search(r"([\d,]+(?:\.\d+)?)", s or "")
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def derive_alt_price(primary: str) -> Optional[str]:
    n = parse_money(primary)
    if n is None:
        return None
    # Best Buy comparison: slightly higher, ~8% up, to make "LOWEST" meaningful on Amazon
    alt = _pretty_round(n * 1.08)
    currency = "€" if "€" in primary else "$"
    return f"{currency}{alt:,}"


def trim_desc(s: str, max_chars: int = 110) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    cut = s[: max_chars + 1]
    idx = cut.rfind(" ")
    if idx < max_chars * 0.6:
        idx = max_chars
    return cut[:idx].rstrip(" ,.;:") + "…"


def main() -> None:
    db = get_db()
    polls = {p["id"]: p for p in (db.table("polls").select("*").execute().data or [])}
    options = db.table("poll_options").select("id, poll_id").execute().data or []
    opt_to_poll = {o["id"]: o["poll_id"] for o in options}
    recs = db.table("recommendations").select("*").execute().data or []

    updated = 0
    print(f"Processing {len(recs)} recommendation rows...")
    for rec in recs:
        poll = polls.get(opt_to_poll.get(rec["option_id"]))
        category = category_for(poll["question"]) if poll else None
        products = rec.get("products") or []
        for p in products:
            # primary price
            if not p.get("price") and category:
                p["price"] = estimate_price(p["title"], p.get("badge", "MOST POPULAR"), category)
            # secondary merchant price
            if p.get("price") and not p.get("alt_price"):
                p["alt_price"] = derive_alt_price(p["price"])
            # description length cap
            p["description"] = trim_desc(p.get("description", ""))
        db.table("recommendations").update({"products": products}).eq("id", rec["id"]).execute()
        updated += 1
    print(f"Done. Updated {updated} rows.")


if __name__ == "__main__":
    main()
