"""
Raw fetch functions — each returns a cleaned pandas DataFrame.

These are the building blocks used by InflowSync.  You can call them
directly if you want the data without writing to Supabase.

    from xis.inflow import fetch_sales_orders_df
    df = fetch_sales_orders_df(client)
"""
import time
import pandas as pd
from datetime import datetime

from xis.inflow._client import InflowClient


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_all_products(client: InflowClient) -> list:
    return client.paginate("/products", {"count": 100, "include": "cost"})


def _fetch_all_locations(client: InflowClient) -> list:
    resp = client.get("/locations")
    return resp.json() if resp.status_code == 200 else []


def _fetch_product_summary(client: InflowClient, product_id: str, location_id: str | None = None) -> dict:
    params = {"locationId": location_id} if location_id else {}
    resp = client.get(f"/products/{product_id}/summary", params)
    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    return {}


def _extract_team_member(record: dict, tm: dict | None, prefix: str) -> None:
    fields = ["name", "email", "isActive", "isInternal", "canBeSalesRep",
              "accessAllLocations", "teamMemberId", "accessLocationIds"]
    if not tm:
        for f in fields:
            record[f"{prefix}_{f}"] = None
        return
    for f in fields:
        if f == "accessLocationIds":
            ids = tm.get("accessLocationIds") or []
            record[f"{prefix}_{f}"] = ",".join(ids) if ids else None
        else:
            record[f"{prefix}_{f}"] = tm.get(f)


def _preprocess_sales_record(record: dict) -> None:
    """Flatten all nested objects on a sales order record in-place."""
    # COGS
    cogs = record.get("costOfGoodsSold") or {}
    record["cogs_value"] = cogs.get("costOfGoodsSold")
    record["cogs_id"] = cogs.get("salesOrderCostOfGoodsSoldId")
    record["cogs_salesOrderId"] = cogs.get("salesOrderId")
    so = cogs.get("salesOrder") or {}
    record["cogs_salesOrder_id"] = so.get("salesOrderId")
    record["cogs_salesOrder_orderNumber"] = so.get("orderNumber")
    record["cogs_salesOrder_orderDate"] = so.get("orderDate")

    # Custom fields
    cf = record.get("customFields") or {}
    for i in range(1, 11):
        record[f"customFields_custom{i}"] = cf.get(f"custom{i}")

    # Non-customer cost
    nc = record.get("nonCustomerCost") or {}
    try:
        record["nonCustomerCost_value"] = float(nc["value"]) if nc.get("value") is not None else None
    except (ValueError, TypeError):
        record["nonCustomerCost_value"] = None
    record["nonCustomerCost_isPercent"] = bool(nc.get("isPercent", False)) if nc else None

    # Pricing scheme (from customer)
    customer = record.get("customer") or {}
    ps = customer.get("pricingScheme") if customer else None
    _extract_pricing_scheme(record, ps)

    # Team members
    _extract_team_member(record, record.get("salesRepTeamMember"), "salesRep")
    _extract_team_member(record, record.get("assignedToTeamMember"), "assignedTo")


def _extract_pricing_scheme(record: dict, ps: dict | None) -> None:
    null_fields = [
        "pricing_scheme_name", "pricing_scheme_id", "pricing_scheme_isActive",
        "pricing_scheme_isDefault", "pricing_scheme_isTaxInclusive", "pricing_scheme_currencyId",
        "pricing_scheme_currency_name", "pricing_scheme_currency_isoCode",
        "pricing_scheme_currency_symbol", "pricing_scheme_currency_decimalPlaces",
        "pricing_scheme_currency_isSymbolFirst", "pricing_scheme_currency_decimalSeparator",
        "pricing_scheme_currency_thousandsSeparator", "pricing_scheme_currency_negativeType",
        "pricing_scheme_currency_exchangeRate", "pricing_scheme_currency_isManual",
        "pricing_scheme_productPrices_count", "pricing_scheme_productPrice_fixedMarkup",
        "pricing_scheme_productPrice_priceType", "pricing_scheme_productPrice_pricingSchemeId",
        "pricing_scheme_productPrice_id", "pricing_scheme_productPrice_unitPrice",
        "pricing_scheme_productPrice_product_name", "pricing_scheme_productPrice_product_sku",
        "pricing_scheme_productPrice_product_autoAssemble", "pricing_scheme_productPrice_product_id",
        "pricing_scheme_productPrice_product_category_name",
        "pricing_scheme_productPrice_product_category_id",
        "pricing_scheme_productPrice_product_category_isDefault",
        "pricing_scheme_productPrice_product_cost_direct",
        "pricing_scheme_productPrice_product_cost_value",
        "pricing_scheme_productPrice_product_cost_id",
        "pricing_scheme_productPrice_product_cost_productId",
        "pricing_scheme_productPrice_product_itemType",
    ]
    if not ps:
        for f in null_fields:
            record[f] = None
        return

    record["pricing_scheme_name"] = ps.get("name")
    record["pricing_scheme_id"] = ps.get("pricingSchemeId")
    record["pricing_scheme_isActive"] = ps.get("isActive")
    record["pricing_scheme_isDefault"] = ps.get("isDefault")
    record["pricing_scheme_isTaxInclusive"] = ps.get("isTaxInclusive")
    record["pricing_scheme_currencyId"] = ps.get("currencyId")

    curr = ps.get("currency") or {}
    record["pricing_scheme_currency_name"] = curr.get("name")
    record["pricing_scheme_currency_isoCode"] = curr.get("isoCode")
    record["pricing_scheme_currency_symbol"] = curr.get("symbol")
    record["pricing_scheme_currency_decimalPlaces"] = curr.get("decimalPlaces")
    record["pricing_scheme_currency_isSymbolFirst"] = curr.get("isSymbolFirst")
    record["pricing_scheme_currency_decimalSeparator"] = curr.get("decimalSeparator")
    record["pricing_scheme_currency_thousandsSeparator"] = curr.get("thousandsSeparator")
    record["pricing_scheme_currency_negativeType"] = curr.get("negativeType")
    convs = curr.get("currencyConversions") or []
    conv = convs[0] if convs else {}
    record["pricing_scheme_currency_exchangeRate"] = conv.get("exchangeRate")
    record["pricing_scheme_currency_isManual"] = conv.get("isManual")

    prices = ps.get("productPrices") or []
    record["pricing_scheme_productPrices_count"] = len(prices)
    pp = prices[0] if prices else {}
    record["pricing_scheme_productPrice_fixedMarkup"] = pp.get("fixedMarkup")
    record["pricing_scheme_productPrice_priceType"] = pp.get("priceType")
    record["pricing_scheme_productPrice_pricingSchemeId"] = pp.get("pricingSchemeId")
    record["pricing_scheme_productPrice_id"] = pp.get("productPriceId")
    record["pricing_scheme_productPrice_unitPrice"] = pp.get("unitPrice")

    pp_prod = pp.get("product") or {}
    record["pricing_scheme_productPrice_product_name"] = pp_prod.get("name")
    record["pricing_scheme_productPrice_product_sku"] = pp_prod.get("sku")
    record["pricing_scheme_productPrice_product_autoAssemble"] = pp_prod.get("autoAssemble")
    record["pricing_scheme_productPrice_product_id"] = pp_prod.get("productId")
    record["pricing_scheme_productPrice_product_itemType"] = pp_prod.get("itemType")
    pp_cat = pp_prod.get("category") or {}
    record["pricing_scheme_productPrice_product_category_name"] = pp_cat.get("name")
    record["pricing_scheme_productPrice_product_category_id"] = pp_cat.get("categoryId")
    record["pricing_scheme_productPrice_product_category_isDefault"] = pp_cat.get("isDefault")
    raw_cost = pp_prod.get("cost")
    record["pricing_scheme_productPrice_product_cost_direct"] = raw_cost
    pp_cost = raw_cost if isinstance(raw_cost, dict) else {}
    record["pricing_scheme_productPrice_product_cost_value"] = pp_cost.get("cost")
    record["pricing_scheme_productPrice_product_cost_id"] = pp_cost.get("productCostId")
    record["pricing_scheme_productPrice_product_cost_productId"] = pp_cost.get("productId")


# ── Public fetch functions ────────────────────────────────────────────────────

def fetch_products_df(client: InflowClient) -> pd.DataFrame:
    """Products + overall inventory summary → ready for d_i_products."""
    print("  [Inflow] Fetching products...")
    all_products = _fetch_all_products(client)
    print(f"  [Inflow] {len(all_products)} products")
    if not all_products:
        return pd.DataFrame()

    df = pd.DataFrame(all_products)

    if "cost" in df.columns:
        df["cost_value"] = df["cost"].apply(lambda x: x.get("cost") if isinstance(x, dict) else None)
        df["productCostId"] = df["cost"].apply(lambda x: x.get("productCostId") if isinstance(x, dict) else None)
        df.drop("cost", axis=1, inplace=True)

    if "customFields" in df.columns:
        for i in range(1, 11):
            df[f"Custom_Field_{i}"] = df["customFields"].apply(
                lambda x, i=i: x.get(f"custom{i}", "") if isinstance(x, dict) else ""
            )
        df.drop("customFields", axis=1, inplace=True)

    print("  [Inflow] Fetching inventory summaries...")
    inventory_data = []
    for idx, product in enumerate(all_products):
        if idx % 25 == 0:
            print(f"    {idx}/{len(all_products)}...")
        pid = product["productId"]
        summary = _fetch_product_summary(client, pid)
        summary["productId"] = pid
        inventory_data.append(summary)
        time.sleep(0.1)

    inventory_df = pd.DataFrame(inventory_data)
    merged = pd.merge(df, inventory_df, on="productId", how="left")
    merged["last_refresh"] = datetime.utcnow().isoformat()
    return merged


def fetch_location_inventory_df(client: InflowClient) -> pd.DataFrame:
    """Per-product per-location inventory → ready for d_i_product-location-inventory."""
    print("  [Inflow] Fetching products and locations for location inventory...")
    all_products = _fetch_all_products(client)
    locations = _fetch_all_locations(client)
    print(f"  [Inflow] {len(all_products)} products × {len(locations)} locations")

    inventory_data = []
    for idx, product in enumerate(all_products):
        if idx % 10 == 0:
            print(f"    Product {idx}/{len(all_products)}...")
        pid = product["productId"]
        for loc in locations:
            if not isinstance(loc, dict):
                continue
            loc_id = loc.get("locationId")
            loc_name = loc.get("name", "")
            summary = _fetch_product_summary(client, pid, loc_id)
            if summary:
                summary["productId"] = pid
                summary["locationId"] = loc_id
                summary["location_name"] = loc_name
                summary["id"] = f"{pid}_{loc_id}"
                inventory_data.append(summary)
            time.sleep(0.1)

    if not inventory_data:
        return pd.DataFrame()
    df = pd.DataFrame(inventory_data)
    df["last_refresh"] = datetime.utcnow().isoformat()
    return df


def fetch_purchase_orders_df(client: InflowClient, date_from: str = "2025-01-01") -> pd.DataFrame:
    """Purchase orders with line items → ready for f_i_purchase-orders."""
    today = datetime.now().strftime("%Y-%m-%d")
    print("  [Inflow] Fetching purchase orders...")
    all_records = client.paginate(
        "/purchase-orders",
        {
            "count": 100,
            "include": "lines,lines.product,vendor,location",
            "filter[orderDate][fromDate]": date_from,
            "filter[orderDate][toDate]": today,
        },
    )
    print(f"  [Inflow] {len(all_records)} purchase orders")

    purchase_orders = []
    for po in all_records:
        cf = po.get("customFields") or {}
        purchase_orders.append({
            "purchaseOrderId": po.get("purchaseOrderId", ""),
            "location_name": (po.get("location") or {}).get("name", ""),
            "amountPaid": po.get("amountPaid", 0),
            "balance": po.get("balance", 0),
            "calculateTax2OnTax1": po.get("calculateTax2OnTax1", False),
            "carrier": po.get("carrier", ""),
            "contactName": po.get("contactName", ""),
            "currencyId": po.get("currencyId", ""),
            "dueDate": po.get("dueDate", ""),
            "email": po.get("email", ""),
            "exchangeRate": po.get("exchangeRate", 0),
            "exchangeRateAutoPulled": po.get("exchangeRateAutoPulled", False),
            "freight": po.get("freight", 0),
            "inventoryStatus": po.get("inventoryStatus", ""),
            "isCancelled": po.get("isCancelled", False),
            "isCompleted": po.get("isCompleted", False),
            "isQuote": po.get("isQuote", False),
            "isTaxInclusive": po.get("isTaxInclusive", False),
            "itemType": po.get("itemType", ""),
            "lastModifiedById": po.get("lastModifiedById", ""),
            "locationId": po.get("locationId", ""),
            "orderDate": po.get("orderDate", ""),
            "orderNumber": po.get("orderNumber", ""),
            "orderRemarks": po.get("orderRemarks", ""),
            "paidDate": po.get("paidDate", ""),
            "paymentStatus": po.get("paymentStatus", ""),
            "phone": po.get("phone") or None,
            "receiveRemarks": po.get("receiveRemarks", ""),
            "returnExtra": po.get("returnExtra", 0),
            "returnFee": po.get("returnFee", 0),
            "returnRemarks": po.get("returnRemarks", ""),
            "shipToCompanyName": po.get("shipToCompanyName", ""),
            "showShipping": po.get("showShipping", False),
            "subTotal": po.get("subTotal", 0),
            "tax1": po.get("tax1", 0),
            "tax1Name": po.get("tax1Name", ""),
            "tax1OnShipping": po.get("tax1OnShipping", False),
            "tax1Rate": po.get("tax1Rate", 0),
            "tax2": po.get("tax2", 0),
            "tax2Name": po.get("tax2Name", ""),
            "tax2OnShipping": po.get("tax2OnShipping", False),
            "tax2Rate": po.get("tax2Rate", 0),
            "taxingSchemeId": po.get("taxingSchemeId", ""),
            "timestamp": po.get("timestamp", ""),
            "total": po.get("total", 0),
            "unstockRemarks": po.get("unstockRemarks", ""),
            "vendorId": po.get("vendorId", ""),
            "vendorOrderNumber": po.get("vendorOrderNumber", ""),
            **{f"customFields_custom{i}": cf.get(f"custom{i}", "") for i in range(1, 11)},
            "nonVendorCosts_value": (po.get("nonVendorCosts") or {}).get("value", 0),
            "nonVendorCosts_isPercent": (po.get("nonVendorCosts") or {}).get("isPercent", False),
            **{f"shipToAddress_{k}": (po.get("shipToAddress") or {}).get(k, "")
               for k in ("address1", "address2", "city", "state", "country", "postalCode", "remarks")},
            **{f"vendorAddress_{k}": (po.get("vendorAddress") or {}).get(k, "")
               for k in ("address1", "address2", "city", "state", "country", "postalCode")},
        })

    po_df = pd.DataFrame(purchase_orders)

    line_items = []
    for po in all_records:
        po_id = po.get("purchaseOrderId", "")
        for line in (po.get("lines") or []):
            if line is None:
                continue
            product = line.get("product") or {}
            line_items.append({
                "purchaseOrderId": po_id,
                "line_id": line.get("purchaseOrderLineId", ""),
                "product_id": line.get("productId", ""),
                "product_name": product.get("name", ""),
                "product_sku": product.get("sku") or None,
                "item_type": product.get("itemType", ""),
                "quantity_ordered": line.get("quantity", 0),
                "quantity_received": line.get("quantityReceived", 0),
                "quantity_returned": line.get("quantityReturned", 0),
                "unit_price": line.get("unitPrice", 0),
                "line_total": line.get("extendedPrice", 0),
                "sublocation": line.get("sublocation", ""),
            })

    li_cols = ["purchaseOrderId", "line_id", "product_id", "product_name", "product_sku",
               "item_type", "quantity_ordered", "quantity_received", "quantity_returned",
               "unit_price", "line_total", "sublocation"]
    li_df = pd.DataFrame(line_items) if line_items else pd.DataFrame(columns=li_cols)
    combined = pd.merge(po_df, li_df, on="purchaseOrderId", how="left")
    combined["last_refresh"] = datetime.utcnow().isoformat()
    return combined


def fetch_sales_orders_df(client: InflowClient, date_from: str = "2025-01-01") -> pd.DataFrame:
    """Sales orders with line-level COGS allocation → ready for f_i_sales-order."""
    today = datetime.now().strftime("%Y-%m-%d")
    print("  [Inflow] Fetching sales orders...")

    all_records, last_id, has_more = [], None, True
    base_params = {
        "count": 100,
        "include": (
            "lines,lines.product,lines.product.cost,customer,location,"
            "customer.pricingScheme,customer.taxingScheme,costOfGoodsSold"
        ),
        "filter[orderDate][fromDate]": date_from,
        "filter[orderDate][toDate]": today,
        "filter[isActive]": "true",
    }

    while has_more:
        params = dict(base_params)
        if last_id:
            params["after"] = last_id
        resp = client.get("/sales-orders", params)
        if resp.status_code != 200:
            print(f"  [Inflow] API error {resp.status_code}: {resp.text[:300]}")
            break
        records: list = resp.json()
        if not records:
            break
        for record in records:
            _preprocess_sales_record(record)
        all_records.extend(records)
        has_more = len(records) >= 100
        if has_more:
            last_id = records[-1].get("salesOrderId")

    print(f"  [Inflow] {len(all_records)} sales orders")
    if not all_records:
        return pd.DataFrame()

    meta_fields = [
        "salesOrderId", "orderNumber", "orderDate", "paymentStatus", "customerId",
        *[f"customFields_custom{i}" for i in range(1, 11)],
        "nonCustomerCost_value", "nonCustomerCost_isPercent",
        "total", "balance", "isCompleted", "isCancelled", "inventoryStatus",
        "isTaxInclusive", "isQuote", "exchangeRate", "exchangeRateAutoPulled",
        "cogs_value", "cogs_id", "cogs_salesOrderId", "cogs_salesOrder_id",
        "cogs_salesOrder_orderNumber", "cogs_salesOrder_orderDate",
        "pricing_scheme_name", "pricing_scheme_id", "pricing_scheme_isActive",
        "pricing_scheme_isDefault", "pricing_scheme_isTaxInclusive", "pricing_scheme_currencyId",
        "pricing_scheme_currency_name", "pricing_scheme_currency_isoCode",
        "pricing_scheme_currency_symbol", "pricing_scheme_currency_decimalPlaces",
        "pricing_scheme_currency_isSymbolFirst", "pricing_scheme_currency_decimalSeparator",
        "pricing_scheme_currency_thousandsSeparator", "pricing_scheme_currency_negativeType",
        "pricing_scheme_currency_exchangeRate", "pricing_scheme_currency_isManual",
        "pricing_scheme_productPrices_count", "pricing_scheme_productPrice_fixedMarkup",
        "pricing_scheme_productPrice_priceType", "pricing_scheme_productPrice_pricingSchemeId",
        "pricing_scheme_productPrice_id", "pricing_scheme_productPrice_unitPrice",
        "pricing_scheme_productPrice_product_name", "pricing_scheme_productPrice_product_sku",
        "pricing_scheme_productPrice_product_autoAssemble", "pricing_scheme_productPrice_product_id",
        "pricing_scheme_productPrice_product_category_name",
        "pricing_scheme_productPrice_product_category_id",
        "pricing_scheme_productPrice_product_category_isDefault",
        "pricing_scheme_productPrice_product_cost_direct",
        "pricing_scheme_productPrice_product_cost_value",
        "pricing_scheme_productPrice_product_cost_id",
        "pricing_scheme_productPrice_product_cost_productId",
        "pricing_scheme_productPrice_product_itemType",
        "salesRepTeamMemberId", "assignedToTeamMemberId",
        "salesRep_name", "salesRep_email", "salesRep_isActive", "salesRep_isInternal",
        "salesRep_canBeSalesRep", "salesRep_accessAllLocations", "salesRep_teamMemberId",
        "salesRep_accessLocationIds", "assignedTo_name", "assignedTo_email",
        "assignedTo_isActive", "assignedTo_isInternal", "assignedTo_canBeSalesRep",
        "assignedTo_accessAllLocations", "assignedTo_teamMemberId", "assignedTo_accessLocationIds",
    ]

    df = pd.json_normalize(
        all_records,
        sep="_",
        record_path=["lines"],
        meta=meta_fields,
        errors="ignore",
    )

    if "salesOrderLineId" in df.columns:
        df["line_id"] = df["salesOrderLineId"]
    elif "line_id" not in df.columns:
        df["line_id"] = df.get("salesOrderId", pd.Series(dtype=str)).astype(str) + "_" + df.index.astype(str)

    for col in ["cogs_value", "total", "subTotal", "product_cost_cost", "quantity_standardQuantity"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "subTotal" in df.columns:
        df["lineTotal"] = df["subTotal"]

    # Allocate order-level COGS proportionally by each line's share of the order subtotal
    if {"cogs_value", "subTotal", "salesOrderId"}.issubset(df.columns):
        order_line_sum = df.groupby("salesOrderId")["subTotal"].transform("sum")
        df["line_cogs_allocated"] = df["cogs_value"] * (df["subTotal"] / order_line_sum)
    else:
        df["line_cogs_allocated"] = None

    if {"product_cost_cost", "quantity_standardQuantity"}.issubset(df.columns):
        df["line_product_cost"] = df["product_cost_cost"] * df["quantity_standardQuantity"]
    else:
        df["line_product_cost"] = None

    df["last_refresh"] = datetime.utcnow().isoformat()
    return df


def fetch_customers_df(client: InflowClient) -> pd.DataFrame:
    """Customers with sales rep details → ready for d_i_customers."""
    print("  [Inflow] Fetching customers...")
    all_records = client.paginate(
        "/customers",
        {"count": 100, "include": "defaultSalesRepTeamMember"},
    )
    print(f"  [Inflow] {len(all_records)} customers")
    if not all_records:
        return pd.DataFrame()

    for customer in all_records:
        _extract_team_member(customer, customer.get("defaultSalesRepTeamMember"), "salesRep")
        cf = customer.get("customFields") or {}
        for i in range(1, 11):
            customer[f"Custom_Field_{i}"] = cf.get(f"custom{i}", "")

    df = pd.DataFrame(all_records)
    for col in ("defaultSalesRepTeamMember", "customFields"):
        if col in df.columns:
            df.drop(col, axis=1, inplace=True)
    df["last_refresh"] = datetime.utcnow().isoformat()
    return df


def fetch_locations_df(client: InflowClient) -> pd.DataFrame:
    """Locations → ready for d_i_locations."""
    print("  [Inflow] Fetching locations...")
    locations = _fetch_all_locations(client)
    print(f"  [Inflow] {len(locations)} locations")
    if not locations:
        return pd.DataFrame()

    rows = []
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address") or {}
        rows.append({
            "locationId":  loc.get("locationId"),
            "name":        loc.get("name"),
            "isActive":    loc.get("isActive"),
            "isDefault":   loc.get("isDefault"),
            "address1":    loc.get("address1") or addr.get("address1"),
            "address2":    loc.get("address2") or addr.get("address2"),
            "city":        loc.get("city")     or addr.get("city"),
            "state":       loc.get("state")    or addr.get("state"),
            "country":     loc.get("country")  or addr.get("country"),
            "postalCode":  loc.get("postalCode") or addr.get("postalCode"),
            "remarks":     loc.get("remarks")  or addr.get("remarks"),
            "addressType": loc.get("addressType") or addr.get("addressType"),
            "timestamp":   loc.get("timestamp"),
        })

    df = pd.DataFrame(rows)
    df["last_refresh"] = datetime.utcnow().isoformat()
    return df
