"""Replace placeholder product images with loremflickr category photos.

loremflickr returns a real Flickr photo matching keyword tags. The `lock`
parameter makes the selection deterministic per product, so re-runs return
the same photo.

Usage: venv/bin/python scripts/update_product_images.py
"""

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402


# Per-poll category keywords. Keyed by an exact substring in the poll question.
POLL_CATEGORIES = [
    ("kilometres do you actually run",     "running,shoes,sneakers"),
    ("old is your current mattress",       "mattress,bed,bedroom"),
    ("upgrade your headphones",            "headphones,audio,music"),
    ("Home coffee or café coffee",         "espresso,coffee,machine"),
    ("Carry-on only",                      "suitcase,luggage,travel"),
    ("How's your back at the end",         "office,chair,desk"),
    ("package stolen from your porch",     "doorbell,camera,security"),
    ("sharp is the chef's knife",          "knife,chef,kitchen"),
    ("How often do you actually vacuum",   "vacuum,cleaner,floor"),
    ("energy bill shock moment",           "thermostat,wall,smart"),
    ("What size is the TV",                "television,tv,livingroom"),
    ("training for something right now",   "smartwatch,running,watch"),
    ("Gas, charcoal, or pellet grill",     "grill,bbq,barbecue"),
    ("lose or break your last pair of sunglasses", "sunglasses,summer,beach"),
    ("unread books are on your nightstand", "kindle,ebook,reader"),
    ("air in your bedroom honestly",       "air,purifier,bedroom"),
    ("Do you wear SPF daily",              "sunscreen,skincare,beach"),
    ("last replace your main bike",        "bicycle,bike,cycling"),
    ("dog or cat actually eat",            "dog,cat,pet"),
    ("Gym or home workouts",               "dumbbells,fitness,gym"),
]


def category_for_question(question: str) -> str:
    for needle, cat in POLL_CATEGORIES:
        if needle.lower() in question.lower():
            return cat
    # generic fallback
    words = re.findall(r"[a-zA-Z]{4,}", question.lower())
    stop = {"actually", "current", "typical", "really", "right", "there", "where", "which", "about", "would", "these", "those", "still", "because", "after", "before", "every", "other", "ever"}
    meaningful = [w for w in words if w not in stop]
    return ",".join(meaningful[:3]) or "product"


def image_url(category: str, product_title: str, idx: int) -> str:
    seed = hashlib.md5(f"{product_title}|{idx}".encode()).hexdigest()[:8]
    return f"https://loremflickr.com/400/300/{quote(category)}?lock={seed}"


def main() -> None:
    db = get_db()
    polls = {p["id"]: p for p in (db.table("polls").select("*").execute().data or [])}
    options = db.table("poll_options").select("*").execute().data or []
    opt_to_poll = {o["id"]: o["poll_id"] for o in options}
    recs = db.table("recommendations").select("*").execute().data or []

    print(f"Updating images on {len(recs)} recommendation rows...")
    updated = 0
    for rec in recs:
        poll_id = opt_to_poll.get(rec["option_id"])
        poll = polls.get(poll_id) if poll_id else None
        category = category_for_question(poll["question"]) if poll else "product"
        products = rec.get("products") or []
        for i, p in enumerate(products):
            p["image_url"] = image_url(category, p["title"], i)
        db.table("recommendations").update({"products": products}).eq("id", rec["id"]).execute()
        updated += 1
    print(f"Done. Updated {updated} rows.")


if __name__ == "__main__":
    main()
