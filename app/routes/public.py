import json
import re
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.models import VoteRequest
from app.services import claude_service, poll_service
from app.services.locale_service import amazon_tld, parse_accept_language

router = APIRouter()

STATIC_DIR = Path(__file__).parent.parent / "static"

WIDGET_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": "frame-ancestors *",
}

# Load widget template once at import time; we SSR a JSON blob into it per request.
_WIDGET_TEMPLATE = (STATIC_DIR / "widget.html").read_text(encoding="utf-8")
_POLL_DATA_PLACEHOLDER = "<!--POLL_DATA_PLACEHOLDER-->"


_AMAZON_SIZE_RE = re.compile(r"\._[A-Z0-9_]+_\.(jpg|jpeg|png|webp)", re.IGNORECASE)


def _thumb(url: str, size: int = 300) -> str:
    """Rewrite Amazon CDN image URLs to request a smaller thumbnail.

    Amazon's m.media-amazon.com supports size modifiers in the URL path itself
    (e.g. ._AC_SL1500_., ._AC_UL320_.). Swapping to ._AC_SL300_. cuts image bytes
    by 10-50x for small card slots without any server-side image work.
    """
    if not url or "m.media-amazon.com/images/" not in url:
        return url
    new_url, n = _AMAZON_SIZE_RE.subn(rf"._AC_SL{size}_.\1", url, count=1)
    return new_url if n else url


def _build_amazon_url(product: dict, locale: str) -> str:
    tld = amazon_tld(locale)
    asin = (product.get("amazon_asin") or "").strip()
    if asin:
        return f"https://www.amazon.{tld}/dp/{asin}"
    return f"https://www.amazon.{tld}/s?k={quote_plus(product['query'])}"


# Secondary "compare" merchant per locale. Best Buy doesn't exist in Europe, so
# `de` uses Otto (broad German generalist — electronics, home, pet, fashion);
# `en` keeps Best Buy. The comparison price is simulated upstream; this only
# decides which retailer + search URL to show.
SECONDARY_MERCHANT = {
    "en": {"name": "Best Buy", "search": "https://www.bestbuy.com/site/searchpage.jsp?st={q}"},
    "de": {"name": "Otto", "search": "https://www.otto.de/suche/{q}"},
}


def _secondary_merchant(locale: str) -> dict:
    return SECONDARY_MERCHANT.get(locale, SECONDARY_MERCHANT["en"])


def _build_alt_url(product: dict, locale: str) -> str:
    return _secondary_merchant(locale)["search"].format(q=quote_plus(product["query"]))


def _render_products(products: list, locale: str) -> list:
    return [
        {
            "title": p["title"],
            "description": p["description"],
            "badge": p["badge"],
            "price": p.get("price"),
            "alt_price": p.get("alt_price"),
            "image_url": _thumb(p.get("image_url", "")),
            "amazon_url": _build_amazon_url(p, locale),
            "alt_merchant": _secondary_merchant(locale)["name"],
            "alt_url": _build_alt_url(p, locale),
        }
        for p in products
    ]


async def build_preview(poll: dict, locales=("en", "de")) -> dict:
    """What a reader would see after voting, for EVERY option — without recording a vote.

    Same data the vote endpoint returns (results, bridge, rendered products), but
    read-only. Used by the admin phone preview (/admin/api/polls/{id}/preview) and
    by scripts/build_lockscreen_snapshot.py. Options with no cached recs in a
    locale are simply missing from `by_option`: a real vote would generate them,
    a preview never calls Claude.
    """
    results = await poll_service.get_results(poll["id"])
    option_ids = [o["id"] for o in poll["options"]]

    per_locale = {}
    for locale in locales:
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
                    "recommendations": _render_products(row["products"], locale),
                }
                for oid, row in rows.items()
            },
        }

    # Previews open on the most popular answer (ties: first in poll order).
    most_voted = (
        max(results["results"], key=lambda r: r["count"])["option_id"] if results["results"] else None
    )

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


@router.get("/widget/{poll_id}", response_class=HTMLResponse)
async def widget(poll_id: str):
    poll = await poll_service.get_poll(poll_id)
    if not poll or poll.get("status") != "active":
        # Fall back to the static template — widget JS will render a "Poll unavailable" error.
        return HTMLResponse(_WIDGET_TEMPLATE, headers=WIDGET_HEADERS)

    payload = {
        "id": poll["id"],
        "question": poll["question"],
        "translations": poll.get("translations") or {},
        "publisher_name": poll.get("publisher_name"),
        "publisher_logo": poll.get("publisher_logo"),
        "options": [
            {"id": o["id"], "label": o["label"], "translations": o.get("translations") or {}}
            for o in poll["options"]
        ],
    }
    # Safe-inject: JSON can't contain raw `</` that would break the script block.
    inline = (
        '<script type="application/json" id="poll-data">'
        + json.dumps(payload).replace("</", "<\\/")
        + "</script>"
    )
    html = _WIDGET_TEMPLATE.replace(_POLL_DATA_PLACEHOLDER, inline)
    return HTMLResponse(html, headers=WIDGET_HEADERS)


@router.get("/embed.js")
async def embed_js():
    embed = STATIC_DIR / "embed.js"
    if not embed.exists():
        raise HTTPException(status_code=500, detail="embed.js not found")
    return FileResponse(
        str(embed),
        media_type="application/javascript",
        # Short TTL + must-revalidate so script edits propagate within minutes.
        # Without `immutable` the browser will conditional-GET on revalidation.
        headers={"Cache-Control": "public, max-age=60, must-revalidate"},
    )


@router.get("/api/polls/{poll_id}")
async def api_get_poll(poll_id: str):
    poll = await poll_service.get_poll(poll_id)
    if not poll or poll.get("status") != "active":
        raise HTTPException(status_code=404, detail="Poll not found")
    return {
        "id": poll["id"],
        "question": poll["question"],
        "translations": poll.get("translations") or {},
        "publisher_name": poll.get("publisher_name"),
        "publisher_logo": poll.get("publisher_logo"),
        "options": [
            {"id": o["id"], "label": o["label"], "translations": o.get("translations") or {}}
            for o in poll["options"]
        ],
    }


@router.get("/api/polls/{poll_id}/results")
async def api_get_results(poll_id: str):
    poll = await poll_service.get_poll(poll_id)
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    return await poll_service.get_results(poll_id)


@router.post("/api/polls/{poll_id}/vote")
async def api_vote(poll_id: str, body: VoteRequest, request: Request):
    poll = await poll_service.get_poll(poll_id)
    if not poll or poll.get("status") != "active":
        raise HTTPException(status_code=404, detail="Poll not found")

    option_ids = {o["id"] for o in poll["options"]}
    if body.option_id not in option_ids:
        raise HTTPException(status_code=400, detail="Invalid option for this poll")

    locale = parse_accept_language(request.headers.get("accept-language"))
    await poll_service.record_vote(poll_id, body.option_id, locale)

    results = await poll_service.get_results(poll_id)
    # Swap option labels into the requested locale where translations exist.
    label_overrides = {
        o["id"]: (o.get("translations") or {}).get(locale, {}).get("label")
        for o in poll["options"]
    }
    for r in results["results"]:
        r["is_user_choice"] = r["option_id"] == body.option_id
        if label_overrides.get(r["option_id"]):
            r["label"] = label_overrides[r["option_id"]]

    # Ensure chosen option has recs cached; generate on the fly if missing.
    cached = await poll_service.get_cached_recs(body.option_id, locale)
    if cached is None:
        option_label = next(o["label"] for o in poll["options"] if o["id"] == body.option_id)
        payload = await claude_service.generate_recommendations(
            question=poll["question"],
            option_label=option_label,
            context_notes=poll.get("context_notes"),
            locale=locale,
        )
        cached = await poll_service.upsert_recs(
            option_id=body.option_id,
            locale=locale,
            bridge=payload.bridge,
            products=[p.model_dump() for p in payload.products],
        )

    # Fetch recs for every option in the poll so the widget can let users click
    # through to see other options' bridges + products without another round trip.
    # One batched query with IN() instead of N sequential calls.
    option_ids_list = [o["id"] for o in poll["options"]]
    rows_by_opt = await poll_service.get_cached_recs_bulk(option_ids_list, locale)
    rows_by_opt[body.option_id] = cached  # overlay freshly-generated recs for the voted option
    by_option = {}
    for opt in poll["options"]:
        row = rows_by_opt.get(opt["id"])
        if row:
            by_option[opt["id"]] = {
                "bridge": row["bridge"],
                "recommendations": _render_products(row["products"], locale),
            }

    return {
        **results,
        "publisher_name": poll.get("publisher_name"),
        "publisher_logo": poll.get("publisher_logo"),
        "voted_option_id": body.option_id,
        "by_option": by_option,
        "locale": locale,
    }
