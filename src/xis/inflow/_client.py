"""
Inflow Cloud Inventory API client.

Handles authentication, rate limiting, SSL retries, and cursor pagination.
All API calls go through this client so sync logic stays clean.
"""
import time
import requests


class InflowClient:
    _API_BASE = "https://cloudapi.inflowinventory.com"
    _ACCEPT = "application/json;version=2024-10-01"

    def __init__(self, api_key: str, company_id: str) -> None:
        self._base = f"{self._API_BASE}/{company_id}"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": self._ACCEPT,
        }

    # ── Low-level request ─────────────────────────────────────────────────────

    def get(self, path: str, params: dict | None = None, max_retries: int = 3) -> requests.Response:
        """GET with exponential-backoff on SSL / network errors and 429 handling."""
        url = f"{self._base}{path}"
        current_params = params or {}

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, headers=self._headers, params=current_params, timeout=30)
            except requests.exceptions.SSLError as exc:
                if attempt == max_retries:
                    raise
                self._backoff(attempt, f"SSL error: {exc}")
                continue
            except requests.exceptions.RequestException as exc:
                if attempt == max_retries:
                    raise
                self._backoff(attempt, f"Request error: {exc}")
                continue

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"  [Inflow] Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue

            return resp

        # Shouldn't reach here, but satisfy type checker
        return resp  # type: ignore[return-value]

    # ── Cursor pagination ─────────────────────────────────────────────────────

    def paginate(self, path: str, params: dict) -> list:
        """
        Fetch every page from a cursor-paginated Inflow endpoint.

        Inflow uses `after=<last_id>` for pagination.  We auto-detect the ID
        field from the first response (purchaseOrderId, salesOrderId, etc.).
        """
        all_records: list = []
        current_params = dict(params)
        last_id_key: str | None = None

        while True:
            resp = self.get(path, current_params)
            if resp.status_code != 200:
                print(f"  [Inflow] API error {resp.status_code}: {resp.text[:300]}")
                break

            records: list = resp.json()
            if not records:
                break

            all_records.extend(records)

            page_size = current_params.get("count", 100)
            if len(records) < page_size:
                break

            # Detect the ID field once on the first page
            if last_id_key is None:
                for candidate in ("purchaseOrderId", "salesOrderId", "productId", "customerId"):
                    if candidate in records[-1]:
                        last_id_key = candidate
                        break

            if last_id_key:
                current_params["after"] = records[-1].get(last_id_key)
            else:
                break

        return all_records

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _backoff(attempt: int, msg: str) -> None:
        wait = 2 ** attempt
        print(f"  [Inflow] {msg} (attempt {attempt}), retrying in {wait}s...")
        time.sleep(wait)
