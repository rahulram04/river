# Workbet: Claude Code implementation instructions

> Repository: `https://github.com/rahulram04/river`  
> Intended location: **repository root, `CLAUDE.md`**  
> Goal: turn the current FastAPI/LMSR prototype into a complete, locally runnable, Jira-connected, **play-credit-only** prediction-market MVP for work-item delivery.

## 0. Operating instructions for Claude Code

You are the lead engineer implementing Workbet. **Make code changes; do not stop after producing a plan or a list of suggestions.** Work through the phases in this file until the Definition of Done is satisfied, or report the exact external blocker and the working parts you completed.

1. First inspect the actual checked-out repository and `git status`. Treat the checked-out code as authoritative; this document describes the starting point observed on **2026-11-18** and may become stale. Preserve unrelated changes, and do not overwrite uncommitted work.
2. Execute the implementation in small, coherent steps, continuously running relevant tests. Prefer a clean, maintainable MVP to speculative infrastructure.
3. Keep the existing LMSR core and test coverage where useful. Refactor rather than duplicate it. Add migrations rather than destroying data. It is acceptable to replace the insecure prototype HTTP contracts when required for security; update tests and documentation accordingly.
4. Make reasonable engineering decisions independently. Do not wait for answers about ordinary implementation details. If Jira credentials, external services, or deployment permissions are unavailable, provide a fully usable **mock-Jira local demo** and finish everything else.
5. Never print, echo, read aloud, copy into logs, or commit API tokens, passwords, session secrets, real Jira issue exports, or `.env` values. **A Jira token was previously exposed in a chat; assume the old token is compromised and require a newly issued token.** Do not attempt to recover the old one.
6. Do not edit Jira issues, comment on issues, move Jira workflow statuses, use real-money payments, provision production cloud resources, rewrite Git history, force-push, or push commits without explicit user authorization. This assignment is to modify the local checkout and document how it works.
7. When finished, provide a short report: changed files, architectural decisions, exact run/test commands, test results, unresolved risks, and anything requiring human action. Do not claim tests passed unless you ran them.

## 1. Product definition

Workbet is a **team forecasting layer on top of Jira**. People spend *nonredeemable virtual credits* to buy and sell YES/NO shares in objectively resolvable work-item markets. The price of YES is presented as the market's implied probability, **not as a calibrated forecast unless evidence demonstrates calibration**.

Example contract:

> **Will Jira issue KAN-1 be in a configured Done-category status at 2026-12-04 22:00:00 UTC?**

The deadline is an immutable event cutoff stored in UTC. A market is successful only when Workbet can prove whether the issue was in an eligible Done status **as of that cutoff**, including transitions into and out of Done before the cutoff. Current Jira status alone is insufficient to resolve a past deadline.

**MVP users**: a small private team, including co-founders, with individual authenticated accounts. **MVP scope**: one Jira Cloud site, one or more allowlisted projects, binary markets, play credits, backend API, responsive frontend, persistence, audited resolution, automated reconciliation, and local Docker deployment.

**Explicitly not in MVP**: real-money deposits/payouts, cryptocurrency, exchange order book, margin, borrowing, short sales, derivatives, ML forecasts, mobile-native apps, multi-tenant SaaS, changing Jira data, third-party billing, and regulatory claims. No cash-out or transfer of virtual credits between users.

## 2. Existing repository, verified starting point

Inspect these exact existing files before modifying them:

- `backend/app/main.py`: FastAPI app with global in-memory `markets` and `traders` dictionaries; `demo` market and trader; `GET /markets/{market_id}`, unauthenticated `POST /traders/{id}`, and `POST /markets/{id}/buy|sell` accepting arbitrary `trader_id`.
- `backend/app/markets/LMSR.py`: standalone, reasonably stable `LMSRMarket`; log-sum-exp cost function, marginal probabilities, market buy/sell.
- `backend/app/models/Users.py`: in-memory `Trader` class; balances and positions keyed by *market object*, unsuitable as persisted IDs.
- `backend/tests/test_lmsr.py`, `test_users.py`, `test_main.py`: `unittest` tests using FastAPI `TestClient` and in-memory state.
- `backend/requirements.txt`: already contains FastAPI, Uvicorn, SQLAlchemy, Alembic, psycopg, pydantic-settings; inspect dependency versions and add missing dependencies (currently including HTTP client and test dependencies) as needed.
- `jira_issue_fetch.py`: standalone `requests` client hardcoded to `KAN-1`; suitable as a reference or CLI, **not** the shared service layer.
- `JIRA_SETUP.md`: describes the original Jira read-only experiment; update it when replacing the workflow.
- `.gitignore`: currently includes `backend/venv/`, `__pycache__/`, `.env`, and `jira_issue.json`, but **does not include `.venv/`**.
- `jira_issue.json` is **already tracked in Git despite being ignored**. It contains a real Jira response with issue/project/user metadata. Remove it from future tracked revisions and explain that the old Git history still contains it. Do not rewrite history automatically.
- No top-level `README.md`, no frontend, no real DB schema/migrations, and no working full-stack Compose setup were present in the inspected tree.

The real Jira site for the initial integration is `https://rahulrram04.atlassian.net`, the sample issue is `KAN-1`, and the public project is on GitHub as `rahulram04/river`. Treat Jira credentials and issue data as private; do not assume the Jira board itself is public.

## 3. Architecture and technology choices

Prefer this coherent stack; avoid introducing unnecessary services:

- **Backend**: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic.
- **Database**: PostgreSQL via psycopg. Use **database transactions, constraints, and row locks** for account and market updates. No in-process mutable singleton as authoritative state.
- **Pricing**: retain and test `LMSRMarket` as pure calculation logic; market state is loaded from and committed to PostgreSQL.
- **Jira**: a dedicated service layer using `httpx` or `requests` with timeouts, secure server-side credentials, bounded retries, and an injectable fake for tests/demo.
- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, a light charting library, and typed API calls. Do not use a second application database.
- **Authentication**: first-party email/password login for the closed MVP, securely hashed passwords (Argon2 or equivalent), persistent server-side sessions with random opaque identifiers in HttpOnly cookies. Store only hashes of session tokens in DB. Use Secure cookies in HTTPS environments, appropriate SameSite settings, CSRF protection for cookie-authenticated mutations, and exact allowed CORS origins. Never accept caller-supplied user IDs as authentication.
- **Jobs**: an explicit single-worker reconciliation process or command that can be run periodically, with database-level safeguards against multiple workers settling a market twice. Manual admin sync should use the same service code.
- **Local dev**: Docker Compose for PostgreSQL + API + web + optional worker; `.env.example` with placeholders only. Also support direct Python/Node development commands.
- **Tests**: pure unit tests, API integration tests against a disposable test DB, concurrency/idempotency tests, mocked Jira state-machine tests, basic frontend tests, and a documented end-to-end smoke scenario.

Suggested shape (adapt to existing code and avoid needless packages):

```text
river/
  CLAUDE.md
  README.md
  JIRA_SETUP.md
  .gitignore
  .env.example
  compose.yaml
  backend/
    app/
      main.py
      config.py
      db.py
      api/                 # auth, markets, orders, portfolio, admin
      auth/                # password, session and access control
      models/              # SQLAlchemy models
      schemas/             # Pydantic request/response types
      services/            # trading, accounts, markets, settlement
      integrations/jira.py # client, DTOs and fake
      markets/LMSR.py      # existing math, preserved/refined
      jobs/reconcile.py
    alembic/               # versioned migrations
    tests/
    requirements.txt
    Dockerfile
  frontend/
    app/                   # Next.js pages
    components/
    lib/                   # typed API client and types
    package.json
    Dockerfile
  scripts/                 # optional reproducible demo/seed scripts
  .github/workflows/ci.yml
```

## 4. Mandatory safety and data-handling rules

Before implementing new features:

1. Inspect `git status` and the tracked file list; do not destroy local changes.
2. Update `.gitignore` with `.venv/`, `venv/`, `node_modules/`, `.next/`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `.env`, `.env.*` **except `.env.example`**, `jira_issue.json`, local databases, logs, and build outputs.
3. Stop tracking `jira_issue.json` without deleting a potentially useful local copy, e.g., `git rm --cached jira_issue.json` if safe. Do **not** log or repeat its contents. Explain historical exposure and recommend a separate, explicitly approved history purge if needed.
4. Audit tracked files for inadvertently committed credentials. Report only filenames and remediation steps, **not secret values**. Do not attempt to use exposed credentials.
5. Ensure the Jira client never sends credentials or full private issue payloads to the browser, and never logs Authorization headers. Do not put raw Jira descriptions in API responses or public screenshots by default; use issue key, summary, status, and minimal timestamps.
6. Restrict sensitive routes by server-side role and membership. Avoid arbitrary credit minting, account impersonation, insecure CORS wildcards, verbose error leaks, hardcoded production secrets, and real Jira mutations.
7. Use Pydantic validation and parameterized database operations. Add sane body limits, server timeouts, pagination limits, rate limiting for login, and actionable 4xx/5xx error contracts. Never return internal exception traces to API clients.

## 5. Formal market and resolution rules

### Market identity and data

A Workbet `market_id` is a generated UUID, **not a Jira key**. Store both `jira_issue_id` (numeric ID string, stable if the Jira key changes) and `jira_issue_key` (human-readable, may change). One Jira issue may have multiple markets with different deadlines, but reject duplicate `(jira_issue_id, deadline_at, contract_version)` combinations.

Each binary market stores:

- UUID, Jira site, Jira ID and current issue key, sanitized summary, question, created-by user, timezone-aware `created_at` and **immutable** `deadline_at` in UTC.
- Immutable contract version and outcome semantics (`YES`, `NO`), configurable eligible Done status IDs/status categories captured at creation, numeric LMSR liquidity `b`, and per-outcome outstanding quantities.
- Lifecycle: `OPEN`, `CLOSED`, `RESOLVED`, `VOID` (admin-only void); winning outcome nullable, `resolution_source`, evidence hash/reference, `resolved_at`, and audited override reason.
- A fixed market-maker funding/subsidy entry and an auditable cumulative market cash balance.

A created market must not be already expired or ineligible. Restrict market creation to configured project keys, reject issues Workbet cannot access, and reject already-completed issues by default. Never change a contract's cutoff, YES/NO semantics, or liquidity after the first trade; simplest MVP rule: never edit them after creation.

### Trading and deadlines

- Use the existing LMSR math: `C(q) = b * log(sum(exp(q_i / b)))` and `p_i = exp(q_i/b) / sum(exp(q_j/b))`. Preserve numerically stable log-sum-exp and softmax implementation.
- **Only fully paid, long-only YES/NO shares** in MVP. No naked sells, no credit balances below zero, no shorting, and no negative holdings.
- Each share of the winning outcome pays **1 play credit** at settlement; losing shares pay zero. No payout before resolution. Use a documented settlement/rounding policy.
- Use integer micro-units (or another exact fixed-point representation) for stored account balances, ledger amounts, and share units, with deterministic rounding rules; use floating point only in isolated LMSR calculations, verify finiteness, and round conservatively when crossing the money boundary. Document precision and minimum trade size. Do not leave financial state as unconstrained Python floats.
- Display an executable quote, estimated after-trade probability, fee (zero for MVP), and a quote timestamp. Execute orders against **fresh database state** and enforce submitted `max_cost` on buys or `min_proceeds` on sells to bound slippage. Quotes are nonbinding.
- Check account ownership and permissions **server-side**. Enforce nonnegative balance, nonnegative positions, per-user/per-market position and order limits, minimum/maximum shares, and finite numeric fields. Reject NaN/Infinity and invalid IDs/outcomes.
- Require a client `Idempotency-Key` for each order. Save the key and payload hash under the authenticated user; retries of the same logical request return the original order result. Reusing the key with a different payload yields `409`.
- Place trade, wallet debit/credit, position change, market inventory change, order record, ledger entries, and price history **inside one PostgreSQL transaction**. Lock market and relevant wallet/position rows in a consistent order. Under concurrent orders, the result must match some valid serial ordering. Use constraints/unique indices to guard invariants, and test them.
- A market becomes nontradable when backend time is at or after `deadline_at`, regardless of the displayed/scheduled `status`. A job marks the market `CLOSED`; the trade transaction must still check its deadline so scheduling delays cannot admit late orders.
- After `RESOLVED` or `VOID`, no trading. Keep all historical trades and prices accessible. Voiding should refund users using an explicit, deterministic policy and ledger entries; for simplicity, refund **net contributions per market** and reverse appropriately if technically feasible, and document the policy. Do not silently delete accounting history.

### Subsidy and accounting

- A binary LMSR market starting at `q=[0,0]` has bounded worst-case market-maker loss of approximately `b * ln(2)` credits (before fees/rounding). Reserve that **virtual** subsidy from a platform issuance/treasury account when creating the market; model it transparently rather than silently inventing balances.
- Track all grants, order cash movements, market-maker subsidies, settlement payouts, and void refunds as an **append-only balanced ledger**. Each logical event has a unique idempotent reference; ledger postings balance to zero including issuer/treasury accounts, with no unexplained credits. Provide reconciliation checks.
- MVP signup gives each authenticated member **a fixed, configurable starting grant** once (e.g., 1,000 credits). Users cannot choose their starting balance or deposit credits through an unauthenticated route. Subsequent admin grants require authorization and an audit trail.

### Objective Jira settlement

- At the deadline, determine whether Jira's issue **status as of the exact cutoff** belonged to the eligible Done set. If done at or before cutoff and reopened before cutoff, the outcome is **NO**. If reopened after cutoff, outcome stays **YES**. More recent edits do not rewrite history.
- Retrieve Jira changelog/history (including pagination and all relevant status transitions), issue creation time, and status metadata as necessary to reconstruct the status at cutoff. **Never** resolve a historical market from the current `fields.status` alone. Work out the status at cutoff even when an issue was already Done and reopened.
- Resolve only when the available data is sufficient and internally consistent. On authentication failure, Jira outage, incomplete pagination, deleted/inaccessible issue, or ambiguity, keep the market `CLOSED`, record the sync failure safely, and retry later. **Never guess an outcome.**
- Settlement must be idempotent and single-writer safe. Payout winning positions exactly once; retain losing positions/trade history as records. Persist evidence with timestamps, source identifiers, resolver version, and minimal sanitized diagnostics.
- Provide an admin-only audited override (require reason, previous/next outcome and actor, and explicit confirmation); no silent mutable `winning_outcome` or unaudited resettlement. Prefer forbidding override after payout unless a separately implemented compensating ledger workflow exists.
- **One-way integration**: Jira -> Workbet. Trading and resolution must never write to Jira.
- **Conflicts of interest**: flag markets involving a user's own assigned issues, give the admin an option to disallow trading by issue assignees/reporters, and document manipulation risks. Default to a conservative policy for a small team (for example, restrict trading on one's own assigned issue). Do not claim prices objectively measure productivity.

## 6. Database schema and migration requirements

Create Alembic migrations, appropriate foreign keys, unique constraints, indexes, timestamps, and explicit transaction boundaries. Suggested normalized tables:

- `users`: UUID, email unique, password hash, role (`ADMIN`, `MEMBER`), created_at, disabled_at.
- `sessions`: hashed opaque token unique, user_id, expires_at, revoked_at, created_at.
- `wallets` or `accounts`: user/system account, integer balance units, account kind; ensure immutable identity and nonnegative **user** balances.
- `ledger_events` and `ledger_entries`: event/reference unique; account_id; signed amount in integer units; event type; created_at; balanced postings.
- `markets`: UUID, Jira mapping, creation/deadline, contract, liquidity, state, outstanding quantities, settlement data, version and price metadata.
- `positions`: unique `(user_id, market_id, outcome)`; positive or zero share amount in fixed units.
- `orders`: UUID, user, market, side, outcome, shares, executed price/cost, quote limit, idempotency key/payload hash, created_at.
- `price_history`: market, timestamp, YES/NO probability and outstanding quantities, associated order; record initial `0.5/0.5` snapshot and subsequent successful trades.
- `jira_sync_events`: issue ID/key, source timestamp, cursor/poll metadata, sanitized status transitions, sync outcome, last error category; enough for diagnostics without exposing private issue bodies.
- `market_resolutions`, `admin_audit_log`: evidence, actor, reason, previous state and new state, timestamp, unique settlement guard.

A simpler schema is acceptable if it satisfies the same invariants. `markets` may store `q_yes/q_no` numeric fixed-point columns rather than an outcome inventory table because MVP is binary. Add DB constraints as far as practical. Define separate transaction boundaries for account initialization, order execution, closing, settlement, and voids.

Do not store a live `LMSRMarket` object, Python dictionary, or object-identity key in persistent state. Rehydrate the pricing engine from persisted quantities for each order or quote. Provide migration up/down scripts and documented fresh-DB setup.

## 7. API contract

Design typed request and response models with consistent errors, input validation, authenticated identities, pagination, and OpenAPI docs. Prefer a versioned `/api` prefix. Implement these routes (the exact path segment may change if consistently documented):

| Method / route | Auth | Behavior |
| --- | --- | --- |
| `POST /api/auth/register` | Public, rate limited | Create one MEMBER and one fixed starting grant; never choose balance/role in request |
| `POST /api/auth/login` | Public, rate limited | Verify password, set secure session cookie |
| `POST /api/auth/logout` | User | Revoke session |
| `GET /api/auth/me` | User | Return own profile and role |
| `GET /api/markets` | User | Paginated markets, filter by status/project |
| `POST /api/markets` | ADMIN | Fetch and validate Jira issue, create funded binary market |
| `GET /api/markets/{market_id}` | User | Contract details, deadline, prices, state, sanitized Jira metadata |
| `POST /api/markets/{market_id}/quote` | User | Quote BUY/SELL, outcome YES/NO, share amount, max/min limit examples |
| `POST /api/markets/{market_id}/orders` | User | Execute one idempotent, slippage-limited trade |
| `GET /api/markets/{market_id}/trades` | User | Paginated public trade history with privacy-conscious identifiers |
| `GET /api/markets/{market_id}/history` | User | Price history for chart |
| `GET /api/me/wallet` | User | Balance and ledger summary |
| `GET /api/me/portfolio` | User | Holdings across markets, value and resolved payouts |
| `POST /api/admin/markets/{market_id}/sync` | ADMIN | Jira refresh/reconcile using shared service |
| `POST /api/admin/markets/{market_id}/resolve` | ADMIN | Trigger verified resolution; never accept an arbitrary winning outcome without audited override protocol |
| `POST /api/admin/markets/{market_id}/void` | ADMIN | Require audit reason; apply documented refund policy |
| `GET /healthz`, `GET /readyz` | Internal/simple | Process health and DB readiness; no secret info |

Order body example:

```json
{
  "side": "BUY",
  "outcome": "YES",
  "shares": "5.000000",
  "max_cost": "3.000000"
}
```

Send `Idempotency-Key` in request headers as a UUID. For sells use `min_proceeds` rather than `max_cost`. Execute buys and sells from **the server-derived session user**, never from a `trader_id` supplied by the client. `POST /markets/{id}/buy|sell` from the prototype may be removed or replaced by authenticated compatibility shims; do not leave insecure legacy paths accessible.

Return normalized decimal quantities as strings and probabilities as finite JSON numbers (or explicitly documented decimal strings). Provide clear HTTP errors: `400` invalid domain action, `401` unauthenticated, `403` forbidden, `404` not found, `409` stale quote/idempotency conflict or closed market, `422` schema validation, `429` login abuse, `503` Jira-dependent feature temporarily unavailable. Never hide a failed trade behind a 200 response.

## 8. Jira integration

Configuration via server environment only:

```dotenv
JIRA_BASE_URL=https://rahulrram04.atlassian.net
JIRA_EMAIL=replace-with-own-atlassian-email
JIRA_API_TOKEN=replace-with-newly-issued-token
JIRA_ALLOWED_PROJECT_KEYS=KAN
JIRA_MODE=mock
DATABASE_URL=postgresql+psycopg://river:local-password@localhost:5432/river
SESSION_SECRET=replace-with-a-long-random-value
WEB_ORIGIN=http://localhost:3000
INITIAL_PLAY_CREDITS=1000
```

**These are placeholders, not actual credentials.** Do not commit a populated `.env` or embed real token values anywhere. If `JIRA_MODE=mock`, the app must be demoable without `JIRA_EMAIL`/`JIRA_API_TOKEN`. If `JIRA_MODE=live`, fail clearly on missing required configuration rather than inventing issue data.

Implement a `JiraClient` interface with a real client and deterministic mock client. At minimum:

- `get_issue(issue_key)` obtains Jira numeric `id`, current key, summary, status ID/category, assignee ID (if needed for conflict checks), and creation timestamp.
- `get_status_history(issue_id)` exhausts Jira status changelog pagination as required, preserves timezone-aware timestamps, and produces ordered transitions for as-of resolution.
- Handle 401/403/404/429/5xx, timeouts, and Retry-After with bounded backoff and descriptive but sanitized errors.
- Never silently accept partial history. Do not send Atlassian email/token from the frontend or store the full Jira response in the Workbet DB.
- Support issue-key changes through stable issue ID. A market remains linked if the issue moves projects, but flag such changes for admin review if outside allowlisted projects.
- Poll for updates periodically, close markets at deadlines, and resolve when historical evidence is available. Use a single CLI worker with appropriate locks; expose manual sync from admin UI. **Webhooks are optional after the polling MVP**; if implemented, authenticate and deduplicate them correctly, and continue periodic reconciliation.
- Leave existing `jira_issue_fetch.py` as a safe CLI or refactor it to call the reusable client; do not require it for normal API startup.

Create deterministic mock scenarios including: open issue, before-deadline completion, completion after deadline, completion then reopening before deadline, reopening after deadline, rate limiting, empty status history, and intermittent API failures. Use `KAN-1` as the default sample key in the demo, but do not depend on the real account or a hardcoded snapshot.

## 9. Frontend requirements

Deliver a functional, responsive, accessible interface. No static mockup in lieu of wired API calls.

**Required screens and behavior**:

1. Registration/login/logout, session persistence, useful auth/error states.
2. Market directory with YES probability, question, Jira key, UTC deadline rendered in local time, OPEN/CLOSED/RESOLVED/VOID state, and search/filter.
3. Market detail with clear **YES/NO contract terms**, price history graph, Jira issue link, current price, volume, deadline, historical status, and risk/limitations text.
4. Buy/sell form for YES and NO: share quantity, executable quote, max-cost/min-proceeds control, cash/position check, confirmation, loading/disabled/error/success states, and automatic refresh of price and wallet. Never imply an order executed when the server rejected it.
5. My portfolio: available play credits, holdings, order history, resolved winnings, and basic P&L with clear accounting assumptions.
6. Admin panel: create a market from Jira key plus UTC deadline, choose liquidity from permitted bounds, inspect integration health, trigger sync/resolve, and see audit entries; no raw token display.
7. A `Mock Jira` mode indicator in development so demo data is not confused with live work items.

Use clean UI with keyboard navigation, proper labels, mobile layouts, and human-readable formatting. The frontend should use a single typed API client. Avoid exposing secrets via `NEXT_PUBLIC_*` variables. Render prices clearly as implied probabilities, not guaranteed delivery forecasts. User-specific routes must not rely on IDs guessed in the browser.

## 10. Tests and verification

Retain or adapt all existing LMSR tests. Add tests for at least the following:

**Pricing**
- Initial binary price is 0.5/0.5; probabilities sum to 1; monotonic price change after buying YES; reversibility of immediate buy+sell (up to rounding); stable behavior for large quantities; invalid and nonfinite values rejected.

**Wallets, transactions, and concurrency**
- Registration grants exactly once; client cannot request more credits; user balance never negative; trader cannot sell more than owned; market quantities and position totals reconcile; all ledger events balance.
- Parallel buys on the same market (and wallet) cannot overspend and reflect serializable valid execution; failed DB transaction rolls back all state; retry of a successful order does not charge twice; repeated idempotency key with changed payload fails.
- Bound slippage under concurrent price changes; stale quotes do not silently execute beyond limit.
- Order and position state survive an API restart.

**Auth**
- Unauthenticated trade, admin action, or other user's account access is blocked; role checks are server-side; password hashes are not returned; login/logout/session expiry work; CSRF checks for mutations work as applicable.

**Jira and settlement**
- Normal success and NO outcomes; done -> reopened before deadline gives NO; reopened after deadline does not change YES; post-deadline completion gives NO.
- Changelog pages are exhausted; status reconstruction does not use current status alone; ambiguous/incomplete history leaves market CLOSED; retries are safe; unauthorized/error responses do not fabricate settlement.
- Two concurrent settle attempts produce one payout and one ledger event; no late trade even if closing worker is delayed; void/override is admin-only and audited.
- Markets survive Jira key rename by numeric ID; invalid/deleted inaccessible Jira issue blocks creation and is reported safely.

**HTTP and UI**
- Typed schema errors, exact balance/position updates, CORS/CSRF behavior, pagination, consistent admin/normal user views.
- A browser smoke test or documented automation executes the full path: create/register two users, market creation from mock `KAN-1`, initial YES price 0.5, trade YES, price rises, trade NO, portfolio updates, close at cutoff using a test clock, mock Jira transition history settles, winning positions receive one credit per share, payout cannot repeat.

Tests must **not contact the real Jira site** or require private credentials. Use a disposable PostgreSQL test database and fixture isolation. Avoid tests depending on wall-clock timing; inject a clock or simulate timestamps. Document the exact commands and run them.

## 11. Developer experience and CI

1. `README.md`: what Workbet is, exact fresh-clone prerequisites and startup commands, no external Jira credentials needed for mock mode, architecture, MVP limitations, tests, common errors.
2. `JIRA_SETUP.md`: per-cofounder Jira credentials (each person creates own token), mode switching, permissions, issue setup, status mapping, and troubleshooting. No real secrets.
3. `.env.example`: all supported environment variables with safe defaults/placeholders; type-safe config validation. Ensure `.env.example` remains trackable despite `.env.*` ignore rule.
4. `compose.yaml`: Postgres, backend, frontend, reconciliation worker (or documented single-worker alternative), health checks/depends-on. `docker compose up --build` from a clean clone should serve app in `JIRA_MODE=mock` after required setup. Do not depend on a hosted service.
5. Migrations and seed command: create deterministic local demo (admin, members, at least one mock Jira market), with **no default shared production password**. If seeded demo login credentials exist, only enable them in explicit mock/dev mode and prominently document them.
6. Code formatting, static checks and version-pinned/locked dependencies appropriate for each ecosystem; `pytest`/unittest, TypeScript checks, frontend lint/build. CI GitHub Actions should run applicable checks and tests without external secrets. A Postgres service container is fine.
7. Add straightforward scripts/Make targets or package scripts for `setup`, `dev`, `test`, `migrate`, `seed`, and `reconcile`. Use macOS-friendly commands. Existing users have Homebrew-managed Python: recommend a project `.venv`, not `pip --break-system-packages`.
8. Update docs whenever actual CLI commands or API routes differ from this plan.

## 12. Implementation sequence

Implement in this order. After each phase, run relevant tests and fix failures before continuing.

### Phase A: hygiene, scaffolding, baseline
- Inspect repository, status, dependencies, and initial tests. Record baseline errors. Add ignore rules and remove tracked export from future commits. Add requirements for HTTP/test tooling, typed configuration, README, and minimal Compose DB.
- Keep pricing implementation intact until regression tests pass.

### Phase B: persistence and secure account model
- Implement models, migration, accounts, ledger and signup grant. Introduce secure sessions and authorization. Remove client-controlled trader identities and balances from HTTP routes. Add DB transaction helpers and tests.

### Phase C: durable markets, trading, and resolution
- Persist markets, share inventories and positions; quote/trade services, idempotency, slippage limits, concurrency locking, price snapshots, close job, settlements, subsidy funding and audited voids. Add reconciliation checks and tests.

### Phase D: Jira service, history-based outcome evaluation
- Implement real Jira client + fake client, issue validation, stable Jira ID mapping, changelog reconstruction, automatic reconciliation worker, safe manual admin sync, and retry logic. Build deterministic test fixtures and tests.

### Phase E: frontend end to end
- Implement auth, market directory, market details, quote/trade form, charts, portfolio, and admin flows, all against the real backend. Confirm responsive behavior and error/loading states.

### Phase F: final QA, documentation, CI
- Fresh-db migration and demo seed. Run all backend/frontend tests, build UI, smoke test with mock Jira, validate API docs and Compose startup, audit secrets and tracked output, fix regressions. Document limitations and unresolved risks.

If time or context is constrained, prioritize **one trustworthy vertical slice** (authenticated mock Jira market -> concurrent-safe trades -> persisted balances -> objective settlement -> UI) instead of spreading partial stubs across many files. However, continue beyond that slice if capable; the stated target is the complete MVP.

## 13. Definition of Done: all required

- [ ] `docker compose up --build` launches a useful local demo without live Jira credentials, and frontend/API links are documented and reachable.
- [ ] Real Jira mode works with a newly created, environment-provided token and read-only Jira API calls; no token is required for tests/mock mode.
- [ ] Two distinct authenticated co-founders can trade YES/NO shares on a Jira-backed work item with fixed starting play credits; no account impersonation or arbitrary balance minting.
- [ ] Prices use LMSR, trades are long-only, idempotent, slippage-bounded, concurrency-safe, and persisted in PostgreSQL with balanced ledger entries.
- [ ] Market creation stores stable Jira numeric ID, exact contract, immutable UTC cutoff, and funded bounded market-maker subsidy.
- [ ] Markets reject trades at/after deadline. Jira changelog determines status **as of deadline**, with proper reopen/late-completion handling.
- [ ] Verified settlement pays winning positions once. Ambiguous Jira history never causes guessed settlement. Admin overrides/voids are auditable.
- [ ] Frontend supports login, market exploration, trading, portfolio, chart, and admin create/sync/resolve end to end.
- [ ] `.gitignore` is correct and `jira_issue.json` is no longer tracked in the new revision; historic exposure is documented without printing data.
- [ ] README and Jira setup are accurate. Migrations, tests, CI, and smoke-demo commands work and are reported honestly.
- [ ] No production/deployment claims beyond what was actually validated; no real money, Jira write actions, or remote pushes.

## 14. Final response format after coding

At completion, report:

1. **Implemented**: concise summary of working user-visible flows and key architecture.
2. **Files changed**: most important additions/edits.
3. **How to run**: exact copied-and-tested commands, localhost URLs, and how to activate live Jira mode safely.
4. **Verification**: commands executed and counts/results; identify tests skipped due to missing runtime/tool access.
5. **Remaining issues**: concrete risks/blockers only, ordered by severity. Do not present an incomplete MVP as complete.

**Start by inspecting the repository now. Then implement, test, and document.**
