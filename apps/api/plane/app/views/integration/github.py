# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging
import re

# Django imports
from django.conf import settings
from django.http import HttpResponse
from django.db.models import Q

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Module imports
from plane.app.integrations import sync_registered_integration_providers
from plane.app.integrations.github import (
    GitHubAppAPIError,
    GitHubAppConfigurationError,
    get_github_installation,
    list_github_pull_request_commits,
    list_github_installation_repositories,
    upsert_github_issue_comment,
    verify_github_webhook_signature,
)
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import GithubRepositorySyncSerializer, WorkspaceIntegrationSerializer
from plane.db.models import (
    APIToken,
    Account,
    GithubIssueSync,
    GithubRepository,
    GithubRepositorySync,
    Integration,
    Issue,
    IssueAssignee,
    IssueLink,
    Project,
    State,
    StateGroup,
    User,
    Workspace,
    WorkspaceIntegration,
    WorkspaceMember,
)
from ..base import BaseAPIView


ISSUE_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,11})-(\d+)\b")
logger = logging.getLogger(__name__)


def extract_issue_keys(*values) -> set[tuple[str, int]]:
    issue_keys = set()
    for value in values:
        if not value:
            continue

        for project_identifier, sequence_id in ISSUE_KEY_PATTERN.findall(str(value).upper()):
            issue_keys.add((project_identifier, int(sequence_id)))

    return issue_keys


def get_repository_syncs_for_github_payload(payload: dict):
    repository = payload.get("repository") or {}
    repository_id = repository.get("id")
    installation_id = (payload.get("installation") or {}).get("id")

    if not repository_id:
        return GithubRepositorySync.objects.none()

    repository_syncs = GithubRepositorySync.objects.filter(
        repository__repository_id=repository_id,
    ).select_related("repository", "project", "workspace", "workspace_integration", "actor")

    if installation_id:
        repository_syncs = repository_syncs.filter(
            Q(workspace_integration__metadata__installation_id=installation_id)
            | Q(workspace_integration__config__installation_id=installation_id)
        )

    return repository_syncs


def get_linkable_issues(repository_sync: GithubRepositorySync, issue_keys: set[tuple[str, int]]):
    sequence_ids = [
        sequence_id
        for project_identifier, sequence_id in issue_keys
        if project_identifier == repository_sync.project.identifier
    ]

    if not sequence_ids:
        return Issue.issue_objects.none()

    return Issue.issue_objects.filter(
        workspace_id=repository_sync.workspace_id,
        project_id=repository_sync.project_id,
        sequence_id__in=sequence_ids,
    ).select_related("state", "project", "workspace")


def resolve_github_account_user(github_user: dict | None, project_id=None) -> User | None:
    if not github_user:
        return None

    github_id = github_user.get("id")
    github_login = github_user.get("login")

    if not github_id and not github_login:
        return None

    filters = Q()
    if github_id:
        filters |= Q(provider_account_id=str(github_id))
    if github_login:
        filters |= Q(metadata__login__iexact=str(github_login))

    accounts = Account.objects.filter(provider="github").filter(filters).select_related("user")

    if project_id:
        accounts = accounts.filter(
            user__member_project__project_id=project_id,
            user__member_project__is_active=True,
        )

    account = accounts.first()
    return account.user if account else None


def resolve_github_assignee_users(github_users: list[dict], project_id) -> list[User]:
    users = []
    seen_user_ids = set()

    for github_user in github_users or []:
        user = resolve_github_account_user(github_user, project_id=project_id)
        if not user or user.id in seen_user_ids:
            continue

        seen_user_ids.add(user.id)
        users.append(user)

    return users


def sync_issue_assignees_from_github(
    *,
    issue: Issue,
    repository_sync: GithubRepositorySync,
    github_assignees: list[dict],
    actor: User | None,
) -> int:
    if not repository_sync.repository.config.get("sync_assignees", True):
        return 0

    assignee_users = resolve_github_assignee_users(github_assignees, project_id=issue.project_id)
    assignee_user_ids = [assignee_user.id for assignee_user in assignee_users]
    mapped_project_user_ids = Account.objects.filter(
        provider="github",
        user__member_project__project_id=issue.project_id,
        user__member_project__is_active=True,
    ).values_list("user_id", flat=True)

    IssueAssignee.objects.filter(
        issue=issue,
        assignee_id__in=mapped_project_user_ids,
    ).exclude(assignee_id__in=assignee_user_ids).delete()

    synced_count = 0

    for assignee_user in assignee_users:
        _, created = IssueAssignee.objects.get_or_create(
            issue=issue,
            assignee=assignee_user,
            defaults={
                "workspace_id": issue.workspace_id,
                "project_id": issue.project_id,
                "created_by": actor or repository_sync.actor,
            },
        )
        if created:
            synced_count += 1

    return synced_count


def sync_github_issue_link(
    *,
    issue: Issue,
    repository_sync: GithubRepositorySync,
    title: str,
    url: str,
    metadata: dict,
    actor: User | None = None,
) -> IssueLink:
    issue_link, created = IssueLink.objects.get_or_create(
        issue=issue,
        url=url,
        defaults={
            "title": title[:255],
            "metadata": metadata,
            "workspace_id": issue.workspace_id,
            "project_id": issue.project_id,
            "created_by": actor or repository_sync.actor,
        },
    )

    if created:
        return issue_link

    issue_link.title = title[:255]
    issue_link.metadata = {
        **(issue_link.metadata or {}),
        **metadata,
    }
    issue_link.save(update_fields=["title", "metadata", "updated_at"])
    return issue_link


def get_github_commit_sha(commit: dict) -> str:
    return str(commit.get("id") or commit.get("sha") or "")


def get_github_commit_message(commit: dict) -> str:
    commit_detail = commit.get("commit") or {}
    return str(commit.get("message") or commit_detail.get("message") or "")


def get_github_commit_title(commit: dict) -> str:
    commit_sha = get_github_commit_sha(commit)
    commit_lines = get_github_commit_message(commit).splitlines()
    commit_subject = ""

    for commit_line in commit_lines:
        commit_subject = " ".join(commit_line.split())
        if commit_subject:
            break

    if commit_subject:
        return f"{commit_sha[:7]}: {commit_subject}"[:255]

    return f"GitHub commit {commit_sha[:7]}"


def get_github_commit_url(commit: dict) -> str:
    return str(commit.get("html_url") or commit.get("url") or "")


def get_github_commit_author(commit: dict) -> dict:
    return commit.get("author") or {}


def get_github_commit_committed_at(commit: dict) -> str | None:
    commit_detail = commit.get("commit") or {}
    committer = commit_detail.get("committer") or {}
    author = commit_detail.get("author") or {}
    return commit.get("timestamp") or committer.get("date") or author.get("date")


def sync_github_commit_link(
    *,
    issue: Issue,
    repository_sync: GithubRepositorySync,
    commit: dict,
    source: str,
    pull_request: dict | None = None,
) -> IssueLink | None:
    commit_url = get_github_commit_url(commit)
    commit_sha = get_github_commit_sha(commit)

    if not commit_url or not commit_sha:
        return None

    pull_request_metadata = {}
    if pull_request:
        pull_request_metadata = {
            "pull_request_number": pull_request.get("number"),
            "pull_request_title": pull_request.get("title"),
            "pull_request_url": pull_request.get("html_url"),
        }

    return sync_github_issue_link(
        issue=issue,
        repository_sync=repository_sync,
        title=get_github_commit_title(commit),
        url=commit_url,
        metadata={
            "source": "github",
            "type": "commit",
            "link_source": source,
            "repository_id": repository_sync.repository.repository_id,
            "repository": f"{repository_sync.repository.owner}/{repository_sync.repository.name}",
            "sha": commit_sha,
            "short_sha": commit_sha[:7],
            "message": get_github_commit_message(commit),
            "author_login": get_github_commit_author(commit).get("login")
            or get_github_commit_author(commit).get("username"),
            "committed_at": get_github_commit_committed_at(commit),
            **pull_request_metadata,
        },
    )


def build_issue_app_url(issue: Issue) -> str:
    app_base_url = getattr(settings, "WEB_URL", None) or getattr(settings, "APP_BASE_URL", None) or ""
    if not app_base_url:
        return ""

    return (
        f"{app_base_url.rstrip('/')}/{issue.workspace.slug}/browse/"
        f"{issue.project.identifier}-{issue.sequence_id}"
    )


def comment_connected_issue_on_github(
    *,
    issue: Issue,
    issue_link: IssueLink,
    repository_sync: GithubRepositorySync,
    github_issue_number: int | None,
) -> None:
    if not repository_sync.repository.config.get("comment_connected_issue", True):
        return

    if not github_issue_number:
        return

    installation_id = get_github_installation_id(repository_sync.workspace_integration)
    issue_app_url = build_issue_app_url(issue)

    if not installation_id or not issue_app_url:
        return

    issue_key = f"{issue.project.identifier}-{issue.sequence_id}"
    marker = f"<!-- plane-connected-issue:{issue.id} -->"
    body = (
        f"{marker}\n"
        f"Connected Plane issue: [{issue_key} {issue.name}]({issue_app_url})"
    )

    try:
        github_comment = upsert_github_issue_comment(
            installation_id=installation_id,
            owner=repository_sync.repository.owner,
            repository=repository_sync.repository.name,
            issue_number=int(github_issue_number),
            marker=marker,
            body=body,
        )
    except (GitHubAppAPIError, GitHubAppConfigurationError, ValueError) as exc:
        logger.warning(
            "Could not comment connected Plane issue on GitHub",
            extra={
                "issue_id": str(issue.id),
                "repository_sync_id": str(repository_sync.id),
                "github_issue_number": github_issue_number,
                "error": str(exc),
            },
        )
        return

    issue_link.metadata = {
        **(issue_link.metadata or {}),
        "github_comment_id": github_comment.get("id"),
        "github_comment_url": github_comment.get("html_url"),
    }
    issue_link.save(update_fields=["metadata", "updated_at"])


def move_issue_to_state_group(issue: Issue, state_group: str) -> bool:
    next_state = State.objects.filter(
        workspace_id=issue.workspace_id,
        project_id=issue.project_id,
        group=state_group,
    ).first()

    if not next_state or issue.state_id == next_state.id:
        return False

    issue.state = next_state
    issue.save(update_fields=["state", "completed_at", "updated_at"])
    return True


def get_pull_request_commits(repository_sync: GithubRepositorySync, pull_request: dict) -> list[dict]:
    installation_id = get_github_installation_id(repository_sync.workspace_integration)
    pull_number = pull_request.get("number")

    if not installation_id or not pull_number:
        return []

    try:
        return list_github_pull_request_commits(
            installation_id=installation_id,
            owner=repository_sync.repository.owner,
            repository=repository_sync.repository.name,
            pull_number=int(pull_number),
        )
    except (GitHubAppAPIError, GitHubAppConfigurationError, ValueError) as exc:
        logger.warning(
            "Could not fetch GitHub pull request commits",
            extra={
                "repository_sync_id": str(repository_sync.id),
                "pull_number": pull_number,
                "error": str(exc),
            },
        )
        return []


def get_commit_issue_keys_by_sha(commits: list[dict]) -> dict[str, set[tuple[str, int]]]:
    return {
        get_github_commit_sha(commit): extract_issue_keys(get_github_commit_message(commit))
        for commit in commits
        if get_github_commit_sha(commit)
    }


def sync_pull_request_commits_to_issue(
    *,
    issue: Issue,
    repository_sync: GithubRepositorySync,
    pull_request: dict,
    pull_request_commits: list[dict],
    commit_issue_keys_by_sha: dict[str, set[tuple[str, int]]],
    pull_request_issue_keys: set[tuple[str, int]],
    source: str,
) -> int:
    link_count = 0
    issue_key = (repository_sync.project.identifier, issue.sequence_id)

    for commit in pull_request_commits:
        commit_sha = get_github_commit_sha(commit)
        commit_issue_keys = commit_issue_keys_by_sha.get(commit_sha, set())

        if issue_key not in pull_request_issue_keys and issue_key not in commit_issue_keys:
            continue

        if sync_github_commit_link(
            issue=issue,
            repository_sync=repository_sync,
            commit=commit,
            source=source,
            pull_request=pull_request,
        ):
            link_count += 1

    return link_count


def build_pull_request_link_metadata(
    *,
    repository_sync: GithubRepositorySync,
    pull_request: dict,
    sender: dict | None = None,
) -> dict:
    return {
        "source": "github",
        "type": "pull_request",
        "github_actor": sender or {},
        "github_assignees": pull_request.get("assignees") or [],
        "repository_id": repository_sync.repository.repository_id,
        "repository": f"{repository_sync.repository.owner}/{repository_sync.repository.name}",
        "number": pull_request.get("number"),
        "state": pull_request.get("state"),
        "draft": pull_request.get("draft"),
        "merged": pull_request.get("merged"),
    }


def sync_pull_request_webhook(payload: dict, action: str) -> int:
    pull_request = payload.get("pull_request") or {}
    head = pull_request.get("head") or {}
    pull_request_issue_keys = extract_issue_keys(
        pull_request.get("title"),
        pull_request.get("body"),
        head.get("ref"),
    )

    link_count = 0
    for repository_sync in get_repository_syncs_for_github_payload(payload):
        pull_request_commits = get_pull_request_commits(repository_sync, pull_request)
        commit_issue_keys_by_sha = get_commit_issue_keys_by_sha(pull_request_commits)
        commit_issue_keys = set().union(*commit_issue_keys_by_sha.values()) if commit_issue_keys_by_sha else set()
        issue_keys = pull_request_issue_keys | commit_issue_keys

        if not issue_keys:
            continue

        actor = resolve_github_account_user(payload.get("sender"), project_id=repository_sync.project_id)
        linked_issues = get_linkable_issues(repository_sync, issue_keys)
        for issue in linked_issues:
            if not pull_request.get("html_url"):
                continue

            issue_link = sync_github_issue_link(
                issue=issue,
                repository_sync=repository_sync,
                title=f"GitHub PR #{pull_request.get('number')}: {pull_request.get('title')}",
                url=pull_request.get("html_url"),
                metadata=build_pull_request_link_metadata(
                    repository_sync=repository_sync,
                    pull_request=pull_request,
                    sender=payload.get("sender"),
                ),
                actor=actor,
            )
            if "assignees" in pull_request:
                sync_issue_assignees_from_github(
                    issue=issue,
                    repository_sync=repository_sync,
                    github_assignees=pull_request.get("assignees") or [],
                    actor=actor,
                )
            comment_connected_issue_on_github(
                issue=issue,
                issue_link=issue_link,
                repository_sync=repository_sync,
                github_issue_number=pull_request.get("number"),
            )
            link_count += 1

            link_count += sync_pull_request_commits_to_issue(
                issue=issue,
                repository_sync=repository_sync,
                pull_request=pull_request,
                pull_request_commits=pull_request_commits,
                commit_issue_keys_by_sha=commit_issue_keys_by_sha,
                pull_request_issue_keys=pull_request_issue_keys,
                source="pull_request",
            )

            if repository_sync.repository.config.get("status_automation", True):
                if action in ["opened", "reopened", "ready_for_review"] and not pull_request.get("draft"):
                    move_issue_to_state_group(issue, StateGroup.STARTED.value)
                elif action == "closed" and pull_request.get("merged"):
                    move_issue_to_state_group(issue, StateGroup.COMPLETED.value)

    return link_count


def backfill_existing_pull_request_commits(
    repository_sync: GithubRepositorySync,
    *,
    only_missing: bool = False,
) -> int:
    pull_request_links = IssueLink.objects.filter(
        workspace_id=repository_sync.workspace_id,
        project_id=repository_sync.project_id,
        metadata__source="github",
        metadata__type="pull_request",
        metadata__repository_id=repository_sync.repository.repository_id,
    ).select_related("issue", "issue__project")
    link_count = 0

    for pull_request_link in pull_request_links:
        metadata = pull_request_link.metadata or {}
        pull_request_number = metadata.get("number")
        if not pull_request_number:
            continue

        pull_request_commit_links = IssueLink.objects.filter(
            issue=pull_request_link.issue,
            metadata__source="github",
            metadata__type="commit",
            metadata__repository_id=repository_sync.repository.repository_id,
            metadata__link_source__in=["pull_request", "pull_request_backfill"],
        )
        has_commit_links_missing_pull_request_context = any(
            not (commit_link.metadata or {}).get("pull_request_number") for commit_link in pull_request_commit_links
        )
        if (
            only_missing
            and pull_request_commit_links.exists()
            and not has_commit_links_missing_pull_request_context
            and not pull_request_commit_links.filter(title__startswith="GitHub commit ").exists()
        ):
            continue

        pull_request = {
            **metadata,
            "number": pull_request_number,
            "html_url": pull_request_link.url,
            "title": pull_request_link.title or f"GitHub PR #{pull_request_number}",
        }
        pull_request_commits = get_pull_request_commits(repository_sync, pull_request)
        commit_issue_keys_by_sha = get_commit_issue_keys_by_sha(pull_request_commits)
        commit_issue_keys = set().union(*commit_issue_keys_by_sha.values()) if commit_issue_keys_by_sha else set()
        pull_request_issue_keys = {
            (repository_sync.project.identifier, pull_request_link.issue.sequence_id),
        }

        link_count += sync_pull_request_commits_to_issue(
            issue=pull_request_link.issue,
            repository_sync=repository_sync,
            pull_request=pull_request,
            pull_request_commits=pull_request_commits,
            commit_issue_keys_by_sha=commit_issue_keys_by_sha,
            pull_request_issue_keys=pull_request_issue_keys,
            source="pull_request_backfill",
        )

        for issue in get_linkable_issues(repository_sync, commit_issue_keys).exclude(id=pull_request_link.issue_id):
            sync_github_issue_link(
                issue=issue,
                repository_sync=repository_sync,
                title=pull_request_link.title or f"GitHub PR #{pull_request_number}",
                url=pull_request_link.url,
                metadata={
                    **build_pull_request_link_metadata(
                        repository_sync=repository_sync,
                        pull_request=pull_request,
                    ),
                    "backfilled": True,
                },
            )
            link_count += 1
            link_count += sync_pull_request_commits_to_issue(
                issue=issue,
                repository_sync=repository_sync,
                pull_request=pull_request,
                pull_request_commits=pull_request_commits,
                commit_issue_keys_by_sha=commit_issue_keys_by_sha,
                pull_request_issue_keys=pull_request_issue_keys,
                source="pull_request_backfill",
            )

    return link_count


def sync_push_webhook(payload: dict) -> int:
    ref = payload.get("ref") or ""
    commits = payload.get("commits") or []
    issue_keys = extract_issue_keys(
        ref,
        *((commit.get("message") for commit in commits if commit)),
    )

    if not issue_keys:
        return 0

    link_count = 0
    for repository_sync in get_repository_syncs_for_github_payload(payload):
        linked_issues = get_linkable_issues(repository_sync, issue_keys)
        for issue in linked_issues:
            for commit in commits:
                if not commit or not commit.get("url"):
                    continue

                commit_issue_keys = extract_issue_keys(ref, commit.get("message"))
                if (repository_sync.project.identifier, issue.sequence_id) not in commit_issue_keys:
                    continue

                if sync_github_commit_link(
                    issue=issue,
                    repository_sync=repository_sync,
                    commit=commit,
                    source="push",
                ):
                    link_count += 1

    return link_count


def sync_github_issue_webhook(payload: dict) -> int:
    github_issue = payload.get("issue") or {}
    issue_keys = extract_issue_keys(github_issue.get("title"), github_issue.get("body"))

    if not issue_keys:
        return 0

    link_count = 0
    for repository_sync in get_repository_syncs_for_github_payload(payload):
        actor = resolve_github_account_user(payload.get("sender"), project_id=repository_sync.project_id)
        linked_issues = get_linkable_issues(repository_sync, issue_keys)
        for issue in linked_issues:
            if not github_issue.get("html_url"):
                continue

            GithubIssueSync.objects.update_or_create(
                repository_sync=repository_sync,
                issue=issue,
                defaults={
                    "repo_issue_id": github_issue.get("number"),
                    "github_issue_id": github_issue.get("id"),
                    "issue_url": github_issue.get("html_url"),
                    "workspace_id": issue.workspace_id,
                    "project_id": issue.project_id,
                },
            )
            issue_link = sync_github_issue_link(
                issue=issue,
                repository_sync=repository_sync,
                title=f"GitHub issue #{github_issue.get('number')}: {github_issue.get('title')}",
                url=github_issue.get("html_url"),
                metadata={
                    "source": "github",
                    "type": "issue",
                    "github_actor": payload.get("sender") or {},
                    "github_assignees": github_issue.get("assignees") or [],
                    "repository_id": repository_sync.repository.repository_id,
                    "repository": f"{repository_sync.repository.owner}/{repository_sync.repository.name}",
                    "number": github_issue.get("number"),
                    "state": github_issue.get("state"),
                },
                actor=actor,
            )
            if "assignees" in github_issue:
                sync_issue_assignees_from_github(
                    issue=issue,
                    repository_sync=repository_sync,
                    github_assignees=github_issue.get("assignees") or [],
                    actor=actor,
                )
            comment_connected_issue_on_github(
                issue=issue,
                issue_link=issue_link,
                repository_sync=repository_sync,
                github_issue_number=github_issue.get("number"),
            )
            link_count += 1

    return link_count


def get_github_bot_user(workspace: Workspace) -> User:
    username = f"github_bot_{workspace.id.hex[:24]}"
    email = f"github-bot-{workspace.id.hex}@plane.so"
    bot_user, _ = User.objects.get_or_create(
        email=email,
        defaults={
            "username": username,
            "display_name": "GitHub Bot",
            "first_name": "GitHub",
            "last_name": "Bot",
            "is_bot": True,
            "bot_type": "GITHUB",
        },
    )

    if not bot_user.is_bot or bot_user.bot_type != "GITHUB":
        bot_user.is_bot = True
        bot_user.bot_type = "GITHUB"
        bot_user.save(update_fields=["is_bot", "bot_type", "updated_at"])

    return bot_user


def get_github_bot_token(workspace: Workspace, bot_user: User) -> APIToken:
    api_token = APIToken.objects.filter(
        user=bot_user,
        workspace=workspace,
        is_service=True,
        label="GitHub Integration",
    ).first()

    if api_token:
        return api_token

    return APIToken.objects.create(
        label="GitHub Integration",
        description="Service token for the GitHub integration.",
        user=bot_user,
        user_type=1,
        workspace=workspace,
        is_service=True,
        allowed_rate_limit=getattr(settings, "API_KEY_RATE_LIMIT", "60/min"),
    )


def create_or_update_github_workspace_integration(
    *,
    workspace: Workspace,
    integration: Integration,
    installation_id: int,
    installation: dict,
) -> WorkspaceIntegration:
    bot_user = get_github_bot_user(workspace)
    api_token = get_github_bot_token(workspace, bot_user)
    account = installation.get("account") or {}
    metadata = {
        "installation_id": installation_id,
        "pending_install": False,
        "account": {
            "id": account.get("id"),
            "login": account.get("login"),
            "type": account.get("type"),
            "html_url": account.get("html_url"),
        },
        "repository_selection": installation.get("repository_selection"),
        "permissions": installation.get("permissions") or {},
        "events": installation.get("events") or [],
    }

    workspace_integration, created = WorkspaceIntegration.objects.get_or_create(
        workspace=workspace,
        integration=integration,
        defaults={
            "actor": bot_user,
            "api_token": api_token,
            "metadata": metadata,
            "config": {
                "installation_id": installation_id,
            },
        },
    )

    if created:
        return workspace_integration

    workspace_integration.actor = bot_user
    workspace_integration.api_token = api_token
    workspace_integration.metadata = {
        **(workspace_integration.metadata or {}),
        **metadata,
        "pending_install": False,
    }
    workspace_integration.config = {
        **(workspace_integration.config or {}),
        "installation_id": installation_id,
    }
    workspace_integration.save(update_fields=["actor", "api_token", "metadata", "config", "updated_at"])
    return workspace_integration


def create_pending_github_workspace_integration(
    *,
    workspace: Workspace,
    integration: Integration,
) -> WorkspaceIntegration:
    bot_user = get_github_bot_user(workspace)
    api_token = get_github_bot_token(workspace, bot_user)
    workspace_integration, created = WorkspaceIntegration.objects.get_or_create(
        workspace=workspace,
        integration=integration,
        defaults={
            "actor": bot_user,
            "api_token": api_token,
            "metadata": {
                "pending_install": True,
            },
            "config": {},
        },
    )

    if created:
        return workspace_integration

    workspace_integration.actor = bot_user
    workspace_integration.api_token = api_token
    metadata = dict(workspace_integration.metadata or {})
    previous_installation_id = metadata.pop("installation_id", None) or (workspace_integration.config or {}).get(
        "installation_id"
    )
    metadata.pop("account", None)
    metadata.pop("repository_selection", None)
    metadata.pop("permissions", None)
    metadata.pop("events", None)
    metadata.pop("suspended", None)
    if previous_installation_id:
        metadata["previous_installation_id"] = previous_installation_id
    workspace_integration.metadata = {
        **metadata,
        "pending_install": True,
    }
    config = dict(workspace_integration.config or {})
    config.pop("installation_id", None)
    workspace_integration.config = config
    workspace_integration.save(update_fields=["actor", "api_token", "metadata", "config", "updated_at"])
    return workspace_integration


def get_github_installation_id(workspace_integration: WorkspaceIntegration) -> int | None:
    installation_id = (workspace_integration.config or {}).get("installation_id") or (
        workspace_integration.metadata or {}
    ).get("installation_id")

    if not installation_id:
        return None

    return int(installation_id)


def user_is_workspace_admin(user: User, workspace: Workspace) -> bool:
    return WorkspaceMember.objects.filter(
        workspace=workspace,
        member=user,
        role=ROLE.ADMIN.value,
        is_active=True,
    ).exists()


def build_popup_response(workspace: Workspace, status_text: str) -> HttpResponse:
    app_base_url = getattr(settings, "APP_BASE_URL", None) or getattr(settings, "WEB_URL", "") or ""
    redirect_url = f"{app_base_url.rstrip('/')}/{workspace.slug}/settings/integrations" if app_base_url else ""
    body = f"""
    <!doctype html>
    <html>
      <head><title>GitHub integration</title></head>
      <body>
        <script>
          if (window.opener) {{
            window.opener.postMessage({{"type": "plane:integration:github", "status": "{status_text}"}}, "*");
            window.close();
          }} else if ("{redirect_url}") {{
            window.location.href = "{redirect_url}";
          }}
        </script>
      </body>
    </html>
    """
    return HttpResponse(body, content_type="text/html")


def install_github_workspace_integration(*, request, workspace, integration):
    installation_id = request.data.get("installation_id")
    if not installation_id:
        workspace_integration = create_pending_github_workspace_integration(
            workspace=workspace,
            integration=integration,
        )
        serializer = WorkspaceIntegrationSerializer(workspace_integration)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    try:
        installation_id = int(installation_id)
        installation = get_github_installation(installation_id)
        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=installation_id,
            installation=installation,
        )
    except (GitHubAppAPIError, GitHubAppConfigurationError, ValueError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    serializer = WorkspaceIntegrationSerializer(workspace_integration)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


class GitHubInstallationCallbackEndpoint(BaseAPIView):
    def get(self, request):
        workspace_slug = request.GET.get("state")
        installation_id = request.GET.get("installation_id")

        if not workspace_slug or not installation_id:
            return Response(
                {"error": "state and installation_id query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        workspace = Workspace.objects.get(slug=workspace_slug)
        if not user_is_workspace_admin(request.user, workspace):
            return Response(
                {"error": "You don't have the required permissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        sync_registered_integration_providers()
        integration = Integration.objects.get(provider="github")

        try:
            installation_id = int(installation_id)
            installation = get_github_installation(installation_id)
            create_or_update_github_workspace_integration(
                workspace=workspace,
                integration=integration,
                installation_id=installation_id,
                installation=installation,
            )
        except (GitHubAppAPIError, GitHubAppConfigurationError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return build_popup_response(workspace, "installed")


class GitHubRepositoriesEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug, workspace_integration_id):
        workspace_integration = WorkspaceIntegration.objects.get(
            id=workspace_integration_id,
            workspace__slug=slug,
            integration__provider="github",
        )
        installation_id = get_github_installation_id(workspace_integration)

        if not installation_id:
            return Response(
                {"error": "GitHub installation_id is not configured for this workspace integration."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            repositories = list_github_installation_repositories(
                installation_id=installation_id,
                page=int(request.GET.get("page", 1)),
                per_page=int(request.GET.get("per_page", 100)),
            )
        except (GitHubAppAPIError, GitHubAppConfigurationError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(repositories, status=status.HTTP_200_OK)


class GitHubRepositorySyncEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=[ROLE.ADMIN], level="PROJECT")
    def get(self, request, slug, project_id, workspace_integration_id):
        repository_syncs = GithubRepositorySync.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            workspace_integration_id=workspace_integration_id,
            workspace_integration__integration__provider="github",
        ).select_related("repository")

        backfill_pr_commits = request.GET.get("backfill_pr_commits") in ["1", "true", "True"]
        for repository_sync in repository_syncs:
            backfill_existing_pull_request_commits(repository_sync, only_missing=not backfill_pr_commits)

        serializer = GithubRepositorySyncSerializer(repository_syncs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="PROJECT")
    def post(self, request, slug, project_id, workspace_integration_id):
        workspace_integration = WorkspaceIntegration.objects.get(
            id=workspace_integration_id,
            workspace__slug=slug,
            integration__provider="github",
        )
        project = Project.objects.get(id=project_id, workspace__slug=slug)

        repository_id = request.data.get("repository_id") or request.data.get("id")
        full_name = request.data.get("full_name") or ""
        name = request.data.get("name") or full_name.split("/")[-1]
        owner = request.data.get("owner")
        url = request.data.get("url") or request.data.get("html_url")

        if isinstance(owner, dict):
            owner = owner.get("login")

        if not repository_id or not name or not owner or not url:
            return Response(
                {"error": "repository_id, name, owner, and url are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repository, _ = GithubRepository.objects.update_or_create(
            project=project,
            repository_id=repository_id,
            defaults={
                "name": name,
                "owner": owner,
                "url": url,
                "config": request.data.get("config") or {},
            },
        )
        GithubRepositorySync.objects.filter(
            project=project,
            workspace_integration=workspace_integration,
        ).exclude(repository=repository).delete()
        repository_sync, _ = GithubRepositorySync.objects.update_or_create(
            project=project,
            repository=repository,
            defaults={
                "actor": workspace_integration.actor,
                "workspace_integration": workspace_integration,
                "credentials": {
                    "installation_id": get_github_installation_id(workspace_integration),
                },
            },
        )
        backfill_existing_pull_request_commits(repository_sync)
        serializer = GithubRepositorySyncSerializer(repository_sync)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GitHubWebhookEndpoint(BaseAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        secret = getattr(settings, "GITHUB_WEBHOOK_SECRET", "")
        signature = request.headers.get("X-Hub-Signature-256")

        if not verify_github_webhook_signature(secret, request.body, signature):
            return Response({"error": "Invalid GitHub webhook signature."}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data
        event = request.headers.get("X-GitHub-Event", "")
        action = payload.get("action")
        installation = payload.get("installation") or {}
        installation_id = installation.get("id")

        if installation_id and event == "installation" and action == "created":
            sync_registered_integration_providers()
            integration = Integration.objects.get(provider="github")
            workspace_integrations = WorkspaceIntegration.objects.filter(
                Q(metadata__installation_id=installation_id) | Q(config__installation_id=installation_id),
                integration=integration,
            )

            if not workspace_integrations.exists():
                workspace_integrations = WorkspaceIntegration.objects.filter(
                    integration=integration,
                    metadata__pending_install=True,
                ).order_by("-updated_at")[:1]

            for workspace_integration in workspace_integrations:
                create_or_update_github_workspace_integration(
                    workspace=workspace_integration.workspace,
                    integration=integration,
                    installation_id=int(installation_id),
                    installation=installation,
                )
        elif installation_id and event == "installation" and action == "deleted":
            WorkspaceIntegration.objects.filter(
                integration__provider="github",
            ).filter(
                Q(metadata__installation_id=installation_id) | Q(config__installation_id=installation_id)
            ).delete()
        elif installation_id and event == "installation" and action in ["suspend", "unsuspend"]:
            workspace_integrations = WorkspaceIntegration.objects.filter(
                Q(metadata__installation_id=installation_id) | Q(config__installation_id=installation_id),
                integration__provider="github",
            )
            for workspace_integration in workspace_integrations:
                workspace_integration.metadata = {
                    **(workspace_integration.metadata or {}),
                    "suspended": action == "suspend",
                }
                workspace_integration.save(update_fields=["metadata", "updated_at"])
        elif event == "pull_request":
            sync_pull_request_webhook(payload, action)
        elif event == "push":
            sync_push_webhook(payload)
        elif event == "issues" and action in ["opened", "edited", "reopened", "closed"]:
            sync_github_issue_webhook(payload)

        return Response(
            {
                "event": event,
                "action": action,
                "installation_id": installation_id,
            },
            status=status.HTTP_202_ACCEPTED,
        )
