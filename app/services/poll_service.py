from typing import Optional

from supabase import Client, create_client

from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


# ---------- Polls ----------

async def list_polls() -> list[dict]:
    db = get_db()
    polls = db.table("polls").select("*").order("created_at", desc=True).execute().data or []
    if not polls:
        return polls
    poll_ids = [p["id"] for p in polls]
    # Batch: options for all polls, then recs for all options — avoids N+1 on the list view.
    opts_rows = db.table("poll_options").select("*").in_("poll_id", poll_ids).order("sort_order").execute().data or []
    opts_by_poll: dict[str, list] = {}
    for o in opts_rows:
        opts_by_poll.setdefault(o["poll_id"], []).append(o)
    option_ids = [o["id"] for o in opts_rows]
    rec_rows = (
        db.table("recommendations").select("option_id").in_("option_id", option_ids).execute().data or []
        if option_ids else []
    )
    recs_by_option: dict[str, int] = {}
    for r in rec_rows:
        recs_by_option[r["option_id"]] = recs_by_option.get(r["option_id"], 0) + 1
    for p in polls:
        p["options"] = opts_by_poll.get(p["id"], [])
        votes = db.table("votes").select("id", count="exact").eq("poll_id", p["id"]).execute()
        p["vote_count"] = votes.count or 0
        p["rec_count"] = sum(recs_by_option.get(o["id"], 0) for o in p["options"])
    return polls


async def get_poll(poll_id: str) -> Optional[dict]:
    db = get_db()
    res = db.table("polls").select("*").eq("id", poll_id).maybe_single().execute()
    poll = res.data if res else None
    if not poll:
        return None
    opts = db.table("poll_options").select("*").eq("poll_id", poll_id).order("sort_order").execute().data or []
    poll["options"] = opts
    return poll


async def create_poll(
    question: str,
    options: list[dict],
    context_notes: Optional[str],
    publisher_name: Optional[str],
    publisher_logo: Optional[str],
) -> dict:
    db = get_db()
    poll = db.table("polls").insert({
        "question": question,
        "context_notes": context_notes,
        "publisher_name": publisher_name,
        "publisher_logo": publisher_logo,
    }).execute().data[0]
    option_rows = [
        {"poll_id": poll["id"], "label": o["label"], "sort_order": i}
        for i, o in enumerate(options)
    ]
    db.table("poll_options").insert(option_rows).execute()
    return await get_poll(poll["id"])


async def update_poll(poll_id: str, patch: dict, options: Optional[list[dict]]) -> dict:
    db = get_db()
    if patch:
        db.table("polls").update(patch).eq("id", poll_id).execute()
    if options is not None:
        # Simple strategy: delete all existing options and insert fresh.
        # Votes reference option_id, so cascade will drop them. For MVP this is fine;
        # admins are expected to edit options before the poll goes live.
        db.table("poll_options").delete().eq("poll_id", poll_id).execute()
        rows = [
            {"poll_id": poll_id, "label": o["label"], "sort_order": i}
            for i, o in enumerate(options)
        ]
        if rows:
            db.table("poll_options").insert(rows).execute()
    return await get_poll(poll_id)


async def delete_poll(poll_id: str) -> None:
    get_db().table("polls").delete().eq("id", poll_id).execute()


# ---------- Votes ----------

async def record_vote(poll_id: str, option_id: str, locale: str) -> None:
    get_db().table("votes").insert({
        "poll_id": poll_id,
        "option_id": option_id,
        "locale": locale,
    }).execute()


async def get_results(poll_id: str) -> dict:
    db = get_db()
    opts = db.table("poll_options").select("*").eq("poll_id", poll_id).order("sort_order").execute().data or []
    votes = db.table("votes").select("option_id").eq("poll_id", poll_id).execute().data or []
    counts: dict[str, int] = {}
    for v in votes:
        counts[v["option_id"]] = counts.get(v["option_id"], 0) + 1
    results = [
        {"option_id": o["id"], "label": o["label"], "count": counts.get(o["id"], 0)}
        for o in opts
    ]
    total = sum(r["count"] for r in results)
    return {"results": results, "total": total}


# ---------- Recommendations ----------

async def get_cached_recs(option_id: str, locale: str) -> Optional[dict]:
    res = (
        get_db()
        .table("recommendations")
        .select("*")
        .eq("option_id", option_id)
        .eq("locale", locale)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


async def get_cached_recs_bulk(option_ids: list, locale: str) -> dict:
    """Fetch recs for many options in ONE query. Returns {option_id: row_dict}."""
    if not option_ids:
        return {}
    rows = (
        get_db()
        .table("recommendations")
        .select("*")
        .in_("option_id", option_ids)
        .eq("locale", locale)
        .execute()
        .data
        or []
    )
    return {r["option_id"]: r for r in rows}


def _placeholder_image(name: str) -> str:
    """Generic category photo via loremflickr; deterministic per product title."""
    import hashlib
    from urllib.parse import quote
    keywords = ",".join([w for w in name.lower().split() if len(w) > 3][:2]) or "product"
    seed = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"https://loremflickr.com/400/300/{quote(keywords)}?lock={seed}"


async def upsert_recs(option_id: str, locale: str, bridge: str, products: list[dict]) -> dict:
    from datetime import datetime, timezone
    # Ensure every product has an image_url (placeholder if none provided).
    products = [
        {**p, "image_url": p.get("image_url") or _placeholder_image(p["title"])}
        for p in products
    ]
    row = {
        "option_id": option_id,
        "locale": locale,
        "bridge": bridge,
        "products": products,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return (
        get_db()
        .table("recommendations")
        .upsert(row, on_conflict="option_id,locale")
        .execute()
        .data[0]
    )


async def update_bridge(option_id: str, locale: str, bridge: str) -> Optional[dict]:
    res = (
        get_db()
        .table("recommendations")
        .update({"bridge": bridge})
        .eq("option_id", option_id)
        .eq("locale", locale)
        .execute()
    )
    return res.data[0] if res.data else None


async def list_recs_for_poll(poll_id: str) -> list[dict]:
    db = get_db()
    opts = db.table("poll_options").select("id").eq("poll_id", poll_id).execute().data or []
    option_ids = [o["id"] for o in opts]
    if not option_ids:
        return []
    return db.table("recommendations").select("*").in_("option_id", option_ids).execute().data or []
