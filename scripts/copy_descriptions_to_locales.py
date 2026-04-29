"""
Copy product descriptions from rich locales (en-US, de-DE) into thinner ones
(en, de) by matching product title within the same option_id.

The CSV import populated en/de with title+query+badge but no description.
Earlier Claude generations stored descriptions under the country-tagged
locales (en-US, de-DE). Both layers reference the same products by title,
so we can lift descriptions across without regenerating.

Idempotent: only fills missing descriptions, never overwrites.

Usage:  venv/bin/python scripts/copy_descriptions_to_locales.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db  # noqa: E402

SOURCE_TO_TARGET = {"en-US": "en", "de-DE": "de"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = get_db()
    recs = db.table("recommendations").select("*").execute().data or []

    # Index by (option_id, locale)
    by_key = {(r["option_id"], r["locale"]): r for r in recs}

    filled = 0
    for (opt_id, target_loc), rec in list(by_key.items()):
        source_loc = next((src for src, tgt in SOURCE_TO_TARGET.items() if tgt == target_loc), None)
        if source_loc is None:
            continue
        source_rec = by_key.get((opt_id, source_loc))
        if source_rec is None:
            continue

        source_desc_by_title = {p["title"]: p.get("description", "") for p in source_rec["products"]}
        changed = False
        for p in rec["products"]:
            if not p.get("description") and source_desc_by_title.get(p["title"]):
                p["description"] = source_desc_by_title[p["title"]]
                changed = True
        if changed:
            print(f"  → {target_loc} option {opt_id[:8]}: filled {sum(1 for p in rec['products'] if p.get('description'))}/{len(rec['products'])} descriptions from {source_loc}")
            filled += 1
            if not args.dry_run:
                db.table("recommendations").update({"products": rec["products"]}).eq("id", rec["id"]).execute()

    print(f"\nDone. Updated {filled} rows.{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
