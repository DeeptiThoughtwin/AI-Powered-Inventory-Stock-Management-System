# AI-Powered-Inventory-Stock-Management-System# AI-Powered Inventory & Stock Management System

A web app for small shops and warehouses. It tracks products, suppliers, purchases, sales,
returns and every stock change, warns about low stock, shows sales analytics, forecasts demand,
recommends reorders and explains the numbers in plain language using AI.

**Principle:** the backend does all stock and money calculations. AI only explains numbers the
backend has already calculated. It cannot change stock or place orders.

## Contents

1. [Tech stack](#tech-stack)
2. [Project structure](#project-structure)
3. [Setup](#setup)
4. [Environment variables](#environment-variables)
5. [Tests](#tests)
6. [Features](#features)
7. [API documentation](#api-documentation)
8. [Business rules](#business-rules)
9. [Assumptions](#assumptions)
10. [Screenshots](#screenshots)
11. [Troubleshooting](#troubleshooting)

## Tech stack

- Backend: Python, FastAPI, SQLAlchemy, Pydantic, PostgreSQL, Alembic
- Frontend: React (Vite)
- AI: Google Gemini
- Tests: Pytest

## Project structure

```
.
├── backend/
│   ├── main.py            API endpoints and business logic
│   ├── models.py          Database tables
│   ├── database.py        Database connection
│   ├── setup_env.py       Creates the .env file by asking questions
│   ├── seed_history.py       Optional sample data
│   └── tests/             Automated tests
├── frontend/
│   └── src/               React pages (Products, Suppliers, Purchases, Sales, ...)
├── alembic/               Database migrations
├── docs/screenshots/      Screenshots used in this README
├── .env.example           Template for the settings file
└── requirements.txt
```

## Setup

You need Python 3.10 or newer, Node.js 18 or newer, and PostgreSQL.

1. Create an empty PostgreSQL database, for example:

```bash
createdb inventory_db
```

2. Install the backend:

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create the `.env` file. Choose one way:

   - **Automatic:** run the setup script and answer the questions. It writes the file and checks
     the database connection.

     ```bash
     python backend/setup_env.py
     ```

   - **Manual:** copy `.env.example` to `.env` and fill in the values (see
     [Environment variables](#environment-variables)).

4. Create the tables (migrations):

```bash
alembic upgrade head
```

   If your database already has these tables, run `alembic stamp head` instead.

5. Optional sample data (empty database only):

```bash
python backend/seed_data.py
```

6. Start the backend (API docs at http://127.0.0.1:8001/docs):

```bash
uvicorn backend.main:app --reload --port 8001
```

   If you get `No module named 'database'`, use
   `uvicorn --app-dir backend main:app --reload --port 8001`.

7. Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

   Open http://127.0.0.1:5173. The backend address is set at the top of `frontend/src/api.js`.

## Environment variables

Settings are read from a `.env` file in the `backend` folder or the project root. Never commit
the real `.env` file. Only `.env.example` is shared.

| Variable | Required | Purpose | Example |
| --- | --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL connection string | `postgresql://user:password@localhost:5432/inventory_db` |
| `GEMINI_API_KEY` | No | Needed only for the "AI summary" and "Explain with AI" buttons | `CHANGE_ME` |
| `GEMINI_MODEL` | No | Overrides the default Gemini model | `gemini-3.5-flash-lite` |

Notes:

- If the database password contains special characters such as `@`, `#` or `/`, they must be
  URL-encoded (`@` becomes `%40`). The setup script does this for you.
- Without an AI key everything else works. The AI buttons show "AI is not configured".
- If `database.py` in your copy reads separate variables instead of `DATABASE_URL`, list those
  names in `.env.example` instead.

## Tests

```bash
cd backend
pip install pytest httpx
pytest -v
```

The tests run on a temporary in-memory database and never touch your data. They cover stock
increase and decrease, blocked sales, no negative stock, all-or-nothing multi-product sales,
history consistency, returns, purchase orders, validation rules and low-stock alerts. The trend
and forecast endpoints rely on PostgreSQL date handling, so they are checked in the running app.

## Features

- Products: create, edit, search, filter, deactivate, supplier link, stock value and status
- Suppliers: records (company, contact person, email, phone, address, lead time), products
  supplied, purchase history, delete
- Purchases and sales with several products per transaction, exact totals, stock checks
- Returns and manual stock adjustments (a reason is always required)
- Inventory history for every stock change, with a running balance and a consistency check
- Low-stock alerts on the dashboard, with "create purchase order"
- Sales analytics: totals, best and slow sellers, trends, filters by date, product and category
- Unusual activity: demand spikes, sales drops and stock that does not match its history
- Demand forecast (moving average) compared with actual sales
- Reorder recommendations with days of stock left, order-by date and quantities already on order
- Purchase orders: created only after user approval, stock changes only when received
- AI insights built from calculated metrics

## API documentation

Interactive documentation with a "Try it out" button is available at `/docs` while the backend
is running (http://127.0.0.1:8001/docs). The tables below summarise every endpoint.

### Conventions

- Requests and responses are JSON.
- Errors always look like `{"detail": "message"}`.

| Status | Meaning |
| --- | --- |
| 200 | Success |
| 400 | A business rule failed (for example insufficient stock) |
| 404 | The product, supplier, sale or order was not found |
| 409 | Conflict (for example duplicate SKU, or a record that cannot be deleted) |
| 422 | The request body is invalid (missing or badly formatted field) |
| 502 / 503 | The AI service is not configured or is unavailable |

### Products

| Method and path | Purpose |
| --- | --- |
| `GET /products` | List products. Filters: `search`, `category`, `supplier_id`, `low_stock_only`, `include_inactive` |
| `POST /products` | Create a product (opening stock is written to the history) |
| `GET /products/{id}` | Get one product |
| `PUT /products/{id}` | Edit a product. If `current_stock` changes, `stock_change_reason` is required |
| `DELETE /products/{id}` | Delete a product (blocked if it has sales, purchases or history) |
| `PATCH /products/{id}/activate` | Make a product active again |
| `PATCH /products/{id}/deactivate` | Hide a product without deleting it |
| `PUT /products/{id}/supplier` | Set or remove the supplier |

### Suppliers

| Method and path | Purpose |
| --- | --- |
| `GET /suppliers` | List suppliers |
| `POST /suppliers` | Create a supplier (name must be unique, ignoring case) |
| `GET /suppliers/{id}` | Get one supplier |
| `PUT /suppliers/{id}` | Edit a supplier |
| `DELETE /suppliers/{id}` | Delete a supplier. Blocked while it has active products or purchase history. Deactivated products are unlinked automatically |
| `GET /suppliers/{id}/products` | Products supplied by this supplier |
| `GET /suppliers/{id}/purchases` | Purchase history, purchase count and total spent |

### Purchases and sales

| Method and path | Purpose |
| --- | --- |
| `POST /purchases-bulk` | Purchase several products from one supplier in one request |
| `GET /purchases-history` | Purchases grouped by reference |
| `POST /purchases`, `GET /purchases`, `GET/PUT/DELETE /purchases/{id}` | Single-product purchase CRUD. Editing or deleting corrects the stock |
| `POST /sales-bulk` | Sell several products in one request |
| `GET /sales-history` | Sales grouped by reference |
| `POST /sales`, `GET /sales`, `GET/PUT/DELETE /sales/{id}` | Single-product sale CRUD. Editing or deleting corrects the stock |

### Returns, adjustments and history

| Method and path | Purpose |
| --- | --- |
| `POST /returns` | Customer return: stock goes up, limited to the units sold |
| `POST /products/{id}/adjust-stock` | Manual correction with a required reason |
| `GET /products/{id}/movements` | Stock history of one product |
| `GET /movements` | All stock history. Filters: `movement_type`, `product_id`, `limit` |
| `GET /analytics/stock-consistency` | Checks that the history total equals `current_stock` for every product |

### Alerts, analytics, forecast and reorder

| Method and path | Purpose |
| --- | --- |
| `GET /alerts/low-stock` | Products at or below their minimum stock |
| `GET /analytics/summary` | Product count, units in stock, stock value, low-stock count |
| `GET /analytics/sales-summary` | Total sales, units and transactions (filters: dates, product, category) |
| `GET /analytics/sales-trend` | Sales per day |
| `GET /analytics/best-selling` | Top products by units sold |
| `GET /analytics/slow-moving` | Products that sell least |
| `GET /analytics/product-trends` | Last `days` vs the `days` before, plus days since last sale |
| `GET /analytics/anomalies` | Sales spikes, sales drops and stock mismatches |
| `GET /analytics/forecast/{id}` | Moving-average demand forecast for one product |
| `GET /reorder/recommendations` | What to reorder, how much, and by when |

### Purchase orders

| Method and path | Purpose |
| --- | --- |
| `POST /purchase-orders` | Approve a purchase order. Does not change stock |
| `GET /purchase-orders` | List purchase orders |
| `POST /purchase-orders/{id}/receive` | Goods arrived: adds the stock and closes the order. Works once per order |

### AI and insights

| Method and path | Purpose |
| --- | --- |
| `GET /insights` | Rule-based summary, no AI needed |
| `POST /insights/ai` | Written shop report generated from the calculated metrics |
| `POST /analytics/forecast/{id}/explain` | Plain-language explanation of one forecast |

### Examples

Sell two products in one request:

```http
POST /sales-bulk
{
  "items": [
    { "product_id": 1, "quantity": 2, "unit_price": 80 },
    { "product_id": 4, "quantity": 1, "unit_price": 1300 }
  ]
}
```

```json
{ "reference": "SALE-3F9A1C20", "lines": 2, "total_amount": 1460.0 }
```

Edit a product and change its stock (the reason is required because the stock changes):

```http
PUT /products/5
{
  "sku": "WEBCAM-001", "name": "Webcam", "category": "Electronics",
  "purchase_price": 900, "selling_price": 1300,
  "current_stock": 12, "minimum_stock": 3, "supplier_id": 2,
  "stock_change_reason": "Recount after stock check"
}
```

Record a customer return:

```http
POST /returns
{ "product_id": 5, "quantity": 1, "reason": "Faulty item" }
```

```json
{ "product_id": 5, "current_stock": 13 }
```

Receive a purchase order:

```http
POST /purchase-orders/7/receive
```

```json
{ "order_id": 7, "status": "received", "current_stock": 40, "purchase_reference": "PO-7" }
```

Error example:

```json
{ "detail": "Insufficient stock. Available: 3" }
```

## Business rules

- Stock can never go below zero. The API checks it, rows are locked during updates, and the
  database has a check constraint.
- Every stock change writes a history row (product, change, type, reference, time, reason).
- Changing stock from the product form or the adjustment endpoint always needs a reason.
- A multi-product sale or purchase is saved completely or not at all.
- SKUs are unique ignoring case. Prices must be above zero with at most 2 decimals.
- Selling price cannot be below the purchase cost.
- Deactivated products cannot be bought or sold.
- Returns cannot exceed the units sold.
- A purchase order can be received only once.
- A supplier with active products or purchase history cannot be deleted.
- Totals are calculated on the server with exact decimal maths.

## Assumptions

- Safety stock is the product's minimum stock level. If it is 0, 5 is used.
- A product without a supplier is assumed to have a 7-day lead time.
- Reorder quantity = expected demand during the lead time + safety stock - stock - quantity
  already on order. Demand is the average daily sales over the last 14 days (adjustable).
- "When to reorder" is shown as the order-by date together with the stock-out date and the
  earliest delivery date. Recommended products need ordering now.
- Customer returns add stock back and are logged, and are limited to the units sold. They do
  not reduce reported sales totals.
- A purchase order is approved when the user creates it. Receiving it books a normal purchase
  at the product's purchase cost.
- Purchase history is kept for accounting, so suppliers with purchases are not deleted.
- Money is shown as plain numbers in the app. The AI text uses Indian rupees.
- When the AI buttons are used, product names and calculated figures are sent to Google Gemini.
  No other data is sent, and the AI cannot change anything.
- There is no login or user management.

## Screenshots

### Dashboard
![Dashboard](docs/screenshots/dashboard-1.png)

### Low-stock alerts
![Low-stock alerts](docs/screenshots/low-stock-alerts.png)

### Products
![Products](docs/screenshots/products.png)

### Suppliers
![Suppliers](docs/screenshots/suppliers.png)

### Purchases
![Purchases](docs/screenshots/purchases.png)

### Sales
![Sales](docs/screenshots/sales.png)

### Inventory history
![Inventory history](docs/screenshots/inventry-history.png)

### Forecast and reorder
![Forecast and reorder](docs/screenshots/forcast_%26_reorder.png)

### AI summary
![AI summary](docs/screenshots/ai_summary.png)

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `No module named 'database'` | Start with `uvicorn --app-dir backend main:app --reload --port 8001` |
| Pages show "Not Found" after saving | The frontend and backend are from different versions, or uvicorn was not restarted |
| AI buttons say "AI is not configured" | Add `GEMINI_API_KEY` to `.env` and restart the backend |
| Cannot connect to the database | Check `DATABASE_URL`, that PostgreSQL is running, and that the database exists |
| `pytest` collects 0 tests | The file name must be exactly `test_*.py` with no trailing space |