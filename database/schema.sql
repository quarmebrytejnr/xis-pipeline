-- xis-pipeline database schema
-- Run this SQL in the Supabase SQL editor to create all required tables.
-- Safe to run multiple times (uses IF NOT EXISTS / CREATE OR REPLACE).

-- ══════════════════════════════════════════════════════════════════════════════
-- XERO TABLES
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.d_x_accounts (
    "AccountID"                 text        NOT NULL,
    "Name"                      text,
    "Status"                    text,
    "Type"                      text,
    "TaxType"                   text,
    "Class"                     text,
    "EnablePaymentsToAccount"   boolean,
    "ShowInExpenseClaims"       boolean,
    "BankAccountNumber"         text,
    "BankAccountType"           text,
    "CurrencyCode"              text,
    "ReportingCode"             text,
    "ReportingCodeName"         text,
    "HasAttachments"            boolean,
    "UpdatedDateUTC"            text,
    "AddToWatchlist"            boolean,
    "Code"                      text,
    "Description"               text,
    "SystemAccount"             text,
    CONSTRAINT d_x_accounts_pkey PRIMARY KEY ("AccountID")
);
CREATE INDEX IF NOT EXISTS idx_d_x_accounts_type ON d_x_accounts("Type");

CREATE TABLE IF NOT EXISTS public.d_x_contacts (
    "ContactID"                                 text        NOT NULL,
    "ContactStatus"                             text,
    "Name"                                      text,
    "FirstName"                                 text,
    "LastName"                                  text,
    "EmailAddress"                              text,
    "Website"                                   text,
    "AccountNumber"                             text,
    "CompanyNumber"                             text,
    "BankAccountDetails"                        text,
    "DefaultCurrency"                           text,
    "IsSupplier"                                boolean,
    "IsCustomer"                                boolean,
    "HasAttachments"                            boolean,
    "HasValidationErrors"                       boolean,
    "UpdatedDateUTC"                            text,
    "ContactGroups"                             jsonb,
    "ContactPersons"                            jsonb,
    "SalesTrackingCategories"                   text,
    "Balances.AccountsReceivable.Outstanding"   text,
    "Balances.AccountsReceivable.Overdue"       text,
    "Balances.AccountsPayable.Outstanding"      text,
    "Balances.AccountsPayable.Overdue"          text,
    "BatchPayments.BankAccountNumber"           text,
    "BatchPayments.BankAccountName"             text,
    "BatchPayments.Details"                     text,
    "BatchPayments.Code"                        text,
    "BatchPayments.Reference"                   text,
    "LastUpdated"                               text,
    CONSTRAINT d_x_contacts_pkey PRIMARY KEY ("ContactID")
);
CREATE INDEX IF NOT EXISTS idx_d_x_contacts_name ON d_x_contacts("Name");

CREATE TABLE IF NOT EXISTS public.f_x_pnl (
    id              bigserial   NOT NULL,
    "ReportDate"    date        NOT NULL,
    "Section"       text,
    "SubSection"    text,
    "RowType"       text,
    "Account"       text,
    "AccountID"     text,
    "Column_1"      text,
    unique_key      text,
    CONSTRAINT f_x_pnl_unique UNIQUE ("ReportDate", "Section", "Account")
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_f_x_pnl_unique_key ON f_x_pnl(unique_key);
CREATE INDEX IF NOT EXISTS idx_f_x_pnl_date    ON f_x_pnl("ReportDate");
CREATE INDEX IF NOT EXISTS idx_f_x_pnl_section ON f_x_pnl("Section");

-- ══════════════════════════════════════════════════════════════════════════════
-- INFLOW TABLES
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.d_i_products (
    "productId"         text        NOT NULL,
    "sku"               text,
    "name"              text,
    "description"       text,
    "isActive"          boolean,
    "itemType"          text,
    "categoryId"        text,
    "cost_value"        numeric,
    "productCostId"     text,
    "last_refresh"      text,
    -- quantity columns
    "quantityOnHand"                        numeric,
    "quantityOnOrder"                       numeric,
    "quantityOnPurchaseOrder"               numeric,
    "quantityOnWorkOrder"                   numeric,
    "quantityOnTransferOrder"               numeric,
    "quantityReserved"                      numeric,
    "quantityReservedForSales"              numeric,
    "quantityReservedForManufacturing"      numeric,
    "quantityReservedForTransfers"          numeric,
    "quantityReservedForBuilds"             numeric,
    "quantityAvailable"                     numeric,
    "rawQuantityAvailable"                  numeric,
    "quantityPicked"                        numeric,
    "quantityInTransit"                     numeric,
    "quantityBuildable"                     numeric,
    "quantityAnticipated"                   numeric,
    "quantityCommitted"                     numeric,
    -- custom fields
    "Custom_Field_1"    text, "Custom_Field_2"  text, "Custom_Field_3"  text,
    "Custom_Field_4"    text, "Custom_Field_5"  text, "Custom_Field_6"  text,
    "Custom_Field_7"    text, "Custom_Field_8"  text, "Custom_Field_9"  text,
    "Custom_Field_10"   text,
    CONSTRAINT d_i_products_pkey PRIMARY KEY ("productId")
);

CREATE TABLE IF NOT EXISTS public."d_i_product-location-inventory" (
    id                                      text        NOT NULL,
    "productId"                             text,
    "locationId"                            text,
    "location_name"                         text,
    "quantityOnHand"                        numeric,
    "quantityOnOrder"                       numeric,
    "quantityOnPurchaseOrder"               numeric,
    "quantityAvailable"                     numeric,
    "quantityReserved"                      numeric,
    "quantityReservedForSales"              numeric,
    "quantityReservedForManufacturing"      numeric,
    "quantityReservedForTransfers"          numeric,
    "quantityReservedForBuilds"             numeric,
    "quantityPicked"                        numeric,
    "quantityInTransit"                     numeric,
    "quantityBuildable"                     numeric,
    "quantityAnticipated"                   numeric,
    "last_refresh"                          text,
    CONSTRAINT "d_i_product-location-inventory_pkey" PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS "idx_d_i_pli_product" ON "d_i_product-location-inventory"("productId");
CREATE INDEX IF NOT EXISTS "idx_d_i_pli_location" ON "d_i_product-location-inventory"("locationId");

CREATE TABLE IF NOT EXISTS public."f_i_purchase-orders" (
    line_id             text        NOT NULL,
    "purchaseOrderId"   text,
    "orderNumber"       text,
    "orderDate"         text,
    "product_id"        text,
    "product_name"      text,
    "product_sku"       text,
    "quantity_ordered"  numeric,
    "quantity_received" numeric,
    "quantity_returned" numeric,
    "unit_price"        numeric,
    "line_total"        numeric,
    "total"             numeric,
    "paymentStatus"     text,
    "inventoryStatus"   text,
    "isCancelled"       boolean,
    "isCompleted"       boolean,
    "vendorId"          text,
    "locationId"        text,
    "location_name"     text,
    "last_refresh"      text,
    CONSTRAINT "f_i_purchase-orders_pkey" PRIMARY KEY (line_id)
);
CREATE INDEX IF NOT EXISTS "idx_f_i_po_order_id"   ON "f_i_purchase-orders"("purchaseOrderId");
CREATE INDEX IF NOT EXISTS "idx_f_i_po_order_date" ON "f_i_purchase-orders"("orderDate");

CREATE TABLE IF NOT EXISTS public."f_i_sales-order" (
    line_id             text        NOT NULL,
    "salesOrderId"      text,
    "orderNumber"       text,
    "orderDate"         text,
    "customerId"        text,
    "productId"         text,
    "product_name"      text,
    "product_sku"       text,
    "unitPrice"         numeric,
    "quantity_standardQuantity" numeric,
    "lineTotal"         numeric,
    "total"             numeric,
    "subTotal"          numeric,
    "balance"           numeric,
    "paymentStatus"     text,
    "inventoryStatus"   text,
    "isCancelled"       boolean,
    "isCompleted"       boolean,
    "cogs_value"        numeric,
    "line_cogs_allocated" numeric,
    "line_product_cost" numeric,
    "last_refresh"      text,
    CONSTRAINT "f_i_sales-order_pkey" PRIMARY KEY (line_id)
);
CREATE INDEX IF NOT EXISTS "idx_f_i_so_order_id"    ON "f_i_sales-order"("salesOrderId");
CREATE INDEX IF NOT EXISTS "idx_f_i_so_order_date"  ON "f_i_sales-order"("orderDate");
CREATE INDEX IF NOT EXISTS "idx_f_i_so_customer_id" ON "f_i_sales-order"("customerId");

CREATE TABLE IF NOT EXISTS public.d_i_customers (
    "customerId"        text        NOT NULL,
    "name"              text,
    "companyName"       text,
    "email"             text,
    "phone"             text,
    "city"              text,
    "state"             text,
    "country"           text,
    "isActive"          boolean,
    "last_refresh"      text,
    CONSTRAINT d_i_customers_pkey PRIMARY KEY ("customerId")
);

CREATE TABLE IF NOT EXISTS public.d_i_locations (
    "locationId"        text        NOT NULL,
    "name"              text,
    "isActive"          boolean,
    "isDefault"         boolean,
    "address1"          text,
    "city"              text,
    "state"             text,
    "country"           text,
    "postalCode"        text,
    "last_refresh"      text,
    CONSTRAINT d_i_locations_pkey PRIMARY KEY ("locationId")
);

-- ══════════════════════════════════════════════════════════════════════════════
-- SHARED / INFRA TABLES
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.config (
    key         text        NOT NULL,
    value       text        NOT NULL,
    updated_at  timestamptz DEFAULT now(),
    CONSTRAINT config_pkey PRIMARY KEY (key)
);

CREATE TABLE IF NOT EXISTS public.sync_log (
    id              bigserial   NOT NULL,
    sync_type       text        NOT NULL,
    status          text        NOT NULL,
    records_synced  integer     DEFAULT 0,
    error_message   text,
    started_at      timestamptz DEFAULT now(),
    completed_at    timestamptz,
    duration_seconds integer,
    CONSTRAINT sync_log_pkey PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS idx_sync_log_type ON sync_log(sync_type);
CREATE INDEX IF NOT EXISTS idx_sync_log_status ON sync_log(status);
