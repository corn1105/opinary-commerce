"""Fill every un-cached (option, locale='en') recommendation via Claude.

Intended to run once after scripts/seed_polls.py so every poll option has a
cached bridge+products and voting never hits Claude in the browser path.

Concurrency is capped at 5 to stay under Anthropic rate limits comfortably.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services import claude_service, poll_service  # noqa: E402

SEM = asyncio.Semaphore(5)


async def fill_option(poll_question: str, option: dict, context_notes: Optional[str]) -> Tuple[str, str]:
    async with SEM:
        cached = await poll_service.get_cached_recs(option["id"], "en")
        if cached:
            return (option["label"], "skip (already cached)")
        try:
            payload = await claude_service.generate_recommendations(
                question=poll_question,
                option_label=option["label"],
                context_notes=context_notes,
                locale="en",
            )
            await poll_service.upsert_recs(
                option_id=option["id"],
                locale="en",
                bridge=payload.bridge,
                products=[p.model_dump() for p in payload.products],
            )
            return (option["label"], f"ok ({len(payload.products)} products)")
        except Exception as e:
            return (option["label"], f"ERROR: {e}")


async def main() -> None:
    db = poll_service.get_db()
    polls = db.table("polls").select("*").execute().data or []
    print(f"Checking {len(polls)} polls...")

    tasks = []
    for poll in polls:
        opts = db.table("poll_options").select("*").eq("poll_id", poll["id"]).order("sort_order").execute().data or []
        for opt in opts:
            tasks.append((poll, opt, fill_option(poll["question"], opt, poll.get("context_notes"))))

    total = len(tasks)
    print(f"Processing {total} (option, locale=en) pairs with concurrency=5...\n")

    current_poll_id = None
    done = 0
    for poll, opt, coro in tasks:
        if poll["id"] != current_poll_id:
            current_poll_id = poll["id"]
            print(f"\n[{poll['question'][:60]}{'…' if len(poll['question']) > 60 else ''}]")
        label, status = await coro
        done += 1
        print(f"  ({done:2d}/{total}) {label!r:40s} {status}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
