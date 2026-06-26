"""
Re-inject the poll widget into already-generated mockups, in place.

Existing mockups in MOCKS_DIR have the widget baked in at whatever position the
placement logic used when they were built. This script moves the widget to the
current placement (see find_injection_point) WITHOUT re-fetching the source
article — the saved HTML is already cleaned and asset-absolutized, so re-fetching
would risk bot-blocks and content drift.

Usage:
    python scripts/reinject_mocks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from app.services.mockup_service import MOCKS_DIR, find_injection_point  # noqa: E402


def reinject(path: Path) -> bool:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

    wrapper = soup.find(attrs={"data-opinary-mockup": True})
    if wrapper is None:
        print(f"skip  {path.name}: no widget found")
        return False

    # Pull the widget out so it doesn't skew paragraph counting, then re-place it.
    wrapper.extract()
    target = find_injection_point(soup)
    if target is None:
        print(f"skip  {path.name}: no injection point")
        return False

    target.insert_after(wrapper)
    path.write_text(str(soup), encoding="utf-8")
    print(f"wrote {path.name}")
    return True


def main() -> None:
    files = sorted(MOCKS_DIR.glob("*.html"))
    if not files:
        sys.exit(f"no mockups found in {MOCKS_DIR}")
    count = sum(reinject(p) for p in files)
    print(f"\nre-injected {count}/{len(files)} mockups")


if __name__ == "__main__":
    main()
