"""
InflowSync — high-level class for syncing Inflow Inventory to Supabase.

Quick start:
    from xis import InflowSync

    # reads credentials from environment / .env automatically
    sync = InflowSync()
    sync.sync()                                      # all datasets
    sync.sync(targets=["products", "sales_orders"])  # selective sync

Explicit credentials (e.g. from a secrets manager):
    sync = InflowSync(
        api_key="...",
        company_id="...",
        supabase_url="...",
        supabase_key="...",
    )
"""
from datetime import datetime

from xis._config import get_inflow_config, get_supabase_config
from xis._utils import df_to_clean_records
from xis.inflow._client import InflowClient
from xis.inflow._schemas import (
    D_I_PRODUCTS_COLS,
    D_I_PRODUCT_LOC_INV_COLS,
    F_I_PURCHASE_ORDERS_COLS,
    F_I_SALES_ORDER_COLS,
    D_I_LOCATIONS_COLS,
    D_I_CUSTOMERS_COLS,
)
from xis.inflow.fetchers import (
    fetch_products_df,
    fetch_location_inventory_df,
    fetch_purchase_orders_df,
    fetch_sales_orders_df,
    fetch_customers_df,
    fetch_locations_df,
)

try:
    from supabase import create_client
except ImportError as e:
    raise ImportError("Install the supabase package: pip install supabase") from e

VALID_TARGETS = ("products", "location_inventory", "purchase_orders", "sales_orders", "customers", "locations")


class InflowSync:
    """
    Sync Inflow Inventory data into Supabase.

    Parameters
    ----------
    api_key, company_id
        Inflow Cloud API credentials.  Defaults to INFLOW_API_KEY /
        INFLOW_COMPANY_ID environment variables.
    supabase_url, supabase_key
        Supabase project credentials.  Defaults to SUPABASE_URL /
        SUPABASE_KEY environment variables.
    date_from
        Earliest order date to include for purchase/sales orders.
    batch_size
        Number of rows per Supabase upsert call.
    """

    def __init__(
        self,
        api_key: str | None = None,
        company_id: str | None = None,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        date_from: str = "2025-01-01",
        batch_size: int = 200,
    ) -> None:
        inflow_cfg = get_inflow_config(api_key, company_id)
        supa_cfg = get_supabase_config(supabase_url, supabase_key)

        self._client = InflowClient(inflow_cfg["api_key"], inflow_cfg["company_id"])
        self._db = create_client(supa_cfg["url"], supa_cfg["key"])
        self.date_from = date_from
        self.batch_size = batch_size

    # ── Public API ────────────────────────────────────────────────────────────

    def sync(self, targets: list[str] | None = None) -> dict[str, int]:
        """
        Run the sync for one or more datasets.

        Parameters
        ----------
        targets
            Subset of valid targets to sync.  Pass ``None`` to sync all.
            Valid values: ``"products"``, ``"location_inventory"``,
            ``"purchase_orders"``, ``"sales_orders"``, ``"customers"``,
            ``"locations"``.

        Returns
        -------
        dict mapping target name → number of records upserted.
        """
        if targets is None:
            targets = list(VALID_TARGETS)

        unknown = [t for t in targets if t not in VALID_TARGETS]
        if unknown:
            raise ValueError(f"Unknown target(s): {unknown}. Valid: {VALID_TARGETS}")

        dispatch = {
            "products": self.sync_products,
            "location_inventory": self.sync_location_inventory,
            "purchase_orders": self.sync_purchase_orders,
            "sales_orders": self.sync_sales_orders,
            "customers": self.sync_customers,
            "locations": self.sync_locations,
        }

        start = datetime.utcnow()
        print(f"\n[InflowSync] Started {start.strftime('%Y-%m-%d %H:%M:%S')} UTC | targets={targets}")
        results: dict[str, int] = {}

        for name in targets:
            try:
                results[name] = dispatch[name]()
            except Exception as exc:
                print(f"  [InflowSync] {name} failed: {exc}")
                results[name] = 0

        elapsed = (datetime.utcnow() - start).total_seconds()
        print(f"\n[InflowSync] Done in {elapsed:.1f}s")
        return results

    def sync_products(self) -> int:
        self._header("f_i_products → d_i_products")
        df = fetch_products_df(self._client)
        records = df_to_clean_records(df, D_I_PRODUCTS_COLS)
        records = [r for r in records if r.get("productId")]
        return self._upsert("d_i_products", records, "productId")

    def sync_location_inventory(self) -> int:
        self._header("f_i_products_ → d_i_product-location-inventory")
        df = fetch_location_inventory_df(self._client)
        records = df_to_clean_records(df, D_I_PRODUCT_LOC_INV_COLS)
        records = [r for r in records if r.get("id")]
        return self._upsert("d_i_product-location-inventory", records, "id")

    def sync_purchase_orders(self) -> int:
        self._header("f_i_purchase-order → f_i_purchase-orders")
        df = fetch_purchase_orders_df(self._client, date_from=self.date_from)
        records = df_to_clean_records(df, F_I_PURCHASE_ORDERS_COLS)
        records = [r for r in records if r.get("line_id")]
        return self._upsert("f_i_purchase-orders", records, "line_id")

    def sync_sales_orders(self) -> int:
        self._header("f_i_sales-order → f_i_sales-order")
        df = fetch_sales_orders_df(self._client, date_from=self.date_from)
        records = df_to_clean_records(df, F_I_SALES_ORDER_COLS)
        records = [r for r in records if r.get("line_id")]
        # Delete-then-insert within the sync window to clear cancelled/inactive rows
        # that are excluded from the API response and would otherwise stay stale.
        print(f"  [InflowSync] Deleting existing rows from {self.date_from}...")
        self._db.table("f_i_sales-order").delete().gte("orderDate", self.date_from).execute()
        return self._upsert("f_i_sales-order", records, "line_id")

    def sync_customers(self) -> int:
        self._header("Inflow customers → d_i_customers")
        df = fetch_customers_df(self._client)
        records = df_to_clean_records(df, D_I_CUSTOMERS_COLS)
        records = [r for r in records if r.get("customerId")]
        return self._upsert("d_i_customers", records, "customerId")

    def sync_locations(self) -> int:
        self._header("Inflow locations → d_i_locations")
        df = fetch_locations_df(self._client)
        records = df_to_clean_records(df, D_I_LOCATIONS_COLS)
        records = [r for r in records if r.get("locationId")]
        return self._upsert("d_i_locations", records, "locationId")

    # ── Low-level ─────────────────────────────────────────────────────────────

    def _upsert(self, table: str, records: list, on_conflict: str) -> int:
        if not records:
            print(f"  [InflowSync] No records to upsert for {table}")
            return 0
        total = 0
        for i in range(0, len(records), self.batch_size):
            batch = records[i: i + self.batch_size]
            result = self._db.table(table).upsert(batch, on_conflict=on_conflict).execute()
            total += len(result.data) if result.data else len(batch)
        print(f"  [InflowSync] {total} records upserted to {table}")
        return total

    @staticmethod
    def _header(label: str) -> None:
        bar = "=" * 60
        print(f"\n{bar}\n[InflowSync] {label}\n{bar}")
