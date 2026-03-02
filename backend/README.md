# Bank Management System Backend

This Django-based backend implements a simple banking system with multi-factor authentication, audit logging, accounts, transactions, and a loan module introduced in Phase 4.

## Setup

1. Create and activate virtualenv (project includes `.venv`).
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Run migrations:
   ```bash
   python manage.py migrate
   ```
4. Create superuser if needed:
   ```bash
   python manage.py createsuperuser
   ```
5. Start development server:
   ```bash
   python manage.py runserver
   ```

## Testing

Individual apps have tests. Run all known tests with:
```bash
python manage.py test accounts banking loans audit core
```

## Authentication

- Session-based login via `/` with email/password and optional OTP/TOTP.
- REST API supports JWT (`/api/token/`) and session auth for browser clients.
- Multi-factor configured per user (`mfa_enabled` / `mfa_secret`).

## Loan API (Phase 4)

Loan endpoints are mounted under `/api/loans/` and require authentication.

| Method | Path                         | Description                                  | Permissions        |
|--------|------------------------------|----------------------------------------------|--------------------|
| GET    | `/api/loans/`                | List loans (own for customers, all for staff/admin/teller) | authenticated      |
| POST   | `/api/loans/`                | Apply for a new loan (customer)              | authenticated      |
| GET    | `/api/loans/<pk>/`           | Retrieve details of a loan                   | owner/staff/admin  |
| PATCH  | `/api/loans/<pk>/approve/`   | Approve or reject a loan (admin/staff only)  | admin/staff        |
| POST   | `/api/loans/<pk>/repay/`     | Create a repayment transaction               | owner/staff/admin  |

Loan objects contain `amount`, `interest_rate`, `duration_months`, `status`, and calculation helpers such as `total_payable_amount()`, `remaining_balance()`, and `generate_schedule()`.

### Frontend URLs

- `/loans/` – list of user loans (or all loans for staff)
- `/loans/<pk>/` – loan detail page with repayment form, schedule and history.

## Phase 4 Status

All features described in Phase 4 are implemented and tested. Remaining tasks:

- Add any further frontend polish or additional business features.

Feel free to extend with notification, statements, or export capabilities.

## Phase 5 – Notifications & Extras

Phase 5 is considered complete once the above features are working and tested.  Feel free to add exports, PDF statements, or other enhancements.

## Phase 6 – Reporting & Utilities

In Phase 6 we've added advanced reporting and exporting tools:

* **Transaction search** – customers can filter by account, type, date range, and amount via the API (`/api/transactions/search/`) or the new "Search Transactions" page on the frontend.
* **Statement export** – any statement view now has an "Export CSV" button; the API endpoint `/api/statements/export/` returns a downloadable CSV.
* **Dashboard statistics** – an API endpoint (`/api/stats/`) provides aggregated totals used to enrich the dashboard with deposit and withdrawal summaries.

### FX rate updates

A management command `python manage.py update_fx_rates` can be run (e.g. via cron) to pull the latest exchange rates from a public API and update the `Currency` records.  Rates from currencies not already present are ignored.  No API key is required currently but the command can be modified to use a paid service.

These capabilities make it easier to analyze activity and produce reports for users and administrators.

Additionally Phase 7 (multi-currency) introduces:

* **Multi‑currency accounts** – each account may now specify a currency (USD default) and transfers between different currencies automatically convert using configurable exchange rates.  A new `Currency` model holds rate information and is seeded with common currencies.  The account opening form/API accepts a currency choice and all views/templates display the currency code.
* Currency conversion logic is applied in the `/accounts/<pk>/transfer/` view, and API serializers expose `currency` on accounts.
* Tests cover cross‑currency transfers to verify correct conversion.

You can continue extending Phase 7 with dynamic rate updates, currency formatting, or internationalization.

### External payment gateway integration

A simple gateway wrapper is provided in `banking/gateway.py` along with a
consumer view at `/api/payments/charge/`.  Configure the URL and API key in
`settings.py` or via environment variables:

```python
GATEWAY_API_URL = "https://sandbox.example.com/charge"  # replace with your provider
GATEWAY_API_KEY = "sk_test_..."
```

The view expects JSON with ```amount```, ```currency``` (default ``"USD"``),
and ```source``` (card token or similar).  Errors from the gateway are
translated into HTTP 400 responses.  Tests use `unittest.mock.patch` to mock
`requests.post`, so you can run the suite without contacting a real service.

At deployment time replace the dummy URL with the real endpoint and make sure
your gateway credentials are kept secret.

## Deployment & Performance

A basic Docker configuration is provided for containerized deployment.  The
`backend/Dockerfile` installs dependencies, collects static files and runs the
app under **gunicorn**.  Use the top-level `docker-compose.yml` to launch a
PostgreSQL database alongside the web service during development or in a CI
pipeline.  An example environment file (`backend/.env.example`) shows the
important environment variables (secret key, debug flag, allowed hosts, and
`DATABASE_URL`).

Key points for production readiness:

1. **Settings** – the project now reads `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`,
   and `DATABASE_URL` from environment variables.  Keep `DEBUG=False` and never
   commit a real secret key.  Use `dj-database-url` to configure the database.
2. **Static files** – `whitenoise` middleware is installed enabling Django to
   serve compiled static assets directly in simple deployments.  Run
   `python manage.py collectstatic` as part of your build.
3. **Database indices** – models have been indexed for common query patterns
   (`Transaction` has indexes on ``account`` and ``created_at``, ``RecurringTransfer``
   uses an index on ``next_transfer_date``).  New migrations are included.
4. **Caching & optimization** – the dashboard stats endpoint caches results for
   60 seconds, and querysets now use ``select_related`` to reduce database hits.
   Configure a real cache backend such as Redis in production by setting
   `REDIS_URL` or overriding the `CACHES` setting.
5. **Gunicorn** – the `gunicorn` package is added to requirements; the Dockerfile
   and Procfile launch the app with gunicorn for better concurrency.

Additional steps you may take:

* Add a reverse proxy (nginx) and SSL termination.
* Configure log collection and error monitoring (Sentry, etc.).
* Run periodic `python manage.py collectstatic` and `migrate` during build.

With these pieces in place the codebase is prepared for scalable deployment and
faster operation under heavy load.

## Summary of Implemented Phases

### Phase 1–3: Core Banking, Security, Accounts
- Basic account opening, deposits, withdrawals, transfers
- User authentication with MFA/TOTP
- Audit logging of all operations
- Session and JWT-based API access

### Phase 4: Loan Module  
- Loan applications and approvals
- Loan schedules with payment tracking
- Loan reminders sent via email

### Phase 5: Notifications & Recurring Transfers
- Low-balance alerts
- Recurring scheduled transfers with cron job
- Monthly statements

### Phase 6: Reporting & Analytics
- Transaction search with filters  
- CSV export of statements
- Dashboard statistics endpoint

### Phase 7: Multi-Currency & Advanced Features
- Multi-currency accounts with real-time exchange rates
- Currency conversion on transfers
- PDF statement export
- Scheduled monthly reports via email
- Management command for FX rate updates
- Template filter for currency formatting

### Phase 8: Production Readiness & Payment Integration
- **External payment gateway** integraction (`/api/payments/charge/`) with pluggable design
- **Query optimization**: database indices on `Transaction(account, created_at)` and `RecurringTransfer(next_transfer_date)`
- **Query prefetching**: `select_related('account')` in statement/search querysets to reduce database hits
- **Results caching**: stats endpoint cached for 60 seconds using Django's caching framework
- **Docker containerization** with `Dockerfile` and `docker-compose.yml` for PostgreSQL integration
- **Environment-based configuration**: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `DATABASE_URL` read from env vars or `.env` file
- **Static file serving**: Whitenoise middleware for serving compiled assets directly from Django
- **Production application server**: Gunicorn with Procfile for Heroku-style deployments
- **Deployment documentation**: Example `.env.example` with all configurable settings

## Performance & Scalability Features

1. **Database Indices**
   - Transaction queries indexed by account and creation date for efficient filtering
   - Recurring transfer queries indexed by next transfer date for daily job execution
   - Applied via migration `0005_recurringtransfer_banking_rec_next_tr_05e4f7_idx_and_more.py`

2. **Query Optimization**
   - Statement API uses `select_related('account')` to eliminate N+1 queries when rendering transaction lists
   - Search and export endpoints similarly optimized
   - Serializers avoid unnecessary related object lookups

3. **Caching**
   - Stats endpoint results cached in memory for 60 seconds
   - Cache backend configurable via environment (`REDIS_URL` for production)
   - Default local memory cache suitable for development

4. **Static Asset Handling**
   - Whitenoise middleware compresses and serves static files directly
   - `python manage.py collectstatic` prepares assets for deployment
   - No need for separate CDN for small/medium deployments

## Deployment Instructions

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py makemigrations && python manage.py migrate

# Run development server
python manage.py runserver
```

### Using Docker Compose (Local or CI/CD)
```bash
# Build and start containers
docker-compose up --build

# Run migrations inside web container
docker-compose exec web python manage.py migrate

# Access at http://localhost:8000
```

### Production Deployment (Heroku Example)
```bash
# Copy and customize environment file
cp backend/.env.example .env
# Edit .env with real SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, DATABASE_URL

# Deploy to Heroku
git add . && git commit -m "Phase 8: Production Ready"
git push heroku main

# View logs
heroku logs --tail
```

### Environment Variables

Key settings configurable via environment:

```python
SECRET_KEY          # Django secret key (NEVER hardcode in production)
DEBUG               # Set to 'False' in production
ALLOWED_HOSTS       # Comma-separated list of allowed domains
DATABASE_URL        # Database connection string (postgres://, sqlite://, etc.)
GATEWAY_API_URL     # External payment processor endpoint
GATEWAY_API_KEY     # API credentials for payment processor
```


Phase 5 adds several convenience and reporting features:

* **Recurring transfers** – schedule automatic money movement every N days.  Customers can create and view their recurring instructions via the frontend or API (`/api/recurring-transfers/`).  A management command (`python manage.py process_recurring_transfers`) runs due transfers.
* **Monthly statements** – pull transaction history by month/year with `/api/statements/` or the dashboard link.  Frontend users can filter on the "Statements" page.
* **Low‑balance alerts** – emails are sent when a withdrawal drops an account below `LOW_BALANCE_THRESHOLD` (configure in `settings.py`).
* **Loan reminders** – a command (`python manage.py send_loan_reminders`) emails customers when their next payment is due.

The frontend includes pages for recurring transfers and statements linked from the dashboard.

### Additional Notes

Run the full test suite to verify everything:

```bash
python manage.py test accounts banking loans audit core
```

Phase 5 is considered complete once the above features are working and tested.  Feel free to add exports, PDF statements, or other enhancements.