"""Backfill `price`, `alt_price`, and trim descriptions on every cached product.

- `price`: primary (Amazon) price.
  1. If the product title matches a row in scripts/product_prices.py (hand-
     checked typical retail), that price is ALWAYS applied for `en` (USD) and
     `de` (EUR), even over an existing price. Re-running re-applies them.
  2. Otherwise, only if the product has no price yet: a category × badge tier
     estimate (the old behaviour). The script prints these titles so someone
     can add a real row to product_prices.py.
- `alt_price`: simulated secondary-shop price (Best Buy for en, Otto for de) =
  price × 1.08 at a tidy ending. Recomputed whenever the price comes from
  product_prices.py; cleared for subscriptions and books (NO_ALT_PRICE).
- description: clamped to 110 chars at a word boundary. CSS also line-clamps at
  3 lines as a safety net.

Prices are display strings shown verbatim by the widget, formatted for the
reader: English "$1,299", German "1.299 €" (no-break space before €).

Usage:  venv/bin/python scripts/backfill_prices_and_merchants.py [--dry-run]
Only rows that actually change are written.
"""

import argparse
import copy
import hashlib
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from app.services.poll_service import get_db  # noqa: E402
from product_prices import NO_ALT_PRICE, PRODUCT_PRICES  # noqa: E402

_CURATED = [(re.compile(rx, re.IGNORECASE), usd, eur) for rx, usd, eur in PRODUCT_PRICES]
_NO_ALT = [re.compile(rx, re.IGNORECASE) for rx in NO_ALT_PRICE]

# Fallback only (products with no row in product_prices.py).
# (low_tier, mid_tier, premium_tier) in local currency units; the same numbers
# are used for USD and EUR, which is close enough for an estimate.
# low = BEST VALUE, mid = MOST POPULAR/NEW RELEASE, premium = TOP RATED/EDITOR'S PICK
PRICE_RANGES = {
    "running,shoes,sneakers":      (95, 140, 180),
    "mattress,bed,bedroom":        (499, 1099, 1999),
    "headphones,audio,music":      (99, 249, 379),
    "espresso,coffee,machine":     (149, 499, 999),
    "suitcase,luggage,travel":     (149, 299, 549),
    "office,chair,desk":           (299, 599, 1399),
    "doorbell,camera,security":    (69, 149, 229),
    "knife,chef,kitchen":          (29, 99, 169),
    "vacuum,cleaner,floor":        (299, 549, 999),
    "thermostat,wall,smart":       (79, 179, 249),
    "television,tv,livingroom":    (449, 999, 1999),
    "smartwatch,running,watch":    (199, 349, 549),
    "grill,bbq,barbecue":          (249, 599, 1199),
    "sunglasses,summer,beach":     (29, 95, 179),
    "kindle,ebook,reader":         (99, 159, 279),
    "air,purifier,bedroom":        (99, 199, 549),
    "sunscreen,skincare,beach":    (12, 25, 39),
    "skincare,face,serum":         (12, 25, 45),
    "bicycle,bike,cycling":        (499, 1099, 2299),
    "dog,cat,pet":                 (25, 59, 99),
    "dumbbells,fitness,gym":       (39, 199, 449),
    # Sleep gadgets (masks, pillows, trackers, sunrise clocks) — NOT mattresses.
    "sleep,gadgets":               (35, 149, 299),
    # Small home-workout kit (bands, kettlebells, books, suspension trainers).
    "fitness,accessories":         (15, 39, 129),
}

# PRIMARY mapping: poll id -> category. Keyed by id (stable) so re-wording a
# question or running a non-English (e.g. German) poll can never silently drop
# the price — and with it the buy button. Covers every active poll; add a row
# when you add a poll. The question-substring list below is only a fallback for
# polls absent from this map.
POLL_ID_TO_CATEGORY = {
    "2b6575af-2ac8-490e-a93d-364878ee981b": "smartwatch,running,watch",   # Are you training for something?
    "00ae2b55-ce68-4786-8f44-b723a88e4d74": "suitcase,luggage,travel",    # Carry-on only, or do you check a bag?
    "5b2923e8-10f1-42db-8de1-b5af44e1c10c": "sunscreen,skincare,beach",   # Do you wear SPF daily?
    "df173ccb-e636-4968-9803-95cedc20a989": "grill,bbq,barbecue",         # Gas, charcoal, or pellet grill?
    "804c7bf8-4e57-4ee3-8a9b-abcc2a9ea3c5": "dumbbells,fitness,gym",      # Gym or home workouts?
    "cf4db86d-4f0f-4b95-9d48-ccb7e17727e9": "doorbell,camera,security",   # Has a package ever been stolen from your porch?
    "9cce8d26-54c4-432d-be0b-2eb20d8cd009": "espresso,coffee,machine",    # Home coffee or café coffee?
    "e113e145-210c-44f3-83f4-736010665fac": "television,tv,livingroom",   # How big is your living-room TV?
    "fc761120-5102-4a7c-8f0e-168a2eb6b490": "sunglasses,summer,beach",    # How did you lose or break your last pair of sunglasses?
    "33021a8d-ff34-4482-832e-a3051b32361e": "sleep,gadgets",              # How many hours sleep do you need?
    "251d0db1-0bc9-4fb8-9525-c9b72b9dd876": "running,shoes,sneakers",     # How many miles do you run a week?
    "eb8bbc4f-6965-4f3a-8a93-519aa26145f0": "kindle,ebook,reader",        # How many unread books are on your nightstand?
    "ac540b1f-fc81-4822-941e-306da8fde58e": "vacuum,cleaner,floor",       # How often do you vacuum?
    "f15ba3c4-779b-4fbc-a2d2-eab05692b247": "mattress,bed,bedroom",       # How old is your mattress?
    "34390375-f77e-4134-b33d-6d149b788a74": "knife,chef,kitchen",         # How sharp is your chef's knife?
    "31c466e6-015a-4f19-aa7a-214d5a3b4313": "air,purifier,bedroom",       # How's the air in your bedroom?
    "ab8df30f-478a-45a5-b77e-683dc06748bd": "office,chair,desk",          # How's your back at the end of a workday?
    "dc314590-acf0-43b3-b898-c68beb809bdc": "running,shoes,sneakers",     # Welche nachhaltige Schuhmarke passt am besten zu dir?
    "e5479266-cd80-4c2c-a8ee-1f0b3a4351d6": "dog,cat,pet",                # What does your dog or cat eat?
    "369c3184-1dbb-4ceb-a142-5f62e195afd9": "fitness,accessories",        # What does your workout routine look like right now?
    "5e748f6a-40d2-45f8-85a5-ac60e2b1111f": "skincare,face,serum",        # What's your biggest skin concern?
    "7f82fb3b-bc3a-4fc7-a5dd-975119a39b37": "bicycle,bike,cycling",       # When did you last replace your main bike?
    "bf393ca1-4163-46e2-a4a0-3e1e88f6476e": "headphones,audio,music",     # When did you last upgrade your headphones?
    "f4a86a8a-7d8c-4665-82bf-ba69ab96d3ed": "thermostat,wall,smart",      # When did your energy bill last shock you?
    "1798d051-20a4-403d-8813-6c61c4afd3fd": "sunscreen,skincare,beach",   # Which SPF do you reach for?
}

# FALLBACK: distinctive substrings — tested against the EN poll question
# (case-insensitive). Only consulted when a poll id is absent from the map above.
POLL_TO_CATEGORY = [
    ("miles do you run",                            "running,shoes,sneakers"),
    ("kilometres do you",                           "running,shoes,sneakers"),  # safety net for any unpolished/legacy data
    ("How old is your mattress",                    "mattress,bed,bedroom"),
    ("hours sleep",                                 "sleep,gadgets"),
    ("upgrade your headphones",                     "headphones,audio,music"),
    ("Home coffee or café coffee",                  "espresso,coffee,machine"),
    ("Carry-on only",                               "suitcase,luggage,travel"),
    ("How's your back at the end",                  "office,chair,desk"),
    ("from your porch",                             "doorbell,camera,security"),
    ("sharp is your chef's knife",                  "knife,chef,kitchen"),
    ("vacuum",                                      "vacuum,cleaner,floor"),
    ("energy bill",                                 "thermostat,wall,smart"),
    ("How big is your living-room TV",              "television,tv,livingroom"),
    ("training for something",                      "smartwatch,running,watch"),
    ("Gas, charcoal, or pellet grill",              "grill,bbq,barbecue"),
    ("lose or break your last pair of sunglasses",  "sunglasses,summer,beach"),
    ("unread books are on your nightstand",         "kindle,ebook,reader"),
    ("air in your bedroom",                         "air,purifier,bedroom"),
    ("Do you wear SPF daily",                       "sunscreen,skincare,beach"),
    ("Which SPF do you reach for",                  "sunscreen,skincare,beach"),
    ("last replace your main bike",                 "bicycle,bike,cycling"),
    ("dog or cat",                                  "dog,cat,pet"),
    ("workout routine",                             "fitness,accessories"),
    ("Gym or home",                                 "dumbbells,fitness,gym"),
    ("biggest skin concern",                        "skincare,face,serum"),
]

# Currency by stored locale string. Only `en` and `de` are ever served to
# readers (see locale_service.py); the other rows are legacy and untouched by
# product_prices.py.
LOCALE_CURRENCY = {
    "en":    "$",
    "en-US": "$",
    "en-GB": "£",
    "en-IE": "€",
    "de":    "€",
    "de-DE": "€",
}
# German number style ("1.299 €") for these locales.
GERMAN_FORMAT_LOCALES = {"de", "de-DE"}
# Which column of PRODUCT_PRICES applies to which served locale.
CURATED_COLUMN = {"en": 1, "de": 2}
# Locales that get a secondary-merchant comparison price (retailer chosen per
# locale at render time in public.py: Best Buy for en, Otto for de).
ALT_PRICE_LOCALES = {"en", "en-US", "de", "de-DE"}

BADGE_TIER = {
    "BEST VALUE": 0,
    "NEW RELEASE": 1,
    "MOST POPULAR": 1,
    "TOP RATED": 2,
    "EDITOR'S PICK": 2,
}


def category_for(poll: dict) -> Optional[str]:
    """Resolve a poll's price category. Prefers the stable poll-id map; falls
    back to scanning the question text for legacy/unmapped polls."""
    cat = POLL_ID_TO_CATEGORY.get(poll.get("id"))
    if cat:
        return cat
    question = poll.get("question") or ""
    for needle, c in POLL_TO_CATEGORY:
        if needle.lower() in question.lower():
            return c
    return None


def format_price(n: int, locale: str) -> str:
    """$1,299 for English readers, 1.299 € for German readers."""
    if locale in GERMAN_FORMAT_LOCALES:
        return f"{n:,}".replace(",", ".") + " €"
    return f"{LOCALE_CURRENCY.get(locale, '$')}{n:,}"


def curated_price(title: str, locale: str) -> Optional[str]:
    """Hand-checked price from product_prices.py, formatted for `locale`."""
    col = CURATED_COLUMN.get(locale)
    if col is None:
        return None
    for row in _CURATED:
        if row[0].search(title or ""):
            value = row[col]
            if value is None:
                return None
            return value if isinstance(value, str) else format_price(value, locale)
    return None


def wants_alt_price(title: str, price: Optional[str]) -> bool:
    if not price or "/" in price:  # subscriptions ("$14.95/mo") never get one
        return False
    return not any(rx.search(title or "") for rx in _NO_ALT)


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


def estimate_price(title: str, badge: str, category: str, locale: str) -> str:
    low, mid, high = PRICE_RANGES[category]
    tier = BADGE_TIER.get(badge, 1)
    base = [low, mid, high][tier]
    # deterministic jitter ±12% based on product title
    h = int(hashlib.md5(title.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    jittered = base * (0.88 + 0.24 * h)
    return format_price(_pretty_round(jittered), locale)


def parse_money(s: str) -> Optional[float]:
    """Read "$1,299", "€1,299" (old German style), "1.299 €" or "9,95 €"."""
    s = (s or "").strip()
    m = re.search(r"\d[\d.,]*", s)
    if not m:
        return None
    num = m.group(0)
    if s.endswith("€") or "€/" in s:  # German: "." groups thousands, "," is decimal
        num = num.replace(".", "").replace(",", ".")
    else:
        num = num.replace(",", "")
    return float(num)


def derive_alt_price(primary: str, locale: str) -> Optional[str]:
    n = parse_money(primary)
    if n is None:
        return None
    # Comparison shop: ~8% higher, so the Amazon price reads as the lowest.
    return format_price(_pretty_round(n * 1.08), locale)


def trim_desc(s: str, max_chars: int = 110) -> str:
    s = (s or "").strip()
    # Already short enough — or already trimmed by an earlier run (110 chars +
    # "…"). Without the second check every re-run chopped off another word.
    if len(s) <= max_chars or (s.endswith("…") and len(s) <= max_chars + 1):
        return s
    cut = s[: max_chars + 1]
    idx = cut.rfind(" ")
    if idx < max_chars * 0.6:
        idx = max_chars
    return cut[:idx].rstrip(" ,.;:") + "…"


def apply_prices(products: list, locale: str, category: Optional[str], unmatched: set) -> list:
    """Return a new product list with prices/alt prices/descriptions fixed."""
    out = copy.deepcopy(products)
    show_alt = locale in ALT_PRICE_LOCALES
    for p in out:
        title = p.get("title", "")
        curated = curated_price(title, locale)
        if curated:
            p["price"] = curated
        elif not p.get("price") and category:
            p["price"] = estimate_price(title, p.get("badge", "MOST POPULAR"), category, locale)
        if locale in CURATED_COLUMN and not curated:
            unmatched.add((locale, title))

        if show_alt and wants_alt_price(title, p.get("price")):
            if curated or not p.get("alt_price"):
                p["alt_price"] = derive_alt_price(p["price"], locale)
        elif locale in CURATED_COLUMN and (curated or not wants_alt_price(title, p.get("price"))):
            p["alt_price"] = None

        p["description"] = trim_desc(p.get("description", ""))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    args = parser.parse_args()

    db = get_db()
    polls = {p["id"]: p for p in (db.table("polls").select("*").execute().data or [])}
    options = db.table("poll_options").select("id, poll_id").execute().data or []
    opt_to_poll = {o["id"]: o["poll_id"] for o in options}
    recs = db.table("recommendations").select("*").execute().data or []

    changed_rows = 0
    changed_products = 0
    no_category = set()
    unmatched: set = set()
    print(f"Processing {len(recs)} recommendation rows...")
    for rec in recs:
        poll = polls.get(opt_to_poll.get(rec["option_id"]))
        category = category_for(poll) if poll else None
        if poll and category is None:
            no_category.add(poll["question"])
        before = rec.get("products") or []
        after = apply_prices(before, rec["locale"], category, unmatched)
        if after == before:
            continue
        for b, a in zip(before, after):
            if b != a:
                changed_products += 1
                if (b.get("price"), b.get("alt_price")) != (a.get("price"), a.get("alt_price")):
                    print(f"  {rec['locale']:5} {a['title'][:52]:52} {b.get('price')!s:>12} -> {a.get('price')!s:<14}"
                          f" alt {b.get('alt_price')!s:>10} -> {a.get('alt_price')!s}")
        changed_rows += 1
        if not args.dry_run:
            db.table("recommendations").update({"products": after}).eq("id", rec["id"]).execute()

    for q in sorted(no_category):
        print(f"  ⚠ no category for poll: {q!r}")
    if unmatched:
        print(f"\n{len(unmatched)} en/de products have no row in scripts/product_prices.py "
              "(they keep their price, or get a category estimate if they have none):")
        for loc, title in sorted(unmatched):
            print(f"  {loc}  {title}")
    verb = "Would update" if args.dry_run else "Updated"
    print(f"\nDone. {verb} {changed_products} products in {changed_rows} rows."
          f"{' (dry run — nothing written)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
