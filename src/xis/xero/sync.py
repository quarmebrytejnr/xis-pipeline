"""
XeroSync — high-level class for syncing Xero data to Supabase.

Quick start:
    from xis import XeroSync

    # reads credentials from environment / .env automatically
    sync = XeroSync()
    sync.sync()                              # accounts + contacts + pnl
    sync.sync(targets=["accounts", "pnl"])   # selective sync

Explicit credentials:
    sync = XeroSync(
        client_id="...",
        client_secret="...",
        refresh_token="...",
        tenant_id="...",
        supabase_url="...",
        supabase_key="...",
    )

Refresh token rotation
----------------------
Xero rotates the refresh token on every use.  XeroSync automatically saves
the new token back to your Supabase `config` table (key = 'xero_refresh_token')
so both local runs and GitHub Actions always start with a valid token.

To also update a GitHub Actions secret automatically, set the env var
GH_PAT (a personal access token with `secrets` scope) and pass your
repo slug:

    sync = XeroSync(gh_repo="owner/repo")
"""
import os
from datetime import datetime, timedelta

try:
    from supabase import create_client
except ImportError as e:
    raise ImportError("Install the supabase package: pip install supabase") from e

from xis._config import get_xero_config, get_supabase_config
from xis.xero._client import XeroClient

VALID_TARGETS = ("accounts", "contacts", "pnl")

# How many months back to sync P&L if no existing data is found
_DEFAULT_PNL_MONTHS = 18


class XeroSync:
    """
    Sync Xero data into Supabase.

    Parameters
    ----------
    client_id, client_secret, refresh_token, tenant_id
        Xero OAuth2 credentials.  Fall back to env vars XERO_CLIENT_ID,
        XERO_CLIENT_SECRET, XERO_REFRESH_TOKEN, XERO_TENANT_ID.
    supabase_url, supabase_key
        Supabase credentials.  Fall back to env vars SUPABASE_URL,
        SUPABASE_KEY.
    gh_repo
        GitHub repo slug (``"owner/repo"``) for updating XERO_REFRESH_TOKEN
        secret after rotation.  Requires GH_PAT env var.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        tenant_id: str | None = None,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        gh_repo: str | None = None,
    ) -> None:
        xero_cfg = get_xero_config(client_id, client_secret, refresh_token, tenant_id)
        supa_cfg = get_supabase_config(supabase_url, supabase_key)

        self._db = create_client(supa_cfg["url"], supa_cfg["key"])
        self._gh_repo = gh_repo

        # Try to pull a fresher refresh token from Supabase first so multiple
        # concurrent instances (local + Actions) don't collide.
        stored_token = self._get_stored_refresh_token()
        effective_refresh = stored_token or xero_cfg["refresh_token"]

        self._xero = XeroClient(
            client_id=xero_cfg["client_id"],
            client_secret=xero_cfg["client_secret"],
            refresh_token=effective_refresh,
            tenant_id=xero_cfg["tenant_id"],
            on_token_refresh=self._on_token_refresh,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def sync(self, targets: list[str] | None = None) -> dict[str, int]:
        """
        Sync one or more Xero datasets to Supabase.

        Parameters
        ----------
        targets
            Subset of ``("accounts", "contacts", "pnl")``.
            Pass ``None`` to sync all.

        Returns
        -------
        dict mapping target name → records upserted.
        """
        if targets is None:
            targets = list(VALID_TARGETS)

        unknown = [t for t in targets if t not in VALID_TARGETS]
        if unknown:
            raise ValueError(f"Unknown Xero target(s): {unknown}. Valid: {VALID_TARGETS}")

        dispatch = {
            "accounts": self.sync_accounts,
            "contacts": self.sync_contacts,
            "pnl": self.sync_pnl,
        }

        start = datetime.utcnow()
        print(f"\n[XeroSync] Started {start.strftime('%Y-%m-%d %H:%M:%S')} UTC | targets={targets}")
        results: dict[str, int] = {}

        for name in targets:
            try:
                results[name] = dispatch[name]()
            except Exception as exc:
                print(f"  [XeroSync] {name} failed: {exc}")
                results[name] = 0

        elapsed = (datetime.utcnow() - start).total_seconds()
        print(f"\n[XeroSync] Done in {elapsed:.1f}s")
        return results

    def sync_accounts(self) -> int:
        self._header("Xero Accounts → d_x_accounts")
        accounts = self._xero.get_accounts()
        print(f"  [XeroSync] {len(accounts)} accounts")
        if not accounts:
            return 0

        records = []
        for a in accounts:
            records.append({
                "AccountID": a.get("AccountID"),
                "Name": a.get("Name"),
                "Status": a.get("Status"),
                "Type": a.get("Type"),
                "TaxType": a.get("TaxType"),
                "Class": a.get("Class"),
                "EnablePaymentsToAccount": a.get("EnablePaymentsToAccount", False),
                "ShowInExpenseClaims": a.get("ShowInExpenseClaims", False),
                "BankAccountNumber": a.get("BankAccountNumber"),
                "BankAccountType": a.get("BankAccountType"),
                "CurrencyCode": a.get("CurrencyCode"),
                "ReportingCode": a.get("ReportingCode"),
                "ReportingCodeName": a.get("ReportingCodeName"),
                "HasAttachments": a.get("HasAttachments", False),
                "UpdatedDateUTC": a.get("UpdatedDateUTC"),
                "AddToWatchlist": a.get("AddToWatchlist", False),
                "Code": a.get("Code"),
                "Description": a.get("Description"),
                "SystemAccount": a.get("SystemAccount"),
            })

        return self._upsert("d_x_accounts", records, "AccountID")

    def sync_contacts(self) -> int:
        self._header("Xero Contacts → d_x_contacts")
        contacts = self._xero.get_contacts()
        print(f"  [XeroSync] {len(contacts)} contacts")
        if not contacts:
            return 0

        records = []
        for c in contacts:
            balances = c.get("Balances", {})
            ar = balances.get("AccountsReceivable", {})
            ap = balances.get("AccountsPayable", {})
            bp = c.get("BatchPayments", {})
            records.append({
                "ContactID": c.get("ContactID"),
                "ContactStatus": c.get("ContactStatus"),
                "Name": c.get("Name"),
                "FirstName": c.get("FirstName"),
                "LastName": c.get("LastName"),
                "EmailAddress": c.get("EmailAddress"),
                "Website": c.get("Website"),
                "AccountNumber": c.get("AccountNumber"),
                "CompanyNumber": c.get("CompanyNumber"),
                "BankAccountDetails": c.get("BankAccountDetails"),
                "DefaultCurrency": c.get("DefaultCurrency"),
                "IsSupplier": c.get("IsSupplier", False),
                "IsCustomer": c.get("IsCustomer", False),
                "HasAttachments": c.get("HasAttachments", False),
                "HasValidationErrors": c.get("HasValidationErrors", False),
                "UpdatedDateUTC": c.get("UpdatedDateUTC"),
                "ContactGroups": c.get("ContactGroups"),
                "ContactPersons": c.get("ContactPersons"),
                "SalesTrackingCategories": str(c.get("SalesTrackingCategories", "")),
                "Balances.AccountsReceivable.Outstanding": str(ar.get("Outstanding", "")),
                "Balances.AccountsReceivable.Overdue": str(ar.get("Overdue", "")),
                "Balances.AccountsPayable.Outstanding": str(ap.get("Outstanding", "")),
                "Balances.AccountsPayable.Overdue": str(ap.get("Overdue", "")),
                "BatchPayments.BankAccountNumber": bp.get("BankAccountNumber"),
                "BatchPayments.BankAccountName": bp.get("BankAccountName"),
                "BatchPayments.Details": bp.get("Details"),
                "BatchPayments.Code": bp.get("Code"),
                "BatchPayments.Reference": bp.get("Reference"),
                "LastUpdated": datetime.utcnow().isoformat(),
            })

        return self._upsert("d_x_contacts", records, "ContactID")

    def sync_pnl(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> int:
        """
        Sync monthly P&L rows.

        If from_date / to_date are omitted, the method syncs every month
        not already present in Supabase (incremental).  Pass explicit dates
        to force a range re-sync.
        """
        self._header("Xero P&L → f_x_pnl")
        today = datetime.utcnow()

        if from_date and to_date:
            months = list(_month_range(from_date, to_date))
        else:
            existing = self._get_existing_pnl_dates()
            start = today - timedelta(days=_DEFAULT_PNL_MONTHS * 30)
            all_months = list(_month_range(start.strftime("%Y-%m-01"), today.strftime("%Y-%m-01")))
            months = [m for m in all_months if m not in existing]

        if not months:
            print("  [XeroSync] P&L already up to date")
            return 0

        print(f"  [XeroSync] Syncing {len(months)} month(s)...")
        total = 0
        for month_start in months:
            month_end = _month_end(month_start)
            print(f"    {month_start} → {month_end}")
            try:
                raw = self._xero.get_pnl_report(month_start, month_end)
                records = _parse_pnl(raw, month_start)
                total += self._upsert("f_x_pnl", records, "unique_key")
            except Exception as exc:
                print(f"    [XeroSync] P&L {month_start} failed: {exc}")

        return total

    # ── Refresh token persistence ──────────────────────────────────────────────

    def _on_token_refresh(self, new_token: str) -> None:
        """Called by XeroClient after every successful token rotation."""
        self._save_refresh_token(new_token)
        self._update_github_secret(new_token)

    def _get_stored_refresh_token(self) -> str | None:
        try:
            result = self._db.table("config").select("value").eq("key", "xero_refresh_token").execute()
            if result.data:
                return result.data[0]["value"]
        except Exception:
            pass
        return None

    def _save_refresh_token(self, token: str) -> None:
        try:
            self._db.table("config").upsert(
                {"key": "xero_refresh_token", "value": token},
                on_conflict="key",
            ).execute()
            print("  [XeroSync] Refresh token saved to Supabase config")
        except Exception as e:
            print(f"  [XeroSync] Warning: could not save refresh token to Supabase: {e}")

    def _update_github_secret(self, token: str) -> None:
        repo = self._gh_repo or os.environ.get("GITHUB_REPOSITORY")
        pat = os.environ.get("GH_PAT")
        if not repo or not pat:
            return
        try:
            import subprocess
            result = subprocess.run(
                ["gh", "secret", "set", "XERO_REFRESH_TOKEN", "--repo", repo],
                input=token.encode(),
                capture_output=True,
            )
            if result.returncode == 0:
                print(f"  [XeroSync] GitHub secret XERO_REFRESH_TOKEN updated for {repo}")
            else:
                print(f"  [XeroSync] Warning: gh secret set failed: {result.stderr.decode()[:200]}")
        except FileNotFoundError:
            pass  # gh CLI not available

    # ── Supabase helpers ──────────────────────────────────────────────────────

    def _get_existing_pnl_dates(self) -> set[str]:
        try:
            result = self._db.table("f_x_pnl").select("ReportDate, unique_key").execute()
            if not result.data:
                return set()
            return {row["ReportDate"] for row in result.data if row.get("unique_key")}
        except Exception:
            return set()

    def _upsert(self, table: str, records: list, on_conflict: str) -> int:
        if not records:
            print(f"  [XeroSync] No records to upsert for {table}")
            return 0
        result = self._db.table(table).upsert(records, on_conflict=on_conflict).execute()
        count = len(result.data) if result.data else len(records)
        print(f"  [XeroSync] {count} records upserted to {table}")
        return count

    @staticmethod
    def _header(label: str) -> None:
        bar = "=" * 60
        print(f"\n{bar}\n[XeroSync] {label}\n{bar}")


# ── P&L parsing ───────────────────────────────────────────────────────────────

def _parse_pnl(raw: dict, report_date: str) -> list[dict]:
    """Flatten a Xero ProfitAndLoss report response into upsert-ready rows."""
    records = []
    reports = raw.get("Reports", [])
    if not reports:
        return records

    report = reports[0]
    rows = report.get("Rows", [])

    def _walk(rows: list, section: str = "", sub_section: str = "") -> None:
        for row in rows:
            row_type = row.get("RowType", "")
            if row_type == "Section":
                title = (row.get("Title") or "").strip()
                new_section = title if title else section
                _walk(row.get("Rows", []), new_section, "")
            elif row_type == "Row":
                cells = row.get("Cells", [])
                account = cells[0].get("Value", "") if cells else ""
                account_id = (cells[0].get("Attributes") or [{}])[0].get("Value", "") if cells else ""
                value = cells[1].get("Value", "") if len(cells) > 1 else ""
                unique_key = f"{report_date}|{section}|{sub_section}|{account}"
                records.append({
                    "ReportDate": report_date,
                    "Section": section,
                    "SubSection": sub_section,
                    "RowType": row_type,
                    "Account": account,
                    "AccountID": account_id,
                    "Column_1": value,
                    "unique_key": unique_key,
                })
            elif row_type == "SummaryRow":
                cells = row.get("Cells", [])
                label = cells[0].get("Value", "TOTAL") if cells else "TOTAL"
                value = cells[1].get("Value", "") if len(cells) > 1 else ""
                unique_key = f"{report_date}|{section}|SUMMARY|{label}"
                records.append({
                    "ReportDate": report_date,
                    "Section": section,
                    "SubSection": "SUMMARY",
                    "RowType": row_type,
                    "Account": label,
                    "AccountID": "",
                    "Column_1": value,
                    "unique_key": unique_key,
                })

    _walk(rows)
    return records


def _month_range(from_date: str, to_date: str):
    """Yield YYYY-MM-01 strings from from_date to to_date inclusive."""
    start = datetime.strptime(from_date[:7], "%Y-%m")
    end = datetime.strptime(to_date[:7], "%Y-%m")
    current = start
    while current <= end:
        yield current.strftime("%Y-%m-01")
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def _month_end(month_start: str) -> str:
    """Return the last day of the month for a YYYY-MM-01 string."""
    dt = datetime.strptime(month_start, "%Y-%m-01")
    if dt.month == 12:
        last = dt.replace(year=dt.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        last = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
    return last.strftime("%Y-%m-%d")
