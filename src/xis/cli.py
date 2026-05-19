"""
Command-line interface for xis-pipeline.

Usage:
    xis-sync                                  # sync all Inflow + Xero
    xis-sync inflow                           # sync all Inflow datasets
    xis-sync xero                             # sync all Xero datasets
    xis-sync inflow products sales_orders     # specific Inflow targets
    xis-sync xero accounts pnl               # specific Xero targets
"""
import sys
from xis.inflow.sync import InflowSync
from xis.xero.sync import XeroSync

INFLOW_TARGETS = {"products", "location_inventory", "purchase_orders", "sales_orders", "customers", "locations"}
XERO_TARGETS = {"accounts", "contacts", "pnl"}


def main(argv: list[str] | None = None) -> None:
    args = (argv or sys.argv)[1:]

    run_inflow = not args or "inflow" in args or any(a in INFLOW_TARGETS for a in args)
    run_xero = not args or "xero" in args or any(a in XERO_TARGETS for a in args)

    inflow_targets = [a for a in args if a in INFLOW_TARGETS] or None
    xero_targets = [a for a in args if a in XERO_TARGETS] or None

    results: dict[str, int] = {}

    if run_inflow:
        try:
            sync = InflowSync()
            results.update(sync.sync(targets=inflow_targets))
        except EnvironmentError as e:
            print(f"[Inflow] Skipped — {e}")

    if run_xero:
        try:
            sync = XeroSync()
            results.update(sync.sync(targets=xero_targets))
        except EnvironmentError as e:
            print(f"[Xero] Skipped — {e}")

    if results:
        print("\nSummary:")
        for name, count in results.items():
            icon = "✓" if count > 0 else "!"
            print(f"  {icon} {name}: {count} records")


if __name__ == "__main__":
    main()
