"""Backfill `image_url` on every cached recommendation product.

For any product without an image_url, sets it to a placehold.co URL labeled with
the product name. Admins can replace individual URLs with real product images
via the admin UI (PATCH /admin/api/options/{id}/recommendations/product).

Idempotent: products that already have an image_url are left untouched.
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402


def placeholder_for(name: str) -> str:
    clean = name.replace('"', "").replace("'", "").strip()
    if len(clean) > 28:
        clean = clean[:25] + "..."
    # light gray bg, medium gray text, no decoration
    return f"https://placehold.co/320x200/f5f5f5/888888?text={quote_plus(clean)}&font=roboto"


def main() -> None:
    db = get_db()
    recs = db.table("recommendations").select("*").execute().data or []
    print(f"Processing {len(recs)} recommendation rows...")
    updated = 0
    untouched = 0
    for rec in recs:
        products = rec.get("products") or []
        changed = False
        for p in products:
            if not p.get("image_url"):
                p["image_url"] = placeholder_for(p["title"])
                changed = True
        if changed:
            db.table("recommendations").update({"products": products}).eq("id", rec["id"]).execute()
            updated += 1
        else:
            untouched += 1
    print(f"Updated: {updated}  Untouched: {untouched}")


if __name__ == "__main__":
    main()
