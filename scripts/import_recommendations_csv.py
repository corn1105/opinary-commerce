"""
Import recommendations from a CSV export into the polls + recommendations tables.

CSV columns:
    poll_question, option_label, country, bridge,
    product_rank, product_title, product_asin, amazon_url, product_query, product_badge

Country -> locale mapping (per current data model: locales are en|de):
    USA     -> en
    Germany -> de
    UK / Ireland -> SKIPPED (no locale slot today; keeps the import lossless)

Behavior:
- Polls are matched by exact question text. New polls are created with options
  in the order they first appear in the CSV.
- Recommendations are upserted per (option_id, locale). Bridges are taken from
  the first row of each (poll, option, country) group; products are the rows
  ordered by product_rank.
- Run from repo root:  venv/bin/python scripts/import_recommendations_csv.py <csv-path>
- Add --dry-run to print what would change without writing.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
import unicodedata
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import get_db, upsert_recs  # noqa: E402

COUNTRY_TO_LOCALE = {"USA": "en", "Germany": "de"}

# Allow these non-ASCII characters silently (German + French + Norwegian/Swedish
# brand names + typography + currency). Anything else triggers a warning so
# mojibake or stray encoded bytes get caught early.
ALLOWED_NON_ASCII = set(
    "äöüÄÖÜß"          # German
    "éèêëàâçîïôùûÉÈÊËÀÂÇÎÏÔÙÛŒœ"  # French
    "ÅåÆæØøÑñ"          # Nordic / Spanish for product brand names
    "—–…"               # typography (em/en dash, ellipsis)
    "‚‘’„“”«»"          # quotation marks
    "€£¥¢$°²³"          # currency, units
)

SUSPICIOUS_BIGRAMS = ("Ã¤", "Ã¶", "Ã¼", "Ã©", "Ãœ", "â€", "Â ", "Ä±", "Äì", "Ã±")


def scan_text(value: str, location: str, warnings: list[str]) -> str:
    """Flag any non-ASCII char outside the allow-list; return the value unchanged."""
    if not value:
        return value
    for bigram in SUSPICIOUS_BIGRAMS:
        if bigram in value:
            warnings.append(f"  mojibake bigram {bigram!r} in {location}: {value[:80]!r}")
            return value
    for ch in value:
        if ord(ch) < 32 and ch not in ("\n", "\t"):
            warnings.append(f"  control char U+{ord(ch):04X} in {location}: {value[:80]!r}")
            return value
        if ord(ch) > 127 and ch not in ALLOWED_NON_ASCII:
            try:
                name = unicodedata.name(ch)
            except ValueError:
                name = "?"
            warnings.append(f"  unusual char {ch!r} (U+{ord(ch):04X} {name}) in {location}: {value[:80]!r}")
            return value
    return value


def load_csv(path: Path, warnings: list[str]) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for i, raw in enumerate(csv.DictReader(f)):
            for k, v in list(raw.items()):
                raw[k] = scan_text((v or "").strip(), f"row {i+2} {k}", warnings)
            rows.append(raw)
    return rows


def group_csv(rows: list[dict]) -> "OrderedDict[str, dict]":
    """
    Returns:
        {
          poll_question: {
            "options": OrderedDict(label -> True),         # preserves first-seen order
            "recs":    {(label, locale): {"bridge": str, "products": [dict, ...]}},
          },
          ...
        }
    """
    polls: "OrderedDict[str, dict]" = OrderedDict()
    for r in rows:
        country = r.get("country")
        locale = COUNTRY_TO_LOCALE.get(country)
        if not locale:
            continue
        q = r["poll_question"]
        opt = r["option_label"]
        if not q or not opt:
            continue
        bucket = polls.setdefault(q, {"options": OrderedDict(), "recs": defaultdict(lambda: {"bridge": "", "products": []})})
        bucket["options"][opt] = True
        recs = bucket["recs"][(opt, locale)]
        if not recs["bridge"] and r.get("bridge"):
            recs["bridge"] = r["bridge"]
        recs["products"].append({
            "rank": int(r.get("product_rank") or 0),
            "title": r.get("product_title") or "",
            "description": "",
            "query": r.get("product_query") or "",
            "badge": r.get("product_badge") or "EDITOR'S PICK",
            "amazon_asin": r.get("product_asin") or None,
        })
    # Sort products by rank, drop the rank field.
    for poll in polls.values():
        for key, recs in poll["recs"].items():
            recs["products"].sort(key=lambda p: p["rank"])
            for p in recs["products"]:
                p.pop("rank", None)
                if not p["amazon_asin"]:
                    p.pop("amazon_asin", None)
    return polls


def fetch_existing_polls() -> dict[str, dict]:
    """Returns {question: poll_row_with_options}."""
    db = get_db()
    polls = db.table("polls").select("*").execute().data or []
    if not polls:
        return {}
    poll_ids = [p["id"] for p in polls]
    opts = (
        db.table("poll_options")
        .select("*")
        .in_("poll_id", poll_ids)
        .order("sort_order")
        .execute()
        .data
        or []
    )
    by_poll: dict[str, list[dict]] = defaultdict(list)
    for o in opts:
        by_poll[o["poll_id"]].append(o)
    out: dict[str, dict] = {}
    for p in polls:
        p["options"] = by_poll.get(p["id"], [])
        out[p["question"]] = p
    return out


def ensure_poll(question: str, options: list[str], existing: dict, dry_run: bool) -> Optional[dict]:
    """Create the poll if missing. If options diverge from CSV, leave the existing
    poll alone but warn — option edits cascade-delete votes and we don't want to
    nuke recorded votes silently."""
    db = get_db()
    if question in existing:
        poll = existing[question]
        existing_labels = [o["label"] for o in poll["options"]]
        if existing_labels != options:
            print(
                f"  ⚠ poll exists but options differ:\n"
                f"      DB:  {existing_labels}\n"
                f"      CSV: {options}\n"
                f"      → leaving DB options as-is. Recommendations will only update for matching labels."
            )
        return poll
    print(f"  + creating poll: {question!r}")
    if dry_run:
        return None
    poll_row = db.table("polls").insert({
        "question": question,
        "context_notes": None,
        "publisher_name": None,
        "publisher_logo": None,
        "status": "active",
    }).execute().data[0]
    opt_rows = [
        {"poll_id": poll_row["id"], "label": label, "sort_order": i}
        for i, label in enumerate(options)
    ]
    inserted = db.table("poll_options").insert(opt_rows).execute().data
    poll_row["options"] = sorted(inserted, key=lambda o: o["sort_order"])
    return poll_row


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", help="Path to recommendations CSV")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    args = parser.parse_args()

    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    warnings: list[str] = []
    rows = load_csv(csv_path, warnings)
    print(f"Loaded {len(rows)} CSV rows from {csv_path.name}")

    if warnings:
        print(f"\n⚠ {len(warnings)} text-quality warnings (rows with these chars are still imported):")
        for w in warnings[:30]:
            print(w)
        if len(warnings) > 30:
            print(f"  ... and {len(warnings) - 30} more")

    polls = group_csv(rows)
    print(f"\nGrouped into {len(polls)} unique polls (USA -> en, Germany -> de; UK/Ireland skipped)")

    existing = fetch_existing_polls()
    print(f"DB already has {len(existing)} polls")

    rec_writes = 0
    rec_skips = 0
    for question, bucket in polls.items():
        print(f"\n• {question!r}")
        options = list(bucket["options"].keys())
        poll = ensure_poll(question, options, existing, args.dry_run)
        if poll is None and args.dry_run:
            # Skip rec writes on dry-run-create
            for (opt_label, locale) in bucket["recs"]:
                print(f"    + would write recs ({opt_label!r}, {locale}) [{len(bucket['recs'][(opt_label, locale)]['products'])} products]")
            continue
        opt_id_by_label = {o["label"]: o["id"] for o in poll["options"]}
        for (opt_label, locale), recs in bucket["recs"].items():
            opt_id = opt_id_by_label.get(opt_label)
            if not opt_id:
                print(f"    ⚠ option {opt_label!r} not in DB poll → skipping {locale} recs")
                rec_skips += 1
                continue
            n = len(recs["products"])
            print(f"    → upserting recs ({opt_label!r}, {locale}) [{n} products]")
            if args.dry_run:
                continue
            await upsert_recs(
                option_id=opt_id,
                locale=locale,
                bridge=recs["bridge"],
                products=recs["products"],
            )
            rec_writes += 1

    print()
    print(f"Done. recs written: {rec_writes}, recs skipped: {rec_skips}{' (DRY RUN)' if args.dry_run else ''}")


if __name__ == "__main__":
    asyncio.run(main())
