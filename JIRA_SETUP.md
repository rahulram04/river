# River

This repository includes `jira_issue_fetch.py`, a Python utility for fetching issues from our shared Jira project.

## Project links

- [Jira board](https://rahulrram04.atlassian.net/jira/software/projects/KAN/boards/2)
- [Example issue: KAN-1](https://rahulrram04.atlassian.net/browse/KAN-1)

## Prerequisites

- Access to this GitHub repository and the shared Jira project
- Python 3 installed (`python3 --version`)
- A Jira Cloud API token associated with **your own** Atlassian account

## Local setup

### 1. Clone the repository

Copy the clone URL from the repository's **Code** button on GitHub, then run:

```bash
git clone <REPOSITORY_CLONE_URL>
cd river
```

If you've already cloned the repository, just run `cd river` from its parent directory.

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Use `source .venv/bin/activate` at the beginning of each new terminal session. On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead.

### 3. Install dependencies

```bash
python -m pip install requests
```

This installs `requests` inside the virtual environment, avoiding macOS/Homebrew's `externally-managed-environment` error.

### 4. Configure Jira credentials

1. Sign in to [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
2. Create an API token for **your account**. The current script uses basic authentication with an Atlassian email address and API token.
3. In the same terminal where you will run the script, set your email and enter the token without displaying it:

```bash
export JIRA_EMAIL="your-atlassian-email@example.com"
printf 'Jira API token: '
IFS= read -rs JIRA_API_TOKEN
printf '\n'
export JIRA_API_TOKEN
```

**Never commit or share API tokens.** Each collaborator should use their own token. Environment variables set this way are local to the current terminal session.

### 5. Fetch an issue

```bash
python jira_issue_fetch.py
```

By default, the script fetches **KAN-1** from `https://rahulrram04.atlassian.net` and prints its key, summary, status, and description. It also writes the full JSON response to `jira_issue.json` in the repository directory.

To fetch a different issue, change `ISSUE_KEY = "KAN-1"` near the top of `jira_issue_fetch.py` to the desired issue key.

## Troubleshooting

| Error | What to check |
| --- | --- |
| `No module named requests` | Activate `.venv` and run `python -m pip install requests`. |
| `Missing environment variable or field: 'JIRA_EMAIL'` | Export `JIRA_EMAIL` in the terminal running the script. |
| `Missing environment variable or field: 'JIRA_API_TOKEN'` | Export `JIRA_API_TOKEN` in that terminal. |
| `401 Unauthorized` | Check your Atlassian email and API token. Recreate the token if needed. |
| `403 Forbidden` or `404 Not Found` | Check Jira project/issue access and verify the issue key. |
| `externally-managed-environment` | Use the virtual environment rather than installing packages globally. |

## Git hygiene

Add these entries to `.gitignore` if they are not already present:

```gitignore
.venv/
__pycache__/
.env
jira_issue.json
```

The JSON output may contain project information and should not be committed by default. Do not store API tokens in source code or tracked files.
