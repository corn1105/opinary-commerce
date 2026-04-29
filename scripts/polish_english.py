"""
Editorially polish the English source text for every poll: rewrites
`polls.question` and `poll_options.label` in place so they read like a
quality reader-poll desk wrote them — concise, observed, no filler.

This is destructive of the original wording but safe for relations:
recommendations and votes link by option_id (UUID), not label text.

Usage:
    venv/bin/python scripts/polish_english.py            # polish all polls (skips already-polished, see --force)
    venv/bin/python scripts/polish_english.py --force    # repolish even if marked done
    venv/bin/python scripts/polish_english.py --dry-run  # show diffs only, don't write
    venv/bin/python scripts/polish_english.py --only "kilometre"  # filter to one poll

Idempotency: a poll's `polls.translations.en._polished = true` flag is set
after a successful write, so re-runs without --force skip it.

Caveat: if you re-run scripts/import_recommendations_csv.py after polishing,
polls won't match the CSV's English questions and you'll get duplicate poll
rows. Re-import BEFORE polishing, not after.
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

POLISH_TOOL = {
    "name": "emit_polished",
    "description": "Emit the editorially polished English question and options.",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Polished English poll question. Cut filler. Same meaning, fewer words.",
            },
            "options": {
                "type": "array",
                "description": "Polished English option labels in the SAME ORDER as input. Length must match exactly.",
                "items": {"type": "string"},
            },
        },
        "required": ["question", "options"],
    },
}

SYSTEM_PROMPT = """You are a senior reader-poll editor at a quality magazine
(reference voice: The Atlantic, FT Weekend, NYT Magazine, The Guardian
Saturday). You're polishing English poll questions and answer options that
were drafted by someone less experienced. Your job is to keep the meaning
and conversational warmth intact, but cut filler, sharpen verbs, and make
each line read like a magazine.

VOICE
- Conversational, observed, second-person ("you" / "your"), present tense.
- Trust the reader. No hand-holding clauses.
- A good poll question is 4–9 words. A good option is 1–6 words.
- Sentence-case, single question mark, no exclamation marks unless the
  original used them.

WORDS TO CUT (almost always)
- "right now", "currently", "actually", "really", "ever", "typically"
  These add nothing. "How sharp is your chef's knife?" beats "How sharp is
  the chef's knife in your kitchen right now?". Keep ONE softener
  ("actually") only if removing it changes the social meaning of the
  question (e.g. it's pointing out a discrepancy between belief and
  behaviour).
- "current" / "current X" — usually the only X they have. Drop.
- "in a typical week / month / day" — drop. "How many km do you run a
  week?" not "...in a typical week?".
- Trailing "in your X" if X is obvious from context: "in your living
  room", "in your kitchen", "on your nightstand" — keep ONLY if it adds
  information or rhythm. "How big is your TV?" beats "What size is the TV
  in your living room right now?".
- "do you" pile-ups ("How often do you actually X?") — usually one verb
  is enough.

PHRASING UPGRADES (sharpen verbs and tighten clauses)
- "When was your last X shock moment?" → "When did X last shock you?"
- "What size is the X?" → "How big is your X?"
- "How did you lose or break your last pair of X?" → "How did your last
  pair of X die?" or "How did you last break or lose your X?" depending
  on tone — keep the macabre humour if the original has it.
- "How's the air in your bedroom honestly?" — keep the "honestly", that's
  the joke. Maybe "Honestly, how's the air in your bedroom?" reads better.
- "Are you training for something right now?" → "Are you training for
  something?"

PRESERVE
- Brand names, units, numeric ranges with em/en dash ("1–10", "65\"+"),
  product nouns (SPF, BARF) — exact characters.
- The original tone: if a question is dry/witty, keep it dry/witty. If it's
  earnest, keep it earnest. Don't punch up earnest questions into jokes.
- The semantic intent. If the original asks "have you EVER", don't quietly
  drop "ever" if it changes whether the question is one-off or recurring.
  But for casual reader polls, "ever" is often droppable.
- The casing of options. If options are sentence-case, keep them sentence
  case. If Title Case, keep Title Case. Don't quietly switch styles.

HARD CONSTRAINTS (these come up repeatedly — do not violate)
- The output MUST NOT be LONGER than the input. If your polished version
  has more words than the original, you've gone backwards. The whole
  point is editing down, not rewriting longer. Same word count or fewer.
  Per item — for the question and for EACH option independently.
- Do NOT generalise away specificity. If the question names "dog or cat"
  the joke is the breadth — collapsing to "pet" loses character. Keep
  named entities (dog, cat, headphones, mattress, bike, knife) — never
  swap to a generic.
- Do NOT presuppose a state that one of the options denies. Before you
  rewrite a question, scan the options. If an option is "I still have
  them", the question can't ask "how did your X die", "how did your X
  meet their end", "how did you break your X" — anything that asserts
  loss/breakage contradicts "still have them". This applies to ANY
  rewording that asserts a state, no matter how witty. Concrete:
    Q: "How did you lose or break your last pair of sunglasses?"
    Options: "Sat on them" / "Left on a plane" / "Lost at the beach"
             / "I still have them"
    BAD polish: "How did your last pair of sunglasses die?"
    BAD polish: "How did your last pair of sunglasses meet their end?"
    OK: leave the question unchanged. The original "lose or break"
        already covers both states neutrally.
- Do NOT delete distinguishing modifiers in options. "Home, basic" is
  distinct from "Home, serious setup" — keep "basic". Don't replace
  short punchy answers ("Mix") with longer ones ("Mix of both"). Don't
  add explanatory clauses ("I overpack" → "I overpack — always check") —
  the original is the answer.
- Do NOT replace a specific question with a generic one. "Gym or home
  workouts?" is more specific and inviting than "Where do you work out?".
  The original framing IS the editorial choice; don't flatten it.

WORKFLOW (do mentally, then output)
1. Read the question and options. Understand the social context — what is
   the reader actually being asked?
2. Draft a polished version. Cut every word that doesn't add meaning or
   rhythm.
3. Self-edit: re-read aloud. Does it sound like a magazine, or like a
   survey? If survey, rewrite.
4. For options: each one should be the natural shortest answer a person
   would give. Not "Yes, every day" → just "Every day".

The options array MUST be in the same order and same length as the input."""


async def polish(client: AsyncAnthropic, question: str, options: list[str]) -> dict:
    user = (
        f"Poll question: {question}\n"
        f"Options ({len(options)}):\n"
        + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(options))
        + "\n\nReturn the polished English. Same order, same length for options."
    )
    resp = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        tools=[POLISH_TOOL],
        tool_choice={"type": "tool", "name": "emit_polished"},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_polished":
            data = block.input if isinstance(block.input, dict) else json.loads(block.input)
            if len(data["options"]) != len(options):
                raise RuntimeError(
                    f"option count mismatch: got {len(data['options'])}, expected {len(options)}"
                )
            return data
    raise RuntimeError("Claude did not return emit_polished")


def diff_line(prefix: str, before: str, after: str) -> str:
    if before == after:
        return f"    {prefix} (unchanged): {before!r}"
    return f"    {prefix}\n        before: {before!r}\n        after:  {after!r}"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-polish even if already marked _polished")
    parser.add_argument("--dry-run", action="store_true", help="Print diffs, don't write")
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
        translations = p.get("translations") or {}
        already_polished = translations.get("en", {}).get("_polished") is True
        if already_polished and not args.force:
            print(f"\n• {p['question']!r}")
            print(f"    ✓ already polished — skipping (use --force to redo)")
            continue

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

        print(f"\n• {p['question']!r}")
        try:
            result = await polish(client, p["question"], opt_labels)
        except Exception as e:
            print(f"    ✗ polish failed: {e}")
            continue

        print(diff_line("Q:", p["question"], result["question"]))
        for orig_opt, orig, after in zip(opts, opt_labels, result["options"]):
            print(diff_line(f"  {orig_opt['sort_order']}.", orig, after))

        if args.dry_run:
            continue

        # Update poll question + flag.
        new_translations = {**translations, "en": {**translations.get("en", {}), "_polished": True}}
        db.table("polls").update({
            "question": result["question"],
            "translations": new_translations,
        }).eq("id", p["id"]).execute()
        _cache_bust(p["id"])

        # Update each option label by id.
        for opt, after in zip(opts, result["options"]):
            if opt["label"] == after:
                continue
            db.table("poll_options").update({"label": after}).eq("id", opt["id"]).execute()


if __name__ == "__main__":
    asyncio.run(main())
