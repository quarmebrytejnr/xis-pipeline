"""
xis-pipeline — Xero + Inflow Inventory → Supabase sync SDK.

Quick start
-----------
    pip install xis-pipeline

    from xis import InflowSync, XeroSync

    # Sync everything (reads credentials from env / .env automatically)
    InflowSync().sync()
    XeroSync().sync()

    # Selective sync
    InflowSync().sync(targets=["products", "sales_orders"])
    XeroSync().sync(targets=["pnl"])

    # Fetch data without writing to Supabase
    from xis.inflow import fetch_sales_orders_df
    from xis.inflow._client import InflowClient
    client = InflowClient(api_key="...", company_id="...")
    df = fetch_sales_orders_df(client)

    # Low-level Supabase access
    from xis import SupabaseClient
    db = SupabaseClient()
    print(db.get_sync_stats())

CLI
---
    xis-sync                      # all datasets
    xis-sync inflow               # all Inflow datasets
    xis-sync xero pnl             # Xero P&L only
    xis-sync products sales_orders
"""
from xis.inflow.sync import InflowSync
from xis.xero.sync import XeroSync
from xis.db.client import SupabaseClient

__version__ = "1.0.0"
__all__ = ["InflowSync", "XeroSync", "SupabaseClient", "__version__"]
