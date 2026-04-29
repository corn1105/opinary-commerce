"""
Translate every poll's question + option labels into German via Claude, and
write the result into the `translations` JSONB columns on `polls` and
`poll_options`.

Schema written:
    polls.translations         = {"de": {"question": "..."}}
    poll_options.translations  = {"de": {"label": "..."}}

The widget + admin dashboard read these when locale=de and fall back to the
original English when missing.

Usage:
    venv/bin/python scripts/translate_polls.py            # translate all polls
    venv/bin/python scripts/translate_polls.py --force    # re-translate even if 'de' translation exists
    venv/bin/python scripts/translate_polls.py --dry-run  # print only, don't write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anthropic import AsyncAnthropic  # noqa: E402

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL  # noqa: E402
from app.services.poll_service import get_db, _cache_bust  # noqa: E402

LOCALE = "de"

TRANSLATE_TOOL = {
    "name": "emit_translation",
    "description": "Emit the German translation of a poll question and its options.",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural-sounding German translation of the poll question. Match the conversational tone of the original. Use the formal Sie form. Keep it short.",
            },
            "options": {
                "type": "array",
                "description": "German translations of the poll options, in the SAME ORDER as the input. Length must match exactly.",
                "items": {"type": "string"},
            },
        },
        "required": ["question", "options"],
    },
}

SYSTEM_PROMPT = """You are a senior editor at a German quality publication writing
reader-poll questions. Reference voice: ZEIT Magazin, Süddeutsche
Magazin, SPIEGEL "Lebensart" — concise, observed, slightly dry, never
patronising. The English on input is briefing material, not a script. Your
job is to write the German version that should appear in print.

Native readers must not be able to tell this came from English.

VOICE
- Formal Sie form throughout. Capitalize Sie / Ihr / Ihnen. Verbs in
  third-person plural ("laufen Sie", "greifen Sie"). Possessives:
  "Ihr Kochmesser", "Ihrem Rücken". Never mix in du / dein.
- Editorial register: courteous, observed, mildly knowing. Not advertising.
  Not survey-bureaucratic. Not chatty.
- Short. A good reader-poll question is 4–9 words. Cut every word that
  doesn't earn its place.

WORDS TO CUT (filler that creeps in from English)
- "aktuell", "aktuelle", "derzeit", "zurzeit", "momentan", "gerade"
  Almost always droppable. "Wie alt ist Ihre Matratze?" beats
  "Wie alt ist Ihre aktuelle Matratze?".
- "wirklich", "tatsächlich", "eigentlich" — keep ONE of these per
  question if the English emphasised it ("actually", "really"). Otherwise
  drop. Don't double up.
- "Bestimmtes" / "etwas Bestimmtes" — almost always overkill.
- Trailing prepositional phrases that just restate the obvious
  ("in Ihrem Wohnzimmer", "in Ihrer Küche") — keep only if it adds
  information.

GERMAN VOCABULARY (specific traps)
- "energy bill" → "Stromrechnung". Not "Energierechnung" (clinical /
  bureaucratic, no native says this).
- "main bike" → "Ihr Rad" or "Ihr wichtigstes Rad". Never "Hauptfahrrad".
- "broke" / "broken" (sunglasses, etc.) → "zerbrochen" or "zerstört".
  Not "kaputt gemacht" (kindergarten register for adult magazine).
- "upgrade" (consumer gear) → "ersetzt" or rephrase "Wann haben Sie
  zuletzt neue X gekauft?". Never "aufgerüstet".
- "vacuum" (the verb) → "saugen". Not "Staub saugen" in compact questions.
- "check a bag" → "einen Koffer aufgeben". Always include "einen Koffer";
  "Ich gebe auf" reads as 'I give up'.
- "greifen" needs "zu": "Zu welchem LSF greifen Sie…", never
  "Welchen LSF greifen Sie…".
- SPF → in product CONTEXT (a creme, a sunscreen) say
  "Sonnenschutz" or "Sonnencreme mit LSF". A bare "LSF" alone is just a
  number. So:
    "Do you wear SPF daily?"     → "Cremen Sie sich täglich mit
                                    Sonnenschutz ein?"  (NOT
                                    "Tragen Sie täglich LSF auf?")
    "Which SPF do you reach for?"→ "Zu welchem Lichtschutzfaktor greifen
                                    Sie normalerweise?"
- "honestly" at end of question → "ehrlich gesagt" or just drop.
- "shock moment" / "shocked" → "Wann hat Sie X zuletzt geschockt?" reads
  better than "Wann hatten Sie zuletzt einen Schreckmoment bei X?".
- "in a typical week" → "pro Woche". Not "in einer typischen Woche".

GERMAN IDIOMS (replace English idioms with native equivalents)
    "X hits me hard"          → "X macht mir zu schaffen"
    "vibes" / "just vibes"    → "einfach so" or "ohne Plan"
    "kind of dull"            → "eher stumpf"
    "I overpack"              → "Ich nehme immer zu viel mit"
    "sat on them"             → "Draufgesetzt"
    "barely sit"              → "Ich sitze kaum"

CONVENTIONS TO PRESERVE
- Brand names, product names, units: as-is (Sony, Nike, BARF).
- Numeric ranges with en/em dash ("1–10", "25+", "65\""): identical.
- Quotes: German „…" only if the English uses quotes.
- Match input punctuation: question mark stays, periods stay. Commas
  placed naturally for German.

WORKFLOW (per item — do this MENTALLY, then output)
1. Read the English. Understand what is being asked.
2. Draft a German version — natural, idiomatic, Sie form.
3. SELF-EDIT pass: Cut every word that doesn't add meaning. Check for
   the "WORDS TO CUT" list. Check the "GERMAN VOCABULARY" traps.
   Read the result aloud — does it sound like a ZEIT/SZ headline-style
   question? If it sounds like a translation, rewrite.
4. Options: each one should be a thing a German person would actually
   say. Single phrases, not full sentences unless the English is a full
   sentence. Same length-discipline as the question.

The options array MUST be in the same order and same length as the input."""


async def translate(client: AsyncAnthropic, question: str, options: list[str]) -> dict:
    user = (
        f"Poll question: {question}\n"
        f"Options ({len(options)}):\n"
        + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
        + "\n\nReturn the German translations. The options array must be in the same order and have the same length as the input."
    )
    resp = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        tools=[TRANSLATE_TOOL],
        tool_choice={"type": "tool", "name": "emit_translation"},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_translation":
            data = block.input if isinstance(block.input, dict) else json.loads(block.input)
            if len(data["options"]) != len(options):
                raise RuntimeError(
                    f"option count mismatch: got {len(data['options'])}, expected {len(options)}"
                )
            return data
    raise RuntimeError("Claude did not return emit_translation")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-translate even if a 'de' translation exists")
    parser.add_argument("--dry-run", action="store_true", help="Print, don't write")
    parser.add_argument("--only", help="Filter to one poll by question substring (case-insensitive)")
    args = parser.parse_args()

    db = get_db()
    polls = db.table("polls").select("*").order("created_at").execute().data or []
    if args.only:
        needle = args.only.lower()
        polls = [p for p in polls if needle in p["question"].lower()]
    print(f"Found {len(polls)} polls")

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    for p in polls:
        existing_de = (p.get("translations") or {}).get(LOCALE, {}).get("question")
        opts = (
            db.table("poll_options")
            .select("*")
            .eq("poll_id", p["id"])
            .order("sort_order")
            .execute()
            .data
            or []
        )
        opt_labels = [o["label"] for o in opts]

        if existing_de and not args.force:
            print(f"\n• {p['question']!r}")
            print(f"    ✓ already translated ({existing_de!r}) — skipping (use --force to redo)")
            continue

        print(f"\n• {p['question']!r}")
        try:
            result = await translate(client, p["question"], opt_labels)
        except Exception as e:
            print(f"    ✗ translation failed: {e}")
            continue

        print(f"    Q: {result['question']!r}")
        for orig, trans in zip(opt_labels, result["options"]):
            print(f"      {orig!r}  →  {trans!r}")

        if args.dry_run:
            continue

        # Merge into existing translations dict so we don't clobber other locales.
        new_poll_translations = {**(p.get("translations") or {}), LOCALE: {"question": result["question"]}}
        db.table("polls").update({"translations": new_poll_translations}).eq("id", p["id"]).execute()
        _cache_bust(p["id"])

        for opt, trans in zip(opts, result["options"]):
            new_opt_translations = {**(opt.get("translations") or {}), LOCALE: {"label": trans}}
            db.table("poll_options").update({"translations": new_opt_translations}).eq("id", opt["id"]).execute()


if __name__ == "__main__":
    asyncio.run(main())
