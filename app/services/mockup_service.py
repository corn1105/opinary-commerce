"""
Build a mockup HTML page from an article URL with the OpinaryCommerce poll
widget injected mid-article. Used by both the CLI (`scripts/build_mock.py`)
and the admin "Create mockup" button.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

# Where generated mockup HTML files are written. Defaults to the in-repo
# directory for local dev; on Railway set MOCKS_DIR=/data/mocks (or whatever
# the persistent volume is mounted at) so the files survive redeploys.
_DEFAULT_MOCKS_DIR = Path(__file__).parent.parent / "static" / "mocks"
MOCKS_DIR = Path(os.environ.get("MOCKS_DIR", str(_DEFAULT_MOCKS_DIR)))
SEED_MOCKS_DIR = _DEFAULT_MOCKS_DIR  # Always points at the in-repo bundled mocks for one-time seeding.

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

NOISE_RE = re.compile(
    r"consent|cookie|cmp|sourcepoint|onetrust|didomi|usercentrics|"
    r"paywall|piano|subscribe-modal|newsletter-modal|gdpr|tcf",
    re.I,
)

# <p> tags that live inside these elements are chrome (deks, photo captions,
# bylines, affiliate disclosures, related-article rails), not article body.
NONBODY_ANCESTORS = {"header", "aside", "figure", "figcaption", "nav", "footer"}

# Short meta lines that sometimes sit among the body <p> (timestamps, photo
# credits, affiliate disclaimers). Matched against the paragraph's own text.
META_TEXT_RE = re.compile(
    r"(©|^stand:|^foto:|^bild:|^quelle:|when you purchase|^lesedauer|"
    r"^\s*\d{1,2}\.\d{1,2}\.\d{4})",
    re.I,
)

# Below this length a leading <p> is almost always a caption/credit/meta line
# rather than a real body paragraph.
MIN_BODY_PARA_LEN = 40

URL_ATTRS = {
    "img": ["src", "data-src"],
    "source": ["src"],
    "link": ["href"],
    "script": ["src"],
    "a": ["href"],
    "iframe": ["src"],
    "video": ["src", "poster"],
    "audio": ["src"],
    "use": ["href", "xlink:href"],
}

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")


class MockupBuildError(Exception):
    """Raised when the article can't be turned into a usable mockup."""


def slugify_for_url(url: str, poll_id: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    host_root = host.rsplit(".", 1)[0].replace(".", "-")
    path_tail = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    path_tail = re.sub(r"\.(html?|aspx?|php)$", "", path_tail, flags=re.I)
    path_tail = re.sub(r"[^a-z0-9]+", "-", path_tail.lower()).strip("-")[:50]
    poll_short = poll_id.replace("-", "")[:8]
    return "-".join(p for p in [host_root, path_tail, poll_short] if p) or "mock"


def absolutize(soup: BeautifulSoup, base_url: str) -> None:
    for tag_name, attrs in URL_ATTRS.items():
        for el in soup.find_all(tag_name):
            for attr in attrs:
                val = el.get(attr)
                if val and not val.startswith(("data:", "javascript:", "mailto:", "#")):
                    el[attr] = urljoin(base_url, val)
    for el in soup.find_all(attrs={"srcset": True}):
        el["srcset"] = rewrite_srcset(el["srcset"], base_url)
    for el in soup.find_all(style=True):
        el["style"] = CSS_URL_RE.sub(
            lambda m: f"url({m.group(1)}{urljoin(base_url, m.group(2))}{m.group(1)})",
            el["style"],
        )


def rewrite_srcset(srcset: str, base_url: str) -> str:
    parts = []
    for candidate in srcset.split(","):
        bits = candidate.strip().split(None, 1)
        if not bits:
            continue
        url = urljoin(base_url, bits[0])
        rest = f" {bits[1]}" if len(bits) > 1 else ""
        parts.append(f"{url}{rest}")
    return ", ".join(parts)


def strip_noise(soup: BeautifulSoup) -> None:
    for el in soup.find_all(["script", "noscript"]):
        if el.name == "script" and el.get("type") == "application/ld+json":
            continue
        el.decompose()
    for el in list(soup.find_all(True)):
        if el.parent is None:
            continue
        ident = " ".join(filter(None, [el.get("id", ""), " ".join(el.get("class", []))]))
        if ident and NOISE_RE.search(ident):
            el.decompose()


def _body_paragraphs(container: Tag) -> list:
    """Real article-body <p> tags, excluding chrome and short meta lines.

    Skips paragraphs nested in header/aside/figure/caption/nav/footer (deks,
    photo captions, bylines, affiliate disclosures, related rails) and short
    meta lines (timestamps, credits) so placement lands inside the body text
    rather than above it.
    """
    out = []
    stop = container.parent
    for p in container.find_all("p", recursive=True):
        text = p.get_text(strip=True)
        if not text or len(text) < MIN_BODY_PARA_LEN or META_TEXT_RE.search(text):
            continue
        anc = p.parent
        in_chrome = False
        while anc is not None and anc is not stop:
            if anc.name in NONBODY_ANCESTORS:
                in_chrome = True
                break
            anc = anc.parent
        if not in_chrome:
            out.append(p)
    return out


def find_injection_point(soup: BeautifulSoup) -> Optional[Tag]:
    """Return the body paragraph the poll should be inserted after.

    Placement is "after the fold": the poll sits just after the 2nd real body
    paragraph, but never deeper than the top third of the body by text volume
    (the floor and ceiling collapse to whichever is shallower). Non-body <p>
    (deks, captions, bylines, disclosures) are excluded via _body_paragraphs so
    the poll never lands above the article body.
    """
    container = soup.find("article") or soup.find("main")
    if container is None:
        candidates = soup.find_all("div")
        if not candidates:
            return None
        container = max(candidates, key=lambda d: len(d.find_all("p", recursive=True)))

    paragraphs = _body_paragraphs(container)
    if len(paragraphs) < 2:
        # Fall back to any non-empty paragraph when body detection is too strict.
        paragraphs = [p for p in container.find_all("p", recursive=True) if p.get_text(strip=True)]
    if len(paragraphs) < 2:
        return paragraphs[-1] if paragraphs else None

    lengths = [len(p.get_text(strip=True)) for p in paragraphs]

    # "After the fold" floor: the 2nd body paragraph (index 1).
    floor_idx = 1 if len(paragraphs) > 1 else 0

    # Top-third-by-volume ceiling: first body paragraph crossing 1/3 of total text.
    one_third = sum(lengths) / 3
    running = 0
    ceil_idx = len(paragraphs) - 1
    for i, length in enumerate(lengths):
        running += length
        if running >= one_third:
            ceil_idx = i
            break

    # Never deeper than the top third; otherwise sit just after the 2nd body paragraph.
    return paragraphs[min(floor_idx, ceil_idx)]


def build_embed_block(
    soup: BeautifulSoup,
    embed_origin: str,
    default_poll_id: str,
    locale: str = "",
) -> Tag:
    # When embed_origin is empty we want same-origin /embed.js, but the page's
    # injected <base href> would rewrite a bare "/embed.js" to the original
    # publisher's domain. Build the URL from location.origin at runtime so the
    # <base> can't capture it.
    embed_src_expr = (
        f"{embed_origin!r}+'/embed.js'" if embed_origin else "location.origin+'/embed.js'"
    )
    wrapper = soup.new_tag("div")
    wrapper["data-opinary-mockup"] = ""
    wrapper["style"] = "margin: 32px auto; max-width: 460px;"
    script = soup.new_tag("script")
    locale_line = f"s.setAttribute('data-locale',{locale!r});" if locale else ""
    script.string = (
        "(function(){"
        "var p=new URLSearchParams(location.search);"
        f"var id=p.get('id')||{default_poll_id!r};"
        "if(!id)return;"
        "var s=document.createElement('script');"
        f"s.src={embed_src_expr};"
        "s.setAttribute('data-poll-id',id);"
        f"{locale_line}"
        "document.currentScript.parentNode.insertBefore(s,document.currentScript);"
        "})();"
    )
    wrapper.append(script)
    return wrapper


def build_mockup(
    url: str,
    out_slug: str,
    default_poll_id: str = "",
    embed_origin: str = "",
    locale: str = "",
) -> Path:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise MockupBuildError(f"Couldn't fetch article: {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")

    head = soup.find("head")
    if head is not None and not head.find("base"):
        base = soup.new_tag("base", href=url)
        head.insert(0, base)

    strip_noise(soup)
    absolutize(soup, url)

    target = find_injection_point(soup)
    if target is None or len(soup.find_all("p")) < 3:
        raise MockupBuildError(
            "Article body has too few paragraphs — the URL is probably paywalled, "
            "JS-rendered, or an unsupported layout."
        )

    embed = build_embed_block(soup, embed_origin, default_poll_id, locale)
    target.insert_after(embed)

    MOCKS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MOCKS_DIR / f"{out_slug}.html"
    out_path.write_text(str(soup), encoding="utf-8")
    return out_path
