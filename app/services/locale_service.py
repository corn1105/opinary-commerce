from typing import Literal, Optional

Locale = Literal["de", "en"]


def parse_accept_language(header: Optional[str]) -> Locale:
    """Return 'de' if the top-quality language tag starts with 'de', else 'en'."""
    if not header:
        return "en"
    first = header.split(",")[0].strip().lower()
    tag = first.split(";")[0].strip()
    return "de" if tag.startswith("de") else "en"


def amazon_tld(locale: Locale) -> str:
    return "de" if locale == "de" else "com"
