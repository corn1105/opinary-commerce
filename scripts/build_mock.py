"""
Build a client-mockup HTML page from a real article URL with the OpinaryCommerce
poll widget injected mid-article.

Usage:
    python scripts/build_mock.py <article-url> --out <slug>
        [--default-poll-id <uuid>]
        [--embed-origin https://opinarycommerce.up.railway.app]

Writes to app/static/mocks/<slug>.html. Open at:
    http://127.0.0.1:8000/static/mocks/<slug>.html?id=<poll-uuid>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.mockup_service import MockupBuildError, MOCKS_DIR, build_mockup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Article URL to mirror")
    parser.add_argument("--out", required=True, help="Output filename slug (no extension)")
    parser.add_argument("--default-poll-id", default="", help="Poll UUID rendered when ?id= is absent")
    parser.add_argument(
        "--embed-origin",
        default="",
        help="Origin to load /embed.js from (e.g. https://opinarycommerce.up.railway.app). "
             "Empty = same-origin, suitable when the mockup is hosted on the OpinaryCommerce server.",
    )
    parser.add_argument(
        "--locale",
        default="",
        choices=["", "en", "de"],
        help="Locale baked into the embed wrapper (data-locale attribute). Empty = let Accept-Language decide.",
    )
    args = parser.parse_args()

    try:
        out_path = build_mockup(args.url, args.out, args.default_poll_id, args.embed_origin, args.locale)
    except MockupBuildError as e:
        sys.exit(str(e))

    rel = out_path.relative_to(MOCKS_DIR.parent.parent.parent)
    print(f"wrote {rel}")
    print(f"local: http://127.0.0.1:8000/static/mocks/{args.out}.html"
          + (f"?id={args.default_poll_id}" if args.default_poll_id else "?id=<poll-uuid>"))


if __name__ == "__main__":
    main()
