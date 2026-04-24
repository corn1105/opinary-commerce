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


def _build_bestbuy_url(product: dict) -> str:
    return f"https://www.bestbuy.com/site/searchpage.jsp?st={quote_plus(product['query'])}"


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
            "bestbuy_url": _build_bestbuy_url(p),
        }
        for p in products
    ]


@router.get("/widget/{poll_id}", response_class=HTMLResponse)
async def widget(poll_id: str):
    poll = await poll_service.get_poll(poll_id)
    if not poll or poll.get("status") != "active":
        # Fall back to the static template — widget JS will render a "Poll unavailable" error.
        return HTMLResponse(_WIDGET_TEMPLATE, headers=WIDGET_HEADERS)

    payload = {
        "id": poll["id"],
        "question": poll["question"],
        "publisher_name": poll.get("publisher_name"),
        "publisher_logo": poll.get("publisher_logo"),
        "options": [{"id": o["id"], "label": o["label"]} for o in poll["options"]],
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
        headers={"Cache-Control": "public, max-age=3600, immutable"},
    )


@router.get("/api/polls/{poll_id}")
async def api_get_poll(poll_id: str):
    poll = await poll_service.get_poll(poll_id)
    if not poll or poll.get("status") != "active":
        raise HTTPException(status_code=404, detail="Poll not found")
    return {
        "id": poll["id"],
        "question": poll["question"],
        "publisher_name": poll.get("publisher_name"),
        "publisher_logo": poll.get("publisher_logo"),
        "options": [{"id": o["id"], "label": o["label"]} for o in poll["options"]],
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
    for r in results["results"]:
        r["is_user_choice"] = r["option_id"] == body.option_id

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
