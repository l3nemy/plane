# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import hmac
import os
import time
from hashlib import sha256
from typing import Any

# Django imports
from django.conf import settings

# Third party imports
import jwt
import requests


GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubAppConfigurationError(Exception):
    """Raised when GitHub App credentials are incomplete."""


class GitHubAppAPIError(Exception):
    """Raised when GitHub App API calls fail."""


def _get_setting(name: str) -> str:
    value = getattr(settings, name, None) or os.environ.get(name, "")
    return str(value).strip()


def get_github_app_private_key() -> str:
    private_key = _get_setting("GITHUB_APP_PRIVATE_KEY")
    private_key_file = _get_setting("GITHUB_APP_PRIVATE_KEY_FILE")

    if private_key:
        return private_key.replace("\\n", "\n")

    if private_key_file:
        with open(private_key_file, encoding="utf-8") as file:
            return file.read()

    return ""


def get_github_app_jwt() -> str:
    app_id = _get_setting("GITHUB_APP_ID")
    private_key = get_github_app_private_key()

    if not app_id or not private_key:
        raise GitHubAppConfigurationError(
            "GitHub App credentials are required. Configure GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY or "
            "GITHUB_APP_PRIVATE_KEY_FILE."
        )

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": app_id,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


def get_github_app_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def raise_for_github_response(response: requests.Response) -> None:
    if response.status_code < 400:
        return

    try:
        message = response.json().get("message", response.text)
    except ValueError:
        message = response.text

    raise GitHubAppAPIError(f"GitHub API returned {response.status_code}: {message}")


def get_github_installation(installation_id: int) -> dict[str, Any]:
    token = get_github_app_jwt()
    response = requests.get(
        f"{GITHUB_API_BASE_URL}/app/installations/{installation_id}",
        headers=get_github_app_headers(token),
        timeout=15,
    )
    raise_for_github_response(response)
    return response.json()


def get_github_installation_token(installation_id: int) -> str:
    token = get_github_app_jwt()
    response = requests.post(
        f"{GITHUB_API_BASE_URL}/app/installations/{installation_id}/access_tokens",
        headers=get_github_app_headers(token),
        timeout=15,
    )
    raise_for_github_response(response)

    installation_token = response.json().get("token")
    if not installation_token:
        raise GitHubAppAPIError("GitHub installation token response did not include a token.")

    return str(installation_token)


def list_github_installation_repositories(
    installation_id: int,
    page: int = 1,
    per_page: int = 100,
) -> dict[str, Any]:
    token = get_github_installation_token(installation_id)
    response = requests.get(
        f"{GITHUB_API_BASE_URL}/installation/repositories",
        headers=get_github_app_headers(token),
        params={
            "page": page,
            "per_page": min(max(per_page, 1), 100),
        },
        timeout=15,
    )
    raise_for_github_response(response)
    payload = response.json()

    repositories = [
        {
            "id": str(repository.get("id")),
            "full_name": repository.get("full_name"),
            "html_url": repository.get("html_url"),
            "url": repository.get("url"),
            "name": repository.get("name"),
            "owner": (repository.get("owner") or {}).get("login"),
        }
        for repository in payload.get("repositories", [])
    ]

    return {
        "repositories": repositories,
        "total_count": payload.get("total_count", len(repositories)),
    }


def list_github_pull_request_commits(
    *,
    installation_id: int,
    owner: str,
    repository: str,
    pull_number: int,
) -> list[dict[str, Any]]:
    token = get_github_installation_token(installation_id)
    headers = get_github_app_headers(token)
    commits = []
    page = 1

    while True:
        response = requests.get(
            f"{GITHUB_API_BASE_URL}/repos/{owner}/{repository}/pulls/{pull_number}/commits",
            headers=headers,
            params={
                "page": page,
                "per_page": 100,
            },
            timeout=15,
        )
        raise_for_github_response(response)

        page_commits = response.json()
        commits.extend(page_commits)

        if len(page_commits) < 100:
            break

        page += 1

    return commits


def upsert_github_issue_comment(
    *,
    installation_id: int,
    owner: str,
    repository: str,
    issue_number: int,
    marker: str,
    body: str,
) -> dict[str, Any]:
    token = get_github_installation_token(installation_id)
    comments_url = f"{GITHUB_API_BASE_URL}/repos/{owner}/{repository}/issues/{issue_number}/comments"
    headers = get_github_app_headers(token)
    comments_response = requests.get(
        comments_url,
        headers=headers,
        params={
            "per_page": 100,
        },
        timeout=15,
    )
    raise_for_github_response(comments_response)

    for comment in comments_response.json():
        if marker in (comment.get("body") or ""):
            response = requests.patch(
                comment.get("url"),
                headers=headers,
                json={
                    "body": body,
                },
                timeout=15,
            )
            raise_for_github_response(response)
            return response.json()

    response = requests.post(
        comments_url,
        headers=headers,
        json={
            "body": body,
        },
        timeout=15,
    )
    raise_for_github_response(response)
    return response.json()


def update_github_issue_assignees(
    *,
    installation_id: int,
    owner: str,
    repository: str,
    issue_number: int,
    assignees: list[str],
) -> dict[str, Any]:
    token = get_github_installation_token(installation_id)
    response = requests.patch(
        f"{GITHUB_API_BASE_URL}/repos/{owner}/{repository}/issues/{issue_number}",
        headers=get_github_app_headers(token),
        json={
            "assignees": assignees,
        },
        timeout=15,
    )
    raise_for_github_response(response)
    return response.json()


def verify_github_webhook_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret:
        return True

    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    return hmac.compare_digest(expected_signature, signature)
