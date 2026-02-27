# Expense Tracker Backend

Minimal Django + DRF microservice for the Expense Tracker app.

## Stack
- Python 3.12
- Django 4.2
- Django REST Framework
- SimpleJWT auth
- SQLite (MVP)

## Important SQLite Runtime Note
If deployed to Cloud Run with SQLite on the container filesystem (for example `/tmp/expense-tracker.sqlite3`), data is ephemeral:
- each instance has its own local filesystem
- restarts or scale events can lose local DB state

For production persistence, migrate to Postgres/Cloud SQL.
The deploy workflow is configured for Cloud SQL (Postgres), following the same pattern as the reference backend.

## Environment
Copy `.env.example` to `.env` and adjust values.

## Local run
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py rundev
```

## Docker run
```bash
docker build -t expense-tracker-backend .
docker run --rm -p 8080:8080 --env-file .env expense-tracker-backend
```

## Auth endpoints
- `POST /api/v1/auth/register/`
- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/refresh/`
- `POST /api/v1/auth/logout/`
- `GET /api/v1/auth/me/`

## Expense endpoints
- `GET|POST /api/v1/people/`
- `GET|PATCH|DELETE /api/v1/people/{id}/` (DELETE soft-deactivates `isActive`)
- `GET|POST /api/v1/items/`
- `GET|PATCH|DELETE /api/v1/items/{id}/`
- `GET|POST /api/v1/payments/?month=YYYY-MM&personId=<uuid>`
- `GET|PATCH|DELETE /api/v1/payments/{id}/`
- `GET|POST /api/v1/ledger/?entityType=...&entityId=...`
- `GET|PATCH /api/v1/settings/me/`
- `GET /api/v1/health/`

## Frontend integration
- Base URL env in React app: `VITE_API_BASE_URL=http://localhost:8000/api/v1`
- Auth header: `Authorization: Bearer <access_token>`

Payload keys match frontend camelCase types from `src/types.ts`, including:
- `people`: `{ id, name, isActive, createdAt, updatedAt }`
- `items`: nested `allocations` with `{ personId, value }`
- `payments`: `{ personId, month, amountPaid, status, paidAt?, method?, notes? }`
- `ledger`: `{ ts, actor, entityType, entityId, action, diff }`

## Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

## Cloud Run + Cloud SQL Variables
Set these GitHub repository variables/secrets for `develop`, `stage`, and `main` deploys:
- Variables: `CLOUDSQL_INSTANCE_*`, `DB_NAME_*`, `DB_USER_*`, `DB_PORT_*`
- Secrets: `DB_PASSWORD_*`, `SECRET_KEY`, `JWT_SIGNING_KEY`, `GCP_SA_KEY`
