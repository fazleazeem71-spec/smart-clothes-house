# Smart Clothes House — Gents

A Streamlit shop-management starter application using PostgreSQL for permanent, transactional data storage.

## Features

- Secrets-based owner password
- Inventory with SKU, category, size, color, purchase price, selling price, stock and low-stock alerts
- Multi-item bills, discounts, partial payments, stock deduction and invoice download
- Customer records and outstanding Khata balances
- Repayment history
- Expense tracking
- Stock adjustment and movement history
- Daily dashboard, date-filtered reports, CSV exports and Excel backup
- WhatsApp invoice sharing link

## Recommended deployment

### 1. Create a PostgreSQL database

Use a managed PostgreSQL provider (for example, a hosted PostgreSQL database). Keep its credentials private. Use SSL if the provider requires it. Do not use a local SQLite file for Streamlit Cloud production data because local files may not be durable across rebuilds/redeploys.

Copy the provider's SQLAlchemy-compatible connection string. Prefer a URL starting with `postgresql+psycopg://` or `postgresql://`. If your provider gives `postgres://`, change the prefix to `postgresql://`. URL-encode special characters in the username/password if required by the provider.

### 2. Upload files to GitHub

Upload `app.py`, `requirements.txt`, and this README to the root of your repository.

### 3. Set Streamlit Secrets

In Streamlit Community Cloud → your app → Settings → Secrets, add:

```toml
database_url = "postgresql+psycopg://DB_USER:DB_PASSWORD@DB_HOST:5432/DB_NAME"

[auth]
password = "REPLACE_WITH_A_LONG_UNIQUE_PASSWORD"
```

Use your actual database credentials and a long, unique password. Never commit secrets to GitHub or send them in chat. If credentials are ever exposed, rotate them.

### 4. First launch

The app creates the required tables automatically on first launch. Sign in with the password configured in Streamlit Secrets.

## Important operational notes

- This is a practical starter app, not audited accounting software. Test it with fictional products and bills before using real data.
- Back up data regularly and test restoring a backup.
- Protect the database with a strong password, provider access controls, and SSL.
- The app uses database transactions and row locks for sale/payment consistency, but a production business should still add automated tests, monitoring, user roles, rate limiting, and a formal return/void workflow.
- A bill's purchase cost is captured at sale time. Profit estimates exclude unrecorded costs, taxes, shrinkage, and accounting adjustments.
- WhatsApp sharing opens a pre-filled message; it does not send automatically. The user must confirm sending in WhatsApp.
- Do not store sensitive customer information you do not need.
