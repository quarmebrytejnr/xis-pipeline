"""
Credential loading — reads env vars set by .env, GitHub Actions secrets,
or values passed explicitly to the sync classes.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    raise EnvironmentError(
        f"Required environment variable '{key}' is not set. "
        f"Add it to your .env file or pass it directly to the sync class."
    )


def get_inflow_config(
    api_key: str | None = None,
    company_id: str | None = None,
) -> dict:
    return {
        "api_key": api_key or os.environ.get("INFLOW_API_KEY") or _require("INFLOW_API_KEY"),
        "company_id": company_id or os.environ.get("INFLOW_COMPANY_ID") or _require("INFLOW_COMPANY_ID"),
    }


def get_supabase_config(
    url: str | None = None,
    key: str | None = None,
) -> dict:
    return {
        "url": url or os.environ.get("SUPABASE_URL") or _require("SUPABASE_URL"),
        "key": key or os.environ.get("SUPABASE_KEY") or _require("SUPABASE_KEY"),
    }


def get_xero_config(
    client_id: str | None = None,
    client_secret: str | None = None,
    refresh_token: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    return {
        "client_id": client_id or os.environ.get("XERO_CLIENT_ID") or _require("XERO_CLIENT_ID"),
        "client_secret": client_secret or os.environ.get("XERO_CLIENT_SECRET") or _require("XERO_CLIENT_SECRET"),
        "refresh_token": refresh_token or os.environ.get("XERO_REFRESH_TOKEN") or _require("XERO_REFRESH_TOKEN"),
        "tenant_id": tenant_id or os.environ.get("XERO_TENANT_ID") or _require("XERO_TENANT_ID"),
    }
