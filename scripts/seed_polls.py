"""Seed the 20 reference polls with their exact bridge sentences + curated products.

Each poll:
- Creates the poll + 4 options.
- Pre-seeds the (option, locale="en") recommendations row for ONE specific option
  with the user's exact bridge sentence and hand-picked products.
- Leaves the other 3 options un-seeded; they'll be Claude-generated on first vote.

Run from repo root:  venv/bin/python scripts/seed_polls.py
"""

import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/seed_polls.py` from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.poll_service import create_poll, upsert_recs  # noqa: E402


PRICES = {
    "Hoka Clifton 9": "$145", "Brooks Ghost 16": "$140", "Nike Pegasus 41": "$139",
    "Saatva Classic": "$1,495", "Tempur-Pedic ProAdapt": "$3,199",
    "Sony WH-1000XM5": "$328", "Bose QuietComfort Ultra": "$379",
    "Breville Barista Express": "$749", "De'Longhi La Specialista Arte Evo": "$899", "Lelit Anna PL41TEM": "$699",
    "Away The Carry-On": "$275", "Rimowa Essential Cabin": "$725", "Monos Carry-On Pro": "$395",
    "Herman Miller Aeron": "$1,795",
    "Ring Video Doorbell Pro 2": "$229", "Google Nest Doorbell (Battery)": "$179",
    "Victorinox Fibrox 8\" Chef": "$49", "Wüsthof Classic 8\" Chef": "$169", "MAC Mighty MTH-80": "$175",
    "iRobot Roomba j7+": "$549", "Roborock S8 Pro Ultra": "$1,099", "Eufy X10 Pro Omni": "$799",
    "Google Nest Learning Thermostat (4th gen)": "$279", "Ecobee Premium": "$249",
    "LG C4 OLED 65\"": "$1,796", "Sony Bravia X90L 65\"": "$1,498", "Hisense U8N 65\"": "$1,099",
    "Garmin Forerunner 265": "$449", "Coros Pace 3": "$229",
    "Weber Performer Deluxe": "$479", "Big Green Egg Large": "$1,149", "PK Grills Original PK300": "$399",
    "Ray-Ban Wayfarer Classic": "$171", "Warby Parker Haskell Sunglasses": "$95", "Knockaround Fort Knocks": "$28",
    "Kindle Paperwhite (12th gen)": "$159", "Kobo Libra Colour": "$219",
    "Coway Airmega AP-1512HH": "$229", "Dyson Purifier HP07": "$749", "Levoit Core 600S": "$299",
    "La Roche-Posay Anthelios UV Mune 400 SPF 50+": "$33", "EltaMD UV Clear SPF 46": "$41", "Supergoop! Unseen Sunscreen SPF 40": "$38",
    "Specialized Sirrus X 4.0": "$1,500", "Trek FX+ 2 Stagger E-Bike": "$2,499", "Canyon Grizl 7": "$1,999",
    "Orijen Original Dry Dog Food": "$99", "The Farmer's Dog": "$2/day",
    "Bowflex SelectTech 552 Adjustable Dumbbells": "$429", "TRX Home2 Suspension Trainer": "$200", "Concept2 RowErg": "$1,050",
}


POLLS = [
    {
        "question": "How many kilometres do you actually run in a typical week?",
        "options": ["0", "1–10", "10–25", "25+"],
        "context_notes": "Category: running shoes. Audience: hobby runners picking a daily trainer.",
        "seed_index": 2,
        "bridge": "You're in the consistent-runner bracket. Three shoes readers at your mileage replaced theirs with.",
        "products": [
            {"title": "Hoka Clifton 9", "description": "Plush 32 mm stack, kind to your legs across a steady weekly base.", "query": "Hoka Clifton 9 running shoes", "badge": "MOST POPULAR"},
            {"title": "Brooks Ghost 16", "description": "The reliable daily trainer consistent runners keep falling back on.", "query": "Brooks Ghost 16 running shoes", "badge": "TOP RATED"},
            {"title": "Nike Pegasus 41", "description": "ReactX foam gives more pop without losing the Pegasus durability.", "query": "Nike Pegasus 41 running shoes", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "How old is your current mattress?",
        "options": ["Under 3 years", "3–7 years", "7–10 years", "Over 10 years"],
        "context_notes": "Category: mattresses. Audience: adults replacing their current mattress.",
        "seed_index": 2,
        "bridge": "Past the refresh point. Two mattresses readers with yours picked next.",
        "products": [
            {"title": "Saatva Classic", "description": "Dual-coil luxury hybrid with three firmness options. The default upgrade past the 7-year mark.", "query": "Saatva Classic mattress", "badge": "TOP RATED"},
            {"title": "Tempur-Pedic ProAdapt", "description": "Dense memory foam that conforms without the sag older mattresses develop by year 10.", "query": "Tempur-Pedic ProAdapt mattress", "badge": "MOST POPULAR"},
        ],
    },
    {
        "question": "When did you last upgrade your headphones?",
        "options": ["This year", "1–3 years ago", "3–5 years ago", "I can't remember"],
        "context_notes": "Category: noise-cancelling over-ear headphones.",
        "seed_index": 2,
        "bridge": "Headphones have moved on more than phones since you bought yours. The two pairs most readers in your camp upgraded to.",
        "products": [
            {"title": "Sony WH-1000XM5", "description": "Industry-leading noise canceling. The gap vs 3-year-old sets is bigger than most phone upgrades.", "query": "Sony WH-1000XM5 headphones", "badge": "TOP RATED"},
            {"title": "Bose QuietComfort Ultra", "description": "Iconic comfort with improved spatial audio. The comfortable default for long flights and all-day calls.", "query": "Bose QuietComfort Ultra headphones", "badge": "MOST POPULAR"},
        ],
    },
    {
        "question": "Home coffee or café coffee?",
        "options": ["Home, basic", "Home, serious setup", "Café only", "Mix"],
        "context_notes": "Category: home espresso machines. Audience: café-only drinkers considering switching.",
        "seed_index": 2,
        "bridge": "That's roughly €1,400 a year. Three machines readers who made the switch swear by.",
        "products": [
            {"title": "Breville Barista Express", "description": "Built-in grinder, PID temp control. The €700 machine most café-switchers start with.", "query": "Breville Barista Express espresso machine", "badge": "MOST POPULAR"},
            {"title": "De'Longhi La Specialista Arte Evo", "description": "Manual grinder and cold brew option. Closer to café output than any bean-to-cup.", "query": "De'Longhi La Specialista Arte Evo", "badge": "BEST VALUE"},
            {"title": "Lelit Anna PL41TEM", "description": "Entry-level E61 workhorse. Punches above its price, loved by the r/espresso crowd.", "query": "Lelit Anna PL41TEM espresso machine", "badge": "EDITOR'S PICK"},
        ],
    },
    {
        "question": "Carry-on only, or do you check a bag?",
        "options": ["Always carry-on", "Always check", "Depends on trip length", "I overpack"],
        "context_notes": "Category: premium carry-on luggage.",
        "seed_index": 0,
        "bridge": "Carry-on loyalist. Three bags readers who fly like you keep going back to.",
        "products": [
            {"title": "Away The Carry-On", "description": "Unbreakable polycarbonate shell and a compression system. Dimensions optimized for most airlines.", "query": "Away The Carry-On luggage", "badge": "MOST POPULAR"},
            {"title": "Rimowa Essential Cabin", "description": "Aluminum build if you want one bag for life. Holds resale value like nothing else.", "query": "Rimowa Essential Cabin aluminium", "badge": "TOP RATED"},
            {"title": "Monos Carry-On Pro", "description": "Front laptop pocket and vegan leather details. The Away competitor for hybrid trips.", "query": "Monos Carry-On Pro", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "How's your back at the end of a work day?",
        "options": ["Fine", "Slightly stiff", "Actually hurts", "I barely sit"],
        "context_notes": "Category: ergonomic office chairs. Audience: knowledge workers with back pain.",
        "seed_index": 2,
        "bridge": "Before you book a physio, one chair most readers with the same complaint replaced theirs with.",
        "products": [
            {"title": "Herman Miller Aeron", "description": "The chair with the best long-term record for lower-back pain. Holds its resale and lasts 15+ years.", "query": "Herman Miller Aeron chair", "badge": "EDITOR'S PICK"},
        ],
    },
    {
        "question": "Have you ever had a package stolen from your porch?",
        "options": ["Never", "Once", "More than once", "It's a weekly thing in my area"],
        "context_notes": "Category: smart doorbells and front-door cameras.",
        "seed_index": 2,
        "bridge": "Porch-theft frustration is the top reason readers fit a doorbell cam. Two they picked.",
        "products": [
            {"title": "Ring Video Doorbell Pro 2", "description": "Best porch coverage with a 1:1 head-to-toe aspect ratio. Widest package-detection ecosystem.", "query": "Ring Video Doorbell Pro 2", "badge": "MOST POPULAR"},
            {"title": "Google Nest Doorbell (Battery)", "description": "No hub needed. Better face familiar-person detection if you're already in the Google ecosystem.", "query": "Google Nest Doorbell Battery", "badge": "TOP RATED"},
        ],
    },
    {
        "question": "How sharp is the chef's knife in your kitchen right now?",
        "options": ["Razor sharp", "OK", "Kind of dull", "I didn't know you were meant to sharpen them"],
        "context_notes": "Category: chef's knives.",
        "seed_index": 2,
        "bridge": "Same answer as 40% of readers. Three knives they replaced theirs with.",
        "products": [
            {"title": "Victorinox Fibrox 8\" Chef", "description": "Pro kitchens use it because it's under $50, sharpens easily, and takes abuse.", "query": "Victorinox Fibrox 8 inch chef knife", "badge": "BEST VALUE"},
            {"title": "Wüsthof Classic 8\" Chef", "description": "Full-tang German steel. The Wirecutter pick for a decade.", "query": "Wusthof Classic 8 inch chef knife", "badge": "TOP RATED"},
            {"title": "MAC Mighty MTH-80", "description": "Japanese hybrid, thinner edge, holds sharpness much longer than a German knife.", "query": "MAC Mighty MTH-80 knife", "badge": "EDITOR'S PICK"},
        ],
    },
    {
        "question": "How often do you actually vacuum?",
        "options": ["Weekly", "Monthly", "When I can't take it anymore", "I bought a robot"],
        "context_notes": "Category: robot vacuums.",
        "seed_index": 2,
        "bridge": "Readers in your camp bought their way out of it. Three that actually work on real floors.",
        "products": [
            {"title": "iRobot Roomba j7+", "description": "Avoids pet messes, empties itself. The reliability default.", "query": "iRobot Roomba j7+ robot vacuum", "badge": "MOST POPULAR"},
            {"title": "Roborock S8 Pro Ultra", "description": "Vacuums AND mops with hot water wash. The premium pick if you'd actually use mopping.", "query": "Roborock S8 Pro Ultra", "badge": "TOP RATED"},
            {"title": "Eufy X10 Pro Omni", "description": "Mid-tier price, auto-empty and auto-wash base, good obstacle avoidance.", "query": "Eufy X10 Pro Omni", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "When was your last energy bill shock moment?",
        "options": ["This winter", "Last summer", "Constantly", "Never"],
        "context_notes": "Category: smart thermostats.",
        "seed_index": 0,
        "bridge": "Smart thermostats typically pay back in two winters. Two most readers who reacted to a bill picked.",
        "products": [
            {"title": "Google Nest Learning Thermostat (4th gen)", "description": "Auto-schedules from your pattern. Pays back in two winters for most households.", "query": "Google Nest Learning Thermostat 4th generation", "badge": "MOST POPULAR"},
            {"title": "Ecobee Premium", "description": "Built-in air quality and room sensors for even heating. Apple HomeKit native.", "query": "Ecobee Premium smart thermostat", "badge": "TOP RATED"},
        ],
    },
    {
        "question": "What size is the TV in your living room right now?",
        "options": ["Under 43\"", "43–55\"", "55–65\"", "65\"+"],
        "context_notes": "Category: televisions. Audience at this bracket upgrades one size up on next buy.",
        "seed_index": 1,
        "bridge": "Most readers in your bracket upgrade one size up on their next buy. Three picks at the next tier.",
        "products": [
            {"title": "LG C4 OLED 65\"", "description": "Perfect black levels. The default size-up OLED for most living rooms.", "query": "LG C4 OLED 65 inch", "badge": "TOP RATED"},
            {"title": "Sony Bravia X90L 65\"", "description": "Mini-LED. Brightest of the mid-premium tier, best for sports and daytime rooms.", "query": "Sony Bravia X90L 65 inch", "badge": "MOST POPULAR"},
            {"title": "Hisense U8N 65\"", "description": "Mini-LED for hundreds less than Sony or Samsung. The value pick at the next size up.", "query": "Hisense U8N 65 inch", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "Are you training for something right now?",
        "options": ["5K", "Half marathon", "Full marathon or triathlon", "Nothing, just vibes"],
        "context_notes": "Category: GPS running/sports watches.",
        "seed_index": 1,
        "bridge": "Half-marathoners tend to ditch phone-based tracking around now. Two watches readers training at your level picked.",
        "products": [
            {"title": "Garmin Forerunner 265", "description": "AMOLED, training-readiness scores, 13-day battery. The default half-marathon watch.", "query": "Garmin Forerunner 265", "badge": "TOP RATED"},
            {"title": "Coros Pace 3", "description": "Under $250, 24-day battery, accurate GPS. What runners at your level buy instead of high-end Garmin.", "query": "Coros Pace 3 running watch", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "Gas, charcoal, or pellet grill?",
        "options": ["Gas", "Charcoal", "Pellet", "I don't grill"],
        "context_notes": "Category: charcoal grills and kamado cookers.",
        "seed_index": 1,
        "bridge": "Charcoal loyalists are a stubborn bunch. Three readers who stayed charcoal upgraded to these.",
        "products": [
            {"title": "Weber Performer Deluxe", "description": "Propane-assist ignition for charcoal. The upgrade most kettle loyalists make.", "query": "Weber Performer Deluxe charcoal grill", "badge": "MOST POPULAR"},
            {"title": "Big Green Egg Large", "description": "Ceramic kamado. Temperature stability a kettle can't match, and doubles as a smoker.", "query": "Big Green Egg Large", "badge": "EDITOR'S PICK"},
            {"title": "PK Grills Original PK300", "description": "Cast-aluminum classic with a lifetime warranty. Meathead at AmazingRibs swears by it.", "query": "PK Grills Original PK300", "badge": "TOP RATED"},
        ],
    },
    {
        "question": "How did you lose or break your last pair of sunglasses?",
        "options": ["Sat on them", "Left on a plane", "Lost at the beach", "I still have them"],
        "context_notes": "Category: affordable-to-mid-range sunglasses.",
        "seed_index": 1,
        "bridge": "Same story as a third of readers. Three pairs readers replaced theirs with, picked for not being devastating to lose again.",
        "products": [
            {"title": "Ray-Ban Wayfarer Classic", "description": "Cheap enough not to devastate when you leave them on a plane. Fits most faces.", "query": "Ray-Ban Wayfarer Classic sunglasses", "badge": "MOST POPULAR"},
            {"title": "Warby Parker Haskell Sunglasses", "description": "Under $100. Stylish enough to forgive yourself for losing them.", "query": "Warby Parker Haskell sunglasses", "badge": "EDITOR'S PICK"},
            {"title": "Knockaround Fort Knocks", "description": "Under $30 polarized. For when you know you'll lose them.", "query": "Knockaround Fort Knocks sunglasses", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "How many unread books are on your nightstand?",
        "options": ["0–2", "3–5", "6–10", "10+"],
        "context_notes": "Category: e-readers and audiobook services. Audience: readers with a growing unread pile.",
        "seed_index": 2,
        "bridge": "You're not short on books, you're short on reading time. Two tools readers in the same pile-up switched to.",
        "products": [
            {"title": "Kindle Paperwhite (12th gen)", "description": "Warmth-adjustable glare-free screen. 10-week battery. The reliable default.", "query": "Kindle Paperwhite 12th generation", "badge": "MOST POPULAR"},
            {"title": "Kobo Libra Colour", "description": "Physical page-turn buttons, color screen, and plays nicely with library books via OverDrive.", "query": "Kobo Libra Colour e-reader", "badge": "EDITOR'S PICK"},
        ],
    },
    {
        "question": "How's the air in your bedroom honestly?",
        "options": ["Fine", "Dusty", "Pollen hits me hard", "City air, I notice it"],
        "context_notes": "Category: HEPA air purifiers.",
        "seed_index": 2,
        "bridge": "You and one in three readers. Three purifiers allergy-bad bedrooms picked.",
        "products": [
            {"title": "Coway Airmega AP-1512HH", "description": "Wirecutter pick for years. True HEPA, quiet, covers 360 sq ft.", "query": "Coway Airmega AP-1512HH", "badge": "TOP RATED"},
            {"title": "Dyson Purifier HP07", "description": "Purifier and heater/fan in one. Real-time air quality readout.", "query": "Dyson Purifier HP07", "badge": "EDITOR'S PICK"},
            {"title": "Levoit Core 600S", "description": "Larger room coverage at a mid-tier price. Smart app, auto mode.", "query": "Levoit Core 600S air purifier", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "Do you wear SPF daily?",
        "options": ["Every day", "Only in summer", "Only on holiday", "Never"],
        "context_notes": "Category: daily-wear SPF for face.",
        "seed_index": 1,
        "bridge": "Dermatologists have been fighting this one for years. Three daily SPFs readers who converted actually stuck with.",
        "products": [
            {"title": "La Roche-Posay Anthelios UV Mune 400 SPF 50+", "description": "The dermatologist default. Doesn't pill under makeup.", "query": "La Roche-Posay Anthelios UV Mune 400 SPF 50", "badge": "TOP RATED"},
            {"title": "EltaMD UV Clear SPF 46", "description": "Niacinamide-added, acne-safe. The 'nothing else I'll wear' pick.", "query": "EltaMD UV Clear SPF 46", "badge": "MOST POPULAR"},
            {"title": "Supergoop! Unseen Sunscreen SPF 40", "description": "Invisible gel primer feel. The SPF people actually stick with daily.", "query": "Supergoop Unseen Sunscreen SPF 40", "badge": "EDITOR'S PICK"},
        ],
    },
    {
        "question": "When did you last replace your main bike?",
        "options": ["Past year", "2–5 years ago", "Over 5 years ago", "Still on my first one"],
        "context_notes": "Category: hybrid, gravel, and e-bikes. Audience: upgrading from an older hybrid.",
        "seed_index": 2,
        "bridge": "Disc brakes and e-assist took over in the last five years. Three bikes readers upgrading from yours picked.",
        "products": [
            {"title": "Specialized Sirrus X 4.0", "description": "Hydraulic disc brakes and a geometry that works for commuting and light gravel.", "query": "Specialized Sirrus X 4.0 bike", "badge": "TOP RATED"},
            {"title": "Trek FX+ 2 Stagger E-Bike", "description": "The first e-bike most people upgrading from a 10-year-old hybrid pick. Light enough to lift.", "query": "Trek FX+ 2 Stagger e-bike", "badge": "MOST POPULAR"},
            {"title": "Canyon Grizl 7", "description": "Direct-to-consumer pricing, gravel/commuter flex. Huge upgrade for the money vs a 5-year-old hybrid.", "query": "Canyon Grizl 7 gravel bike", "badge": "BEST VALUE"},
        ],
    },
    {
        "question": "What does your dog or cat actually eat?",
        "options": ["Supermarket kibble", "Premium dry", "Fresh", "Raw"],
        "context_notes": "Category: premium pet food.",
        "seed_index": 0,
        "bridge": "Same as 45% of readers. Two premium brands readers who made the switch landed on, and what they said after.",
        "products": [
            {"title": "Orijen Original Dry Dog Food", "description": "85% animal ingredients. The big step up from grocery kibble without needing a subscription.", "query": "Orijen Original dry dog food", "badge": "TOP RATED"},
            {"title": "The Farmer's Dog", "description": "Fresh-cooked, portioned, delivered. The service most supermarket-kibble switchers actually stuck with.", "query": "The Farmer's Dog fresh dog food", "badge": "MOST POPULAR"},
        ],
    },
    {
        "question": "Gym or home workouts?",
        "options": ["Gym only", "Home only", "Both", "Neither"],
        "context_notes": "Category: home workout equipment. Audience: people building a home setup from nothing.",
        "seed_index": 1,
        "bridge": "Home-only readers end up building a stack. Three pieces most of them started with.",
        "products": [
            {"title": "Bowflex SelectTech 552 Adjustable Dumbbells", "description": "5–52.5 lbs per hand in one pair. The usual first buy.", "query": "Bowflex SelectTech 552 adjustable dumbbells", "badge": "MOST POPULAR"},
            {"title": "TRX Home2 Suspension Trainer", "description": "Full-body bodyweight work. Takes up a doorframe, not a room.", "query": "TRX Home2 suspension trainer", "badge": "BEST VALUE"},
            {"title": "Concept2 RowErg", "description": "Indoor rowing's default. Holds value for 20+ years, fits under a bed.", "query": "Concept2 RowErg rower", "badge": "EDITOR'S PICK"},
        ],
    },
]


def _placeholder_image(name: str) -> str:
    import hashlib
    from urllib.parse import quote
    keywords = ",".join([w for w in name.lower().split() if len(w) > 3][:2]) or "product"
    seed = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"https://loremflickr.com/400/300/{quote(keywords)}?lock={seed}"


def _apply_prices(products: list[dict]) -> list[dict]:
    return [
        {
            **p,
            "price": p.get("price") or PRICES.get(p["title"]),
            "image_url": p.get("image_url") or _placeholder_image(p["title"]),
        }
        for p in products
    ]


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--wipe", action="store_true", help="Delete all existing polls before seeding")
    args = parser.parse_args()

    from app.services.poll_service import get_db
    db = get_db()

    if args.wipe:
        existing = db.table("polls").select("id").execute().data or []
        for p in existing:
            db.table("polls").delete().eq("id", p["id"]).execute()
        print(f"Wiped {len(existing)} existing polls.")

    print(f"Seeding {len(POLLS)} polls...")
    for i, entry in enumerate(POLLS, 1):
        poll = await create_poll(
            question=entry["question"],
            options=[{"label": o} for o in entry["options"]],
            context_notes=entry.get("context_notes"),
            publisher_name=None,
            publisher_logo=None,
        )
        seeded_option = poll["options"][entry["seed_index"]]
        products_with_prices = _apply_prices(entry["products"])
        await upsert_recs(
            option_id=seeded_option["id"],
            locale="en",
            bridge=entry["bridge"],
            products=products_with_prices,
        )
        print(f"  [{i:2d}/20] {entry['question'][:60]}{'…' if len(entry['question']) > 60 else ''}")
        print(f"          seeded option: {seeded_option['label']!r} with {len(products_with_prices)} product(s)")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
