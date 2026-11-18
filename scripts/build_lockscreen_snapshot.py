"""Build the read-only data snapshot used by the lock-screen showcase.

The showcase (`/static/lockscreen-showcase.html`) shows every active poll in its
*voted* state. Casting real votes to get there would pollute the `votes` table
(there is no dedup), so instead this script reads the database once — SELECTs
only, nothing is written — and saves, per poll, exactly the data the vote
endpoint would have returned: results, bridge sentences and products for every
option, in English and German.

Output (overwritten on every run):
    app/static/lockscreen-data/index.json        list of polls, in showcase order
    app/static/lockscreen-data/<poll_id>.json    one file per poll

Usage:
    venv/bin/python scripts/build_lockscreen_snapshot.py

Re-run it whenever polls, bridges or products change and you want the showcase
to reflect that.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.routes.public import _render_products  # noqa: E402
from app.services import poll_service  # noqa: E402

OUT_DIR = ROOT / "app" / "static" / "lockscreen-data"
LOCALES = ("en", "de")


async def build_poll(poll: dict) -> dict:
    results = await poll_service.get_results(poll["id"])
    option_ids = [o["id"] for o in poll["options"]]

    per_locale = {}
    for locale in LOCALES:
        rows = await poll_service.get_cached_recs_bulk(option_ids, locale)
        # Same label override the vote endpoint applies for the reader's locale.
        overrides = {
            o["id"]: (o.get("translations") or {}).get(locale, {}).get("label")
            for o in poll["options"]
        }
        per_locale[locale] = {
            "results": [
                {**r, "label": overrides.get(r["option_id"]) or r["label"]}
                for r in results["results"]
            ],
            "total": results["total"],
            "by_option": {
                oid: {
                    "bridge": row["bridge"],
                    # Full product fields (same as the vote endpoint), so the showcase can
                    # also render today's widget side by side with the compact one.
                    "recommendations": _render_products(row["products"], locale),
                }
                for oid, row in rows.items()
            },
        }

    # Showcase opens on the most popular answer (ties: first in poll order).
    most_voted = max(results["results"], key=lambda r: r["count"])["option_id"] if results["results"] else None

    return {
        "poll": {
            "id": poll["id"],
            "question": poll["question"],
            "translations": poll.get("translations") or {},
            "publisher_name": poll.get("publisher_name"),
            "options": [
                {"id": o["id"], "label": o["label"], "translations": o.get("translations") or {}}
                for o in poll["options"]
            ],
        },
        "default_option_id": most_voted,
        "locales": per_locale,
    }


async def main() -> None:
    polls = [p for p in await poll_service.list_polls() if p.get("status") == "active"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()

    index = []
    for poll in polls:
        data = await build_poll(poll)
        (OUT_DIR / f"{poll['id']}.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        index.append({
            "id": poll["id"],
            "question": poll["question"],
            "translations": poll.get("translations") or {},
            "publisher_name": poll.get("publisher_name"),
        })
        print(f"  {poll['id'][:8]}  {poll['question']}")

    (OUT_DIR / "index.json").write_text(
        json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "polls": index},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {len(index)} polls to {OUT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    asyncio.run(main())
