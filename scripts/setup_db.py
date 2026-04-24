"""
Database setup script for OpinaryCommerce.

Connects directly to Postgres via DATABASE_URL (psycopg2) and runs schema SQL
or ad-hoc migrations.

Usage:
    python scripts/setup_db.py                # Print SETUP_SQL only (no DB contact)
    python scripts/setup_db.py --exec         # Apply SETUP_SQL to the DB
    python scripts/setup_db.py --sql "..."    # Run arbitrary SQL (one transaction)
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


SETUP_SQL = """
-- ============================================
-- OpinaryCommerce — Database Schema
-- ============================================

CREATE TABLE IF NOT EXISTS polls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    context_notes TEXT,
    publisher_name TEXT,
    publisher_logo TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS poll_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    poll_id UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_poll_options_poll_id ON poll_options(poll_id);

CREATE TABLE IF NOT EXISTS votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    poll_id UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    option_id UUID NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
    locale TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_votes_poll_id ON votes(poll_id);
CREATE INDEX IF NOT EXISTS idx_votes_option_id ON votes(option_id);

CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    option_id UUID NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
    locale TEXT NOT NULL,
    bridge TEXT NOT NULL,
    products JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (option_id, locale)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_option_id ON recommendations(option_id);

-- RLS lockdown: enable RLS with no policies so anon/authenticated REST clients
-- cannot read anything. Backend uses SUPABASE_SERVICE_KEY which bypasses RLS.
ALTER TABLE polls            ENABLE ROW LEVEL SECURITY;
ALTER TABLE poll_options     ENABLE ROW LEVEL SECURITY;
ALTER TABLE votes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations  ENABLE ROW LEVEL SECURITY;

-- Auto-update updated_at trigger (polls only — other tables are append-only
-- or have generated_at instead of updated_at).
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS polls_updated_at ON polls;
CREATE TRIGGER polls_updated_at
    BEFORE UPDATE ON polls
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
"""


def _build_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit(
            "ERROR: DATABASE_URL is not set. Add it to .env:\n"
            "  DATABASE_URL=postgresql://postgres:<password>@<host>:5432/postgres"
        )
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


def run_sql(sql: str) -> None:
    import psycopg2

    dsn = _build_dsn()
    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.OperationalError as e:
        sys.exit(
            f"ERROR connecting to Postgres: {e}\n"
            "If this is a network error, Supabase's direct connection "
            "(db.<ref>.supabase.co:5432) may be IPv6-only. Try the pooler URL."
        )

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        print("OK")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="OpinaryCommerce DB setup / migration runner.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--exec", action="store_true", dest="exec_", help="Apply SETUP_SQL to the DB.")
    group.add_argument("--sql", type=str, help="Run arbitrary SQL against the DB (single transaction).")
    args = parser.parse_args()

    if args.exec_:
        print("Applying SETUP_SQL via direct Postgres connection...")
        run_sql(SETUP_SQL)
        return

    if args.sql:
        print("Running ad-hoc SQL via direct Postgres connection...")
        run_sql(args.sql)
        return

    print("=" * 60)
    print("OpinaryCommerce — Database Setup SQL")
    print("=" * 60)
    print(SETUP_SQL)
    print("To execute, run: python scripts/setup_db.py --exec")


if __name__ == "__main__":
    main()
