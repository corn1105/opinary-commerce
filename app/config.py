import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

_required = {
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
}

_missing = [k for k, v in _required.items() if not v]
if _missing and ENVIRONMENT != "test":
    print(f"WARNING: missing env vars: {', '.join(_missing)}", file=sys.stderr)
