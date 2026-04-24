# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

OpinaryCommerce — an embeddable poll widget for publishers. A reader sees a question in an article, votes, gets results with their choice highlighted, and sees 3 AI-generated Amazon product recommendations bridged by a single short sentence that connects their answer to *why they should care* about the products.

The **bridge sentence** is the core of the product. Everything else (bars, cards, Amazon links) is commodity; the bridge is the thing that turns a poll vote into a click.

Deployed to Railway, single FastAPI process (`uvicorn app.main:app`). Supabase Postgres for storage.

## Commands

```bash
# Install (use a local venv in this repo)
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Run locally
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# DB
python scripts/setup_db.py                # print SETUP_SQL
python scripts/setup_db.py --exec         # apply SETUP_SQL
python scripts/setup_db.py --sql "..."    # ad-hoc
```

No tests, no linter, no formatter. If you add any, document them here.

## Required env vars (`.env`)

```
ANTHROPIC_API_KEY
ANTHROPIC_MODEL          # defaults to claude-sonnet-4-6
SUPABASE_URL
SUPABASE_SERVICE_KEY     # service_role key; bypasses RLS
ADMIN_PASSWORD
DATABASE_URL             # pooler URL; used ONLY by scripts/setup_db.py
ENVIRONMENT              # optional
```

## Architecture

### Runtime shape

```
publisher page <--script-- /embed.js  --injects--> <iframe src=/widget/{id}>
                                                         |
                                                         v
                        FastAPI   ---->   Claude (recommendations)
                           |
                           +---->   Supabase (polls/options/votes/recommendations)

admin ---(cookie auth)---> /admin/* (poll CRUD, rec preview/regen/bridge edit)
```

### Key files

- `app/main.py` — FastAPI entry. CORS wide-open. Mounts public + admin routers.
- `app/routes/public.py` — `/widget/{id}`, `/embed.js`, `/api/polls/{id}`, `/api/polls/{id}/vote`, `/api/polls/{id}/results`.
- `app/routes/admin.py` — `/admin/*` with cookie-auth. Poll CRUD + rec endpoints.
- `app/services/poll_service.py` — all Supabase reads/writes. Don't call `get_db().table(...)` from routers.
- `app/services/claude_service.py` — single `generate_recommendations()` function using forced `tool_use`.
- `app/services/locale_service.py` — `Accept-Language` → `"de"|"en"`, and Amazon TLD mapping.
- `app/prompts/recommendations_prompt.md` — **the single highest-leverage file in the repo.** The 20 few-shot bridge examples live here. Edit carefully. Reloaded from disk on process restart.
- `app/static/widget.html` — iframe contents. Single file, vanilla JS. Renders vote UI → results + recs UI. Posts `opinary-height` to parent for iframe resize.
- `app/static/embed.js` — one-line publisher snippet. Reads `data-poll-id`, injects iframe, listens for height messages.
- `app/static/admin.html` — admin SPA. Sections: login, polls list, poll editor, recs panel.
- `app/static/demo.html` — dev-only test page that embeds a widget at `/demo.html`. Stores the poll ID in localStorage.
- `scripts/setup_db.py` — schema + migration runner (direct psycopg2).

### Data model

Four tables, **RLS enabled with no policies** (backend uses `SUPABASE_SERVICE_KEY`, anon clients can't read anything):

- `polls` — question, context_notes, publisher_name, publisher_logo, status (`active|archived`).
- `poll_options` — label, sort_order, FK to polls. Cascade delete.
- `votes` — one row per vote, append-only. No dedup.
- `recommendations` — `(option_id, locale)` unique. Stores **bridge** (text) + **products** (jsonb: `[{title, description, query, badge}]`). `generated_at` instead of `created_at/updated_at`.

**Trigger note:** the `update_updated_at()` trigger is attached to `polls` only. Votes and recommendations are append-only / have `generated_at` — do NOT attach the trigger to them (it references `NEW.updated_at` and will fail every UPDATE against tables without that column).

### Recommendations caching

- Cached per `(option_id, locale)`. First voter on a (option, locale) pair triggers Claude; result is upserted and serves all subsequent voters picking the same option in that locale.
- Two potential cache rows per option (`en`, `de`). No auto-expiry — admin must manually regenerate from the admin UI.
- The cached row stores Claude's raw output (`query` field stays as keywords). The Amazon URL is built at render time in `_build_amazon_url()` in `public.py`, so switching locales/TLDs doesn't invalidate the cache.

### The bridge — treat as product-critical

The bridge sentence is not decoration. Rules enforced by `app/prompts/recommendations_prompt.md`:

1. Name the voter's identity/bracket.
2. Give a fact, cost, peer-stat, or market-shift that makes the status quo feel suboptimal.
3. Lead into the product count ("three …") to match the 3 products returned.
4. Max 2 sentences, ~25 words.
5. Never generic marketing-speak.

The 20 few-shot examples (headphones, mattress, espresso machine, etc.) live in the prompt file. **If you're tempted to "clean up" or "shorten" the examples, don't — they're the voice.** Adding more examples is fine; removing them degrades output.

When a bridge looks bad in production:
- Prefer **editing it inline in the admin UI** (saves to `recommendations.bridge`, products untouched).
- Use **Regenerate** only if the products are also off.

### Admin auth

Same pattern as MiGreat. `ADMIN_PASSWORD` compared via `hmac.compare_digest`, stored verbatim as `admin_token` cookie (httpOnly, samesite=strict, 24h). Every `/admin/api/*` route re-checks. Fine for a one-operator tool.

### Embed & CORS

- `/widget/{id}` response sets `Content-Security-Policy: frame-ancestors *` so publishers can iframe it from any origin.
- `allow_origins=["*"]` on CORS — public endpoints are meant to be hit from the iframe on any host.
- Admin endpoints rely on cookie auth + same-origin browsing; the wide CORS does not expose them because the cookie is `samesite=strict`.
- Iframe auto-resize: widget posts `{type: "opinary-height", height: N}` to parent; `embed.js` listens and updates `iframe.style.height`.

## Conventions

- All Supabase access through `app/services/poll_service.py`.
- All Claude calls through `app/services/claude_service.py`.
- Ad-hoc DB migrations via `python scripts/setup_db.py --sql "..."`. Don't paste SQL into the Supabase dashboard.
- Static HTML files are single-file, vanilla JS. No build step, no framework.
- `app/prompts/recommendations_prompt.md` is loaded from disk and **cached in-process** on first use — restart the server to pick up edits.

## Known gaps / gotchas

- **No vote dedup.** A refresh = a new vote. This is by design for MVP; raw counts are not a commit. If you want dedup later: cookie-based is easiest, IP-hash is sturdier.
- **Prices are not generated.** The mockup shows `$328.00 LOWEST` pills; we intentionally don't render them because Claude can't know real prices and we don't scrape Amazon. The CTA says "See on Amazon" only. Adding live prices = Amazon Product Advertising API = a separate project.
- **Option edits nuke votes.** `update_poll` with new `options` array deletes all existing rows (cascading votes/recs) and re-inserts. Only safe before a poll goes live. If we ever need in-flight option edits, switch to label-only UPDATEs keyed by `id`.
- **Bridge regeneration regenerates products too.** They're a single Claude call. Editing just the bridge uses the PATCH endpoint and leaves products alone.
- **Locale is naive.** `parse_accept_language` just looks at the top tag. Good enough for `.de` vs `.com`; don't trust it for finer-grained routing.
