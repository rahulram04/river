
import os
import json
import requests
from requests.auth import HTTPBasicAuth

# Jira configuration
JIRA_BASE_URL = "https://rahulrram04.atlassian.net"
ISSUE_KEY = "KAN-1"


def fetch_jira_issue(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"

    auth = HTTPBasicAuth(
        os.environ["JIRA_EMAIL"],
        os.environ["JIRA_API_TOKEN"]
    )


    response = requests.get(
        url,
        auth=auth,
        headers={"Accept": "application/json"},
        timeout=15
    )

    response.raise_for_status()
    return response.json()


def main():
    try:
        issue = fetch_jira_issue(ISSUE_KEY)

        print("Issue Key:", issue["key"])
        print("Summary:", issue["fields"]["summary"])
        print("Status:", issue["fields"]["status"]["name"])
        print(
            "Description:",
            json.dumps(
                issue["fields"].get("description"),
                indent=2
            )
        )

        # Save full issue data to JSON
        with open("jira_issue.json", "w", encoding="utf-8") as f:
            json.dump(issue, f, indent=2)

        print("\nSaved to jira_issue.json")

    except requests.exceptions.RequestException as error:
        print("Error fetching Jira issue:", error)
    except KeyError as error:
        print("Missing environment variable or field:", error)


if __name__ == "__main__":
    main()