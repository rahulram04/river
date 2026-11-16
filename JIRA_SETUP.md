# River prediction market and Jira setup

This guide describes how to associate prediction-market markets with Jira
issues. The current repository includes a read-only Jira example in
`jira_issue_fetch.py`; the FastAPI market endpoints do not create or update
Jira issues yet.

## Intended integration

Use Jira as the source of truth for the work item and River as the source of
truth for market activity:

```text
Jira issue KAN-1
    ↓ issue key
River market "KAN-1"
    ↓
LMSR prices, trades, and trader positions
```

Recommended mapping:

| River field | Jira value |
| --- | --- |
| `market_id` | Jira issue key, such as `KAN-1` |
| Market question | Jira issue summary or a configured question |
| Market description | Jira issue description |
| Outcome labels | Application configuration, not Jira status names |
| Market status | Derived from Jira status plus application rules |

Do not use the Jira status as an LMSR outcome. Jira statuses describe work
progress; LMSR outcomes describe mutually exclusive predictions.

## Prerequisites

- Access to the `KAN` Jira project
- Python 3.12 or newer
- A Jira Cloud API token associated with your own Atlassian account
- The River backend installed from `backend/requirements.txt`

Project links:

- [Jira board](https://rahulrram04.atlassian.net/jira/software/projects/KAN/boards/2)
- [Example issue: KAN-1](https://rahulrram04.atlassian.net/browse/KAN-1)

## Configure credentials

Create a token at [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
Never put the token in Python source, JSON files, Jira descriptions, or Git.

### Windows PowerShell

```powershell
$env:JIRA_BASE_URL = "https://rahulrram04.atlassian.net"
$env:JIRA_EMAIL = "your-atlassian-email@example.com"
$secureToken = Read-Host "Jira API token" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $env:JIRA_API_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
}
```

The token remains available only in the current PowerShell process. Do not
save it in a PowerShell profile or commit it to the repository.

### macOS/Linux

```bash
export JIRA_BASE_URL="https://rahulrram04.atlassian.net"
export JIRA_EMAIL="your-atlassian-email@example.com"
read -r -s JIRA_API_TOKEN
export JIRA_API_TOKEN
```

The existing fetch script uses basic authentication with `JIRA_EMAIL` and
`JIRA_API_TOKEN`.

## Verify Jira access

From the repository root:

```powershell
python -m pip install requests
python jira_issue_fetch.py
```

The script fetches `KAN-1`, prints its key, summary, status, and description,
and writes the response to `jira_issue.json`. Treat that file as temporary
local data.

To fetch another issue, change `ISSUE_KEY` in `jira_issue_fetch.py`. A future
backend integration should pass the issue key as a function argument instead
of using a module-level constant.

## Connect a market to a Jira issue

For the first implementation, create a market only after confirming that the
issue exists:

```text
1. Receive a Jira issue key, for example KAN-1.
2. GET /rest/api/3/issue/KAN-1 from Jira.
3. Check that the issue is eligible for prediction trading.
4. Create a River market with market_id="KAN-1".
5. Store the market configuration and Jira key together.
6. Use the River market endpoints for prices and trades.
```

The market should store configuration similar to:

```json
{
  "market_id": "KAN-1",
  "jira_issue_key": "KAN-1",
  "question": "Will Task 1 be completed?",
  "outcomes": ["Yes", "No"],
  "liquidity": 10
}
```

The Jira issue fetch belongs in a Jira integration/service module, not inside
`LMSRMarket`. `LMSRMarket` should continue to handle only pricing and share
quantities. FastAPI routes or a service layer should coordinate Jira and the
market.

Recommended future structure:

```text
backend/app/
├── integrations/
│   └── jira.py       # Jira API client
├── markets/
│   └── LMSR.py      # LMSR calculations
├── services/
│   └── market_service.py
└── main.py           # HTTP routes
```

## Suggested API workflow

After the integration is implemented, the application can expose:

```text
POST /markets
GET  /markets/{market_id}
POST /markets/{market_id}/buy
POST /markets/{market_id}/sell
```

Example market creation request:

```json
{
  "jira_issue_key": "KAN-1",
  "outcomes": ["Yes", "No"],
  "liquidity": 10
}
```

The response should include the River `market_id`, the Jira issue key, the
outcomes, and current LMSR prices. Do not send Jira credentials from clients;
the backend should read them from its environment.

## Jira synchronization rules

Keep synchronization one-directional at first:

```text
Jira issue metadata → River market configuration
River trades → River database
```

Do not automatically edit Jira issues after every trade until the behavior is
well-defined. If synchronization is added later:

- Update Jira only through an explicit service.
- Record failures and retry them; do not silently ignore them.
- Avoid putting trader identities or sensitive trading data in Jira comments.
- Use a stable Jira issue key rather than the issue summary as an identifier.
- Decide what happens when an issue is closed, deleted, or inaccessible.

## Troubleshooting

| Error | What to check |
| --- | --- |
| `No module named requests` | Run `python -m pip install requests` in the active environment. |
| `401 Unauthorized` | Check the Jira email and API token. |
| `403 Forbidden` | Confirm the account can browse the `KAN` project. |
| `404 Not Found` | Check the Jira base URL and issue key. |
| Market not found | Confirm the River `market_id` matches the configured issue key. |
| Jira works but market creation fails | Check application validation and LMSR outcome configuration. |

## Git hygiene

The repository `.gitignore` should exclude:

```gitignore
backend/venv/
__pycache__/
.env
jira_issue.json
```

`jira_issue.json` may contain project or user information and should not be
committed by default. Revoke and replace any token that is accidentally
committed or exposed.
