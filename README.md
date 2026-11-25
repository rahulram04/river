# River

River is a **play-credit-only prediction market for Jira work items**. Members buy and sell binary YES/NO shares on whether a Jira issue will be in a Jira **Done-category status at a specific UTC deadline**. An LMSR market maker updates the implied probability after each trade. Each outstanding winning share pays one nonredeemable play credit after the deadline; there are no deposits, withdrawals or cash prizes.

**Project status:** functional development MVP, not production-hardened. The mock Jira mode has sample issues and never contacts the real Jira site. It does **not** measure individual productivity or guarantee calibrated forecasts.

## Quick start (Docker)

Prerequisites: Docker Engine/Desktop with Compose.

```bash
git clone https://github.com/rahulram04/river.git
cd river
docker compose up --build -d
# Create the first admin. You will be prompted for a password (12+ characters).
docker compose exec api python -m app.seed --admin-email you@example.com
```

Then visit [http://localhost:3000](http://localhost:3000) for the app and [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API documentation.

Log in with the admin account you just created. On the **Admin** page, create a market using mock `KAN-1`, `KAN-2`, `KAN-3`, or `KAN-4`, a future deadline, and a liquidity value (start with 10). A co-founder can register their own account at `/register`; every account gets exactly 1,000 play credits. Both users can obtain quotes and execute bounded trades. The reconciliation worker closes and settles due markets using mock issue histories. No actual Jira credentials are needed for this demo.

Mock fixtures:

| Key | Sample behavior |
| --- | --- |
| `KAN-1` | In progress, no history, resolves NO after cutoff |
| `KAN-2` | Done since Nov 15, 2026, resolves YES for later cutoffs |
| `KAN-3` | Done Nov 15, reopened Nov 16, resolves depending on cutoff |
| `KAN-4` | Done transition Nov 20, resolves depending on cutoff |

In mock mode these are **simulated issue histories**, not your team's actual Jira issues. To test immediate settlement without waiting for a future deadline, use the automated backend test suite or create a near-term deadline, make trades, and wait for the 30-second reconciliation polling interval.

Stop with `docker compose down`. Data remains in the `river_postgres` named volume. `docker compose down -v` **deletes local database data**.

## Run without Docker (macOS / Homebrew Python)

The backend supports SQLite for a simple **single-user/local development environment**. PostgreSQL is required for concurrency guarantees and team use.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Default DATABASE_URL is sqlite:///./river-dev.db
alembic upgrade head
python -m app.seed --admin-email you@example.com
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open `http://localhost:3000`. Virtual environments avoid `externally-managed-environment` errors on Homebrew-managed Python. Do **not** use `pip --break-system-packages`.

The full local PostgreSQL workflow is also supported by setting `DATABASE_URL=postgresql+psycopg://...` and running `alembic upgrade head` in the backend directory.

## Authentication

Users register with email and a password of at least 12 characters. Passwords use Argon2. Session cookies are random, server-stored and HttpOnly. Frontend requests use a CSRF token from `/api/auth/me`. Admins can create, sync, resolve or void markets; members cannot. Registration **never** accepts a requested starting balance or role.

For an initial admin, run `python -m app.seed --admin-email ...` in the backend with an interactive terminal. The command will not upgrade an existing user to admin and does not expose a default production password. For local Compose, `COOKIE_SECURE=false` supports HTTP on `localhost`; production **must** use HTTPS, `COOKIE_SECURE=true`, a genuine hostname and audited CORS settings.

## How a market works

- Admin creates a unique market for a Jira numeric issue ID and immutable UTC cutoff. Current Jira key and sanitized summary are stored for display.
- At creation, an issuance account funds the bounded LMSR market-maker subsidy. Prices start at 50/50. Play credits have no external value.
- The API computes a quote, then enforces user ownership, balances, exact fixed-point share accounting, an explicit maximum buy cost or minimum sell proceeds, and an `Idempotency-Key` on execution.
- A user may hold YES or NO shares in a market, but not both at once. They must sell their entire current position before buying the opposite outcome. New orders use whole shares; an existing fractional holding from an older database can only be sold down to zero.
- Trades lock the market and affected wallet rows in PostgreSQL, write balanced double-entry ledger events and a price-history snapshot, and commit atomically. No naked `trader_id` supplied by callers is trusted.
- At cutoff, trading stops **regardless of the reconciliation worker's scheduling**. The worker fetches Jira's entire status changelog and reconstructs the status category as of cutoff. Incomplete/inconsistent history leaves the market CLOSED, not guessed.
- A winning YES/NO share pays one play credit; payment is unique per market and cannot be repeated. Admin may void a non-finalized market with a reason; voids pay outstanding shares at pre-void marginal prices, not as a full reversal of all prior trades.

### API highlights

| Route | Purpose |
| --- | --- |
| `POST /api/auth/register`, `/login`, `/logout` | Account and session management |
| `GET /api/auth/me` | Session identity + CSRF token |
| `GET /api/markets` | List/filter markets |
| `POST /api/markets` | Admin-only Jira-backed market creation |
| `GET /api/markets/{id}` | Contract and current probability |
| `POST /api/markets/{id}/quote` | Indicative buy/sell amount |
| `POST /api/markets/{id}/orders` | Idempotent slippage-bounded execution |
| `GET /api/markets/{id}/history`, `/trades` | Price and trade history |
| `GET /api/me/wallet`, `/portfolio`, `/orders` | User-specific credit and position data |
| `POST /api/admin/markets/{id}/sync|resolve|void` | Audited admin actions |
| `GET /healthz`, `/readyz` | Health/readiness |

All `/api` routes except register and login require a session. Mutating protected routes require an `X-CSRF-Token` header. Orders additionally require a unique `Idempotency-Key` header (e.g. a UUID), and `max_cost` for BUY or `min_proceeds` for SELL. Prices represent market-implied probabilities, not guarantees.

## Live Jira integration

See [JIRA_SETUP.md](JIRA_SETUP.md). Set `JIRA_MODE=live`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, the Jira URL and project allowlist via **server-side environment variables**, then restart API/worker. River only **reads** issue status and changelog. Each co-founder must use their own personal Jira token. Use a **new token** if one was ever shared or exposed, and never commit `.env`.

## Project tree

```
backend/app/markets/LMSR.py     LMSR pricing, retained as pure calculation engine
backend/app/db_models.py        users, sessions, balances, markets, orders, ledger, history, audit
backend/app/services.py         trade, subsidy, settlement and void transactions
backend/app/jira.py             read-only real/mock Jira clients and as-of cutoff evaluation
backend/app/main.py             FastAPI endpoints
backend/app/seed.py             password-prompt admin bootstrap
backend/app/worker.py           due-market reconciliation worker
backend/alembic/               versioned initial migration
backend/tests/                 isolated HTTP/pricing/Jira/ledger tests
frontend/app/                  Next.js App Router screens
frontend/components/           chart, authentication, trading form
compose.yaml                   local PostgreSQL, API, worker and web services
```

## Tests

```bash
cd backend
python -m pytest -q
```

Test suite uses mock Jira and an isolated temporary SQLite DB. It does not require an Atlassian token or touch your real board. Run PostgreSQL-specific concurrency tests with `TEST_DATABASE_URL` set to a disposable PostgreSQL database, never production:

```bash
TEST_DATABASE_URL=postgresql+psycopg://river:river-local-only@localhost:5432/river_test python -m pytest -q
```

Frontend checks (after `npm install`): `npm run typecheck && npm run build`.

## Security, operational limits and privacy

- This is a private small-team development app. No real-money, cryptocurrency, redemptions, credit transfers, payouts, or speculative financial claims.
- **Do not put this development stack directly on the public Internet.** Add TLS, robust distributed rate limits, monitoring, backups, account recovery, separate secrets and code security review first. The current login limiter is process-local.
- Jira permissions apply to the server-side Jira identity. River does not yet link individual Jira account IDs to member accounts or enforce an assignee-trading prohibition. That limitation creates conflict-of-interest risk.
- Issue summaries and contracts are viewable by authenticated River members; do not add private ticket descriptions or tokens to responses. The current repo previously included a **tracked** `jira_issue.json` export. This new project excludes it. If you are updating an existing clone, run `git rm --cached jira_issue.json` and commit that removal. Ignore rules do not remove earlier Git history, which may require a separately approved history purge.
- The existing historic exposed Jira token should remain revoked. Use a freshly generated token only.
- The initial Alembic revision is designed for a fresh database; do not use `down -v` or downgrade migrations on a database containing valuable data.
- Database-first worker polling is at-least-once; idempotent resolution prevents double payouts. Multiple worker deployments should be coordinated and monitored.
