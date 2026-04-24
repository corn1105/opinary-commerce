import json
from pathlib import Path
from typing import Optional

from anthropic import AsyncAnthropic

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.models import RecPayload

_client: Optional[AsyncAnthropic] = None
_prompt_cache: Optional[str] = None

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "recommendations_prompt.md"


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _get_system_prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = PROMPT_PATH.read_text(encoding="utf-8")
    return _prompt_cache


RECS_TOOL = {
    "name": "emit_recommendations",
    "description": "Emit the bridge sentence and product recommendations for this poll answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "bridge": {
                "type": "string",
                "description": "1-2 short sentences (~25 words max) bridging the user's answer to the products. Must name the voter's bracket/identity, give a fact/cost/peer-stat, and lead into the product count. No marketing fluff.",
            },
            "products": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Product name."},
                        "description": {"type": "string", "description": "2-3 line reason-to-care, terse."},
                        "query": {"type": "string", "description": "Amazon search keyword string (NOT a URL)."},
                        "badge": {
                            "type": "string",
                            "enum": ["TOP RATED", "MOST POPULAR", "BEST VALUE", "EDITOR'S PICK", "NEW RELEASE"],
                        },
                    },
                    "required": ["title", "description", "query", "badge"],
                },
            },
        },
        "required": ["bridge", "products"],
    },
}


async def generate_recommendations(
    question: str,
    option_label: str,
    context_notes: Optional[str],
    locale: str,
) -> RecPayload:
    """Generate bridge + 3 products for a (poll-question, option, locale) tuple."""
    user_content = (
        f"Poll question: {question}\n"
        f"User's answer: {option_label}\n"
        f"Admin context notes: {context_notes or '(none)'}\n"
        f"Locale: {locale} "
        f"(write bridge and product names in {'German' if locale == 'de' else 'English'})\n\n"
        "Emit exactly 3 products and a bridge sentence that says \"three\" (or the German equivalent "
        "\"drei\") to match."
    )

    resp = await _get_client().messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=_get_system_prompt(),
        tools=[RECS_TOOL],
        tool_choice={"type": "tool", "name": "emit_recommendations"},
        messages=[{"role": "user", "content": user_content}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_recommendations":
            payload = block.input if isinstance(block.input, dict) else json.loads(block.input)
            return RecPayload.model_validate(payload)

    raise RuntimeError("Claude did not return an emit_recommendations tool call")
