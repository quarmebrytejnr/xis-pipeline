"""
SupabaseClient — thin wrapper around the Supabase Python SDK that exposes
typed helpers for every table used by the xis-pipeline.

You rarely need this directly — InflowSync and XeroSync use it internally.
It is exposed publicly for custom integrations or one-off queries.

    from xis import SupabaseClient

    db = SupabaseClient()               # reads SUPABASE_URL / SUPABASE_KEY
    stats = db.get_sync_stats()
    print(stats)
"""
from datetime import datetime, timedelta
from typing import Any

try:
    from supabase import create_client, Client
except ImportError as e:
    raise ImportError("Install the supabase package: pip install supabase") from e

from xis._config import get_supabase_config


class SupabaseClient:
    """
    Low-level Supabase helper for all xis-pipeline tables.

    Parameters
    ----------
    url, key
        Supabase project URL and service-role key.
        Fall back to SUPABASE_URL / SUPABASE_KEY env vars.
    """

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        cfg = get_supabase_config(url, key)
        self._client: Client = create_client(cfg["url"], cfg["key"])

    # ── Xero tables ───────────────────────────────────────────────────────────

    def upsert_accounts(self, accounts: list[dict]) -> int:
        return self._upsert("d_x_accounts", accounts, "AccountID")

    def upsert_contacts(self, contacts: list[dict]) -> int:
        return self._upsert("d_x_contacts", contacts, "ContactID")

    def upsert_pnl_records(self, records: list[dict]) -> int:
        db_records = []
        for r in records:
            amount_str = r.get("value_1", "0") or "0"
            try:
                amount_str = "".join(c for c in str(amount_str) if c.isdigit() or c in ".-")
                amount = float(amount_str) if amount_str and amount_str != "-" else 0.0
            except (ValueError, TypeError):
                amount = 0.0

            report_date = r.get("report_date", "")
            section = r.get("section", "")
            sub_section = r.get("sub_section", "")
            account = r.get("account", "")
            db_records.append({
                "ReportDate": report_date,
                "Section": section,
                "SubSection": sub_section,
                "RowType": r.get("row_type", ""),
                "Account": account,
                "AccountID": r.get("account_id", ""),
                "Column_1": str(amount),
                "unique_key": f"{report_date}|{section}|{sub_section}|{account}",
            })
        return self._upsert("f_x_pnl", db_records, "unique_key")

    def get_existing_pnl_dates(self) -> set[str]:
        """Return the set of ReportDate values already in Supabase (monthly synced only)."""
        try:
            result = self._client.table("f_x_pnl").select("ReportDate, unique_key").execute()
            if not result.data:
                return set()
            return {row["ReportDate"] for row in result.data if row.get("unique_key")}
        except Exception as e:
            print(f"  [SupabaseClient] Warning: could not fetch P&L dates: {e}")
            return set()

    def delete_all_pnl_records(self) -> int:
        """Delete all P&L rows so the next sync re-fetches everything fresh."""
        try:
            result = self._client.table("f_x_pnl").delete().neq("unique_key", "").execute()
            count = len(result.data) if result.data else 0
            print(f"  [SupabaseClient] Deleted {count} P&L records")
            return count
        except Exception as e:
            print(f"  [SupabaseClient] Warning: could not delete P&L records: {e}")
            return 0

    def delete_old_pnl_records(self, days: int = 90) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        try:
            result = self._client.table("f_x_pnl").delete().lt("ReportDate", cutoff).execute()
            count = len(result.data) if result.data else 0
            if count:
                print(f"  [SupabaseClient] Deleted {count} P&L records older than {cutoff}")
            return count
        except Exception as e:
            print(f"  [SupabaseClient] Warning: could not delete old P&L records: {e}")
            return 0

    # ── Config (refresh token) ────────────────────────────────────────────────

    def get_xero_refresh_token(self) -> str | None:
        try:
            result = self._client.table("config").select("value").eq("key", "xero_refresh_token").execute()
            if result.data:
                return result.data[0]["value"]
        except Exception as e:
            print(f"  [SupabaseClient] Warning: could not read refresh token: {e}")
        return None

    def set_xero_refresh_token(self, token: str) -> None:
        try:
            self._client.table("config").upsert(
                {"key": "xero_refresh_token", "value": token},
                on_conflict="key",
            ).execute()
        except Exception as e:
            print(f"  [SupabaseClient] Warning: could not save refresh token: {e}")

    # ── Sync stats ────────────────────────────────────────────────────────────

    def get_sync_stats(self) -> dict[str, Any]:
        """Return record counts for all xis-pipeline tables."""
        tables = {
            "d_x_accounts": "AccountID",
            "d_x_contacts": "ContactID",
            "f_x_pnl": "id",
            "d_i_products": "productId",
            "d_i_product-location-inventory": "id",
            "f_i_purchase-orders": "line_id",
            "f_i_sales-order": "line_id",
            "d_i_customers": "customerId",
            "d_i_locations": "locationId",
        }
        stats: dict[str, Any] = {}
        for table, pk in tables.items():
            try:
                result = self._client.table(table).select(pk, count="exact").execute()
                stats[table] = result.count if hasattr(result, "count") else 0
            except Exception:
                stats[table] = "error"
        return stats

    # ── Internal ──────────────────────────────────────────────────────────────

    def _upsert(self, table: str, records: list[dict], on_conflict: str) -> int:
        if not records:
            return 0
        result = self._client.table(table).upsert(records, on_conflict=on_conflict).execute()
        count = len(result.data) if result.data else len(records)
        print(f"  [SupabaseClient] {count} records upserted to {table}")
        return count
