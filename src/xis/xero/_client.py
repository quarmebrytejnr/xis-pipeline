"""
Xero OAuth2 client with automatic refresh-token rotation.

Xero's tokens expire after 30 minutes (access) / 60 days inactive (refresh).
This client transparently refreshes on every instantiation and persists the
new refresh token back to a Supabase `config` table so GitHub Actions and
local runs always share a valid token.

Token bootstrap for first use
------------------------------
1. Create a Xero app at https://developer.xero.com/myapps
2. Run the initial OAuth2 flow once locally (see README → "First-time setup")
3. Store the resulting refresh_token as env var XERO_REFRESH_TOKEN (and in
   your GitHub repo secret of the same name).
"""
import time
import requests
from base64 import b64encode


XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"


class XeroClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        tenant_id: str,
        on_token_refresh=None,
    ) -> None:
        """
        Parameters
        ----------
        on_token_refresh
            Optional callable(new_refresh_token: str) invoked after every
            successful token refresh.  Use it to persist the rotated token
            (e.g. write it back to a Supabase config table or GitHub secret).
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id
        self._on_token_refresh = on_token_refresh

        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._refresh_token = refresh_token

        # Eagerly refresh so the caller always has a valid token
        self._do_refresh()

    # ── Token management ──────────────────────────────────────────────────────

    def _do_refresh(self) -> None:
        credentials = b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        resp = requests.post(
            XERO_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Xero token refresh failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        self._expires_at = time.time() + data.get("expires_in", 1800) - 60  # 60s buffer

        if self._on_token_refresh:
            try:
                self._on_token_refresh(self._refresh_token)
            except Exception as e:
                print(f"  [Xero] Warning: could not persist rotated refresh token: {e}")

    def _ensure_valid_token(self) -> None:
        if time.time() >= self._expires_at:
            self._do_refresh()

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        self._ensure_valid_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Xero-tenant-id": self._tenant_id,
            "Accept": "application/json",
        }

    def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{XERO_API_BASE}/{path.lstrip('/')}"
        resp = requests.get(url, headers=self._headers(), params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_paginated(self, path: str, root_key: str, page_size: int = 100) -> list:
        """Page through a Xero endpoint that supports ?page=N."""
        all_items: list = []
        page = 1
        while True:
            data = self.get(path, {"page": page, "pageSize": page_size})
            items = data.get(root_key, [])
            all_items.extend(items)
            if len(items) < page_size:
                break
            page += 1
        return all_items

    # ── Xero API calls ────────────────────────────────────────────────────────

    def get_accounts(self) -> list:
        data = self.get("Accounts")
        return data.get("Accounts", [])

    def get_contacts(self, page_size: int = 100) -> list:
        return self.get_paginated("Contacts", "Contacts", page_size)

    def get_pnl_report(self, from_date: str, to_date: str) -> dict:
        return self.get(
            "Reports/ProfitAndLoss",
            {
                "fromDate": from_date,
                "toDate": to_date,
                "periods": 1,
                "timeframe": "MONTH",
            },
        )

    def get_connections(self) -> list:
        self._ensure_valid_token()
        resp = requests.get(
            XERO_CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
