"""Build ONE self-contained HTML file: a poll's compact widget on a phone lock
screen, with the poll data and the product photos baked in.

The file needs no server, no admin login and no database, so it can sit inside
a slide deck (or be emailed) and still work. Votes are simulated on screen
only; nothing is ever sent anywhere. Reads the database once (SELECTs only)
and downloads the product thumbnails once, at build time.

Usage:
    venv/bin/python scripts/build_standalone_phone.py <poll_id> <out.html> \
        [--locale en] [--title "Bazr - The Prequel"] [--phone "pad=8&max=2&wp=6&flat=1"]

--phone takes the lockscreen-phone.html options (see the comment at its top).
--prices FILE is a JSON object {"<product title>": "$170", ...}: use these prices
instead of the database's category estimates (e.g. checked prices for a slide).
The database is never changed.
"""

import argparse
import asyncio
import base64
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.routes.public import build_preview  # noqa: E402
from app.services import poll_service  # noqa: E402

STATIC = ROOT / "app" / "static"


def image_data_uri(url: str) -> str:
    """Download one product photo and return it as a data: URI ('' on failure,
    which the widget shows as the bag icon)."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ctype = r.headers.get_content_type() or "image/jpeg"
            data = r.read()
        if not ctype.startswith("image/") or len(data) < 500:
            raise ValueError(f"not an image ({ctype}, {len(data)} bytes)")
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"
    except Exception as e:  # noqa: BLE001
        print(f"  ! image skipped ({e}): {url}")
        return ""


def script_json(value) -> str:
    # Safe inside a <script> block: no literal "</" can close it early.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


async def build(poll_id: str, locale: str, prices: dict) -> dict:
    poll = await poll_service.get_poll(poll_id)
    if not poll:
        sys.exit(f"Poll not found: {poll_id}")
    snap = await build_preview(poll, (locale,))
    loc = snap["locales"][locale]
    n_img = 0
    for block in loc["by_option"].values():
        slim = []
        for p in block["recommendations"]:
            uri = image_data_uri(p.get("image_url") or "")
            n_img += bool(uri)
            slim.append({"title": p["title"], "price": prices.get(p["title"], p.get("price")),
                         "image_url": uri, "amazon_url": p["amazon_url"]})
        block["recommendations"] = slim
    print(f"  {poll['question']}  ({len(loc['by_option'])} answers, {n_img} photos embedded)")
    missing = sorted({p["title"] for b in loc["by_option"].values() for p in b["recommendations"]} - set(prices))
    if prices and missing:
        print("  ! no price override for:", ", ".join(missing))
    return snap


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("poll_id")
    ap.add_argument("out")
    ap.add_argument("--locale", default="en", choices=["en", "de"])
    ap.add_argument("--title", default="Phone preview")
    ap.add_argument("--phone", default="pad=8&max=2&flat=1")
    ap.add_argument("--state", default="vote", choices=["vote", "results"])
    ap.add_argument("--prices", help="JSON file: {product title: price}")
    args = ap.parse_args()
    prices = json.loads(Path(args.prices).read_text(encoding="utf-8")) if args.prices else {}

    snap = asyncio.run(build(args.poll_id, args.locale, prices))

    widget_params = f"poll={args.poll_id}&preview=1&locale={args.locale}&theme=glass"
    if args.state == "results":
        widget_params += "&voted=top"
    widget = (STATIC / "widget-compact.html").read_text(encoding="utf-8")
    widget = widget.replace(
        "<head>",
        "<head>\n<script>window.OPINARY_PARAMS=" + script_json(widget_params)
        + ";window.OPINARY_SNAPSHOT=" + script_json(snap) + ";</script>",
        1,
    )

    phone_params = f"poll={args.poll_id}&locale={args.locale}&state={args.state}&{args.phone}"
    phone = (STATIC / "lockscreen-phone.html").read_text(encoding="utf-8")
    phone = phone.replace("<title>Phone preview</title>", f"<title>{args.title}</title>", 1)
    phone = phone.replace(
        "<head>",
        "<head>\n<script>window.PHONE_PARAMS=" + script_json(phone_params)
        + ";window.PHONE_WIDGET_SRCDOC=" + script_json(widget) + ";</script>",
        1,
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(phone, encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
