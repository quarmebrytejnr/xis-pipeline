# xis-pipeline

**Xero + Inflow Inventory → Supabase sync SDK**

A Python package that syncs your Xero accounting data and Inflow Cloud Inventory data into a Supabase (Postgres) database — ready for Power BI, Metabase, or any other BI tool.

```
Xero API  ─┐
           ├──► xis-pipeline ──► Supabase (Postgres) ──► Power BI
Inflow API ─┘
```

---

## Installation

```bash
pip install xis-pipeline
```

Or from source:

```bash
git clone https://github.com/quarmebrytejnr/xis-pipeline.git
cd xis-pipeline
pip install -e .
```

---

## Quick start

### 1. Set up credentials

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
INFLOW_API_KEY=...
INFLOW_COMPANY_ID=...
XERO_CLIENT_ID=...
XERO_CLIENT_SECRET=...
XERO_REFRESH_TOKEN=...
XERO_TENANT_ID=...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key
```

### 2. Create Supabase tables

Run `database/schema.sql` in your Supabase SQL editor (Dashboard → SQL Editor → New query → paste and run).

### 3. Sync

```python
from xis import InflowSync, XeroSync

InflowSync().sync()   # products, orders, customers, locations
XeroSync().sync()     # accounts, contacts, P&L
```

Or via the CLI:

```bash
xis-sync                        # sync everything
xis-sync inflow                 # all Inflow datasets
xis-sync products sales_orders  # specific Inflow targets
xis-sync xero pnl               # Xero P&L only
```

---

## Credentials reference

| Environment variable  | Where to find it |
|-----------------------|-----------------|
| `INFLOW_API_KEY`      | Inflow Cloud → Settings → Integrations → API Keys |
| `INFLOW_COMPANY_ID`   | Inflow Cloud → Settings → Integrations → API Keys |
| `XERO_CLIENT_ID`      | developer.xero.com → My Apps → your app |
| `XERO_CLIENT_SECRET`  | developer.xero.com → My Apps → your app |
| `XERO_REFRESH_TOKEN`  | See *Xero first-time setup* below |
| `XERO_TENANT_ID`      | See *Xero first-time setup* below |
| `SUPABASE_URL`        | Supabase dashboard → Settings → API |
| `SUPABASE_KEY`        | Supabase dashboard → Settings → API → `service_role` key |

---

## Xero first-time setup (OAuth2)

Xero uses OAuth2 with rotating refresh tokens.  You need to complete the auth flow once to get your initial refresh token.

1. Go to [developer.xero.com/myapps](https://developer.xero.com/myapps) and create a **Web App**.
2. Set the redirect URI to `http://localhost:5000/callback`.
3. Note your **Client ID** and **Client Secret**.
4. Open your browser and navigate to:

```
https://login.xero.com/identity/connect/authorize
  ?response_type=code
  &client_id=YOUR_CLIENT_ID
  &redirect_uri=http://localhost:5000/callback
  &scope=openid profile email accounting.transactions accounting.reports.read accounting.contacts
  &state=random_string
```

5. Log in, approve, and copy the `code` from the redirect URL.
6. Exchange the code for tokens:

```bash
curl -X POST https://identity.xero.com/connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "YOUR_CLIENT_ID:YOUR_CLIENT_SECRET" \
  -d "grant_type=authorization_code&code=YOUR_CODE&redirect_uri=http://localhost:5000/callback"
```

7. The response contains `refresh_token` and — from `GET https://api.xero.com/connections` — `tenantId`.

Store these in your `.env` and GitHub Actions secrets.  After the first sync, the SDK **automatically rotates and saves** the new refresh token to your Supabase `config` table, so you never have to update it manually again.

---

## Datasets synced

### Inflow → Supabase

| Target | Supabase table | Description |
|--------|----------------|-------------|
| `products` | `d_i_products` | Full product catalogue + overall inventory summary |
| `location_inventory` | `d_i_product-location-inventory` | Per-product inventory at each location |
| `purchase_orders` | `f_i_purchase-orders` | POs with line items |
| `sales_orders` | `f_i_sales-order` | Sales orders with line-level COGS allocation |
| `customers` | `d_i_customers` | Customer master |
| `locations` | `d_i_locations` | Warehouse / store locations |

### Xero → Supabase

| Target | Supabase table | Description |
|--------|----------------|-------------|
| `accounts` | `d_x_accounts` | Chart of accounts |
| `contacts` | `d_x_contacts` | Suppliers and customers |
| `pnl` | `f_x_pnl` | Monthly P&L report (incremental by default) |

---

## Advanced usage

### Selective sync

```python
from xis import InflowSync

sync = InflowSync()
sync.sync(targets=["products", "customers"])
```

### Explicit credentials (no .env)

```python
from xis import InflowSync, XeroSync

inflow = InflowSync(
    api_key="...",
    company_id="...",
    supabase_url="...",
    supabase_key="...",
    date_from="2024-01-01",
)

xero = XeroSync(
    client_id="...",
    client_secret="...",
    refresh_token="...",
    tenant_id="...",
    supabase_url="...",
    supabase_key="...",
)
```

### Use the fetch functions without syncing to Supabase

```python
from xis.inflow._client import InflowClient
from xis.inflow.fetchers import fetch_sales_orders_df

client = InflowClient(api_key="...", company_id="...")
df = fetch_sales_orders_df(client, date_from="2024-01-01")
print(df.head())
```

### Low-level Supabase access

```python
from xis import SupabaseClient

db = SupabaseClient()
print(db.get_sync_stats())
```

---

## GitHub Actions setup

Copy `.github/workflows/sync.yml` into your own repo (it is already included if you cloned this repo).

Add these **repository secrets** (Settings → Secrets and variables → Actions):

```
INFLOW_API_KEY
INFLOW_COMPANY_ID
XERO_CLIENT_ID
XERO_CLIENT_SECRET
XERO_REFRESH_TOKEN
XERO_TENANT_ID
SUPABASE_URL
SUPABASE_KEY
GH_PAT          ← personal access token with `secrets` write scope (for refresh token rotation)
```

The workflow runs daily at 06:00 UTC and can be triggered manually with an optional date range.

---

## Power BI connection

1. In Power BI Desktop → **Get Data** → **PostgreSQL database**.
2. Enter your Supabase host (found in Settings → Database → Connection string).
3. Connect using the database password from Supabase → Settings → Database.
4. Select the tables you need — all xis-pipeline tables are immediately queryable.

---

## Project structure

```
xis-pipeline/
├── src/xis/
│   ├── __init__.py          ← Public API: InflowSync, XeroSync, SupabaseClient
│   ├── _config.py           ← Credential loading from env
│   ├── _utils.py            ← DataFrame serialisation helpers
│   ├── cli.py               ← `xis-sync` CLI entry point
│   ├── inflow/
│   │   ├── _client.py       ← Inflow HTTP client + pagination
│   │   ├── _schemas.py      ← Column allowlists per table
│   │   ├── fetchers.py      ← fetch_*_df() functions (return DataFrames)
│   │   └── sync.py          ← InflowSync class
│   ├── xero/
│   │   ├── _client.py       ← Xero OAuth2 client + token rotation
│   │   └── sync.py          ← XeroSync class + P&L parser
│   └── db/
│       └── client.py        ← SupabaseClient wrapper
├── database/
│   └── schema.sql           ← Run once in Supabase SQL editor
├── .github/workflows/
│   └── sync.yml             ← Ready-to-use GitHub Actions workflow
├── .env.example             ← Template — copy to .env and fill in secrets
└── pyproject.toml           ← Package metadata
```

---

## License

MIT © Bright Kwame Dogbey
