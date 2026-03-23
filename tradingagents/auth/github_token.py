"""GitHub token retrieval for the GitHub Copilot API.

Uses the ``gh`` CLI exclusively — no explicit API token or env var.
Run ``gh auth login`` once to authenticate; this module handles the rest.
"""

import subprocess
from typing import Optional


def get_github_token() -> Optional[str]:
    """Return a GitHub token obtained via the GitHub CLI (``gh auth token``).

    Returns None if the CLI is unavailable or the user is not logged in.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_copilot_api_url() -> str:
    """Resolve the Copilot inference base URL.

    Queries the GitHub GraphQL API for the user's Copilot endpoints.
    Falls back to the standard individual endpoint on failure.
    """
    import requests

    token = get_github_token()
    if not token:
        return "https://api.individual.githubcopilot.com"

    try:
        resp = requests.post(
            "https://api.github.com/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"query": "{ viewer { copilotEndpoints { api } } }"},
            timeout=5,
        )
        if resp.status_code == 200:
            api = resp.json()["data"]["viewer"]["copilotEndpoints"]["api"]
            if api:
                return api.rstrip("/")
    except Exception:
        pass

    return "https://api.individual.githubcopilot.com"


# Required headers for the Copilot inference API (reverse-engineered from the
# Copilot CLI at /usr/local/lib/node_modules/@github/copilot).
COPILOT_HEADERS = {
    "Copilot-Integration-Id": "copilot-developer-cli",
    "X-GitHub-Api-Version": "2025-05-01",
    "Openai-Intent": "conversation-agent",
}
