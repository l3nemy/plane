# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.app.integrations.github import verify_github_webhook_signature
from plane.app.views.integration.github import create_or_update_github_workspace_integration
from plane.db.models import (
    Account,
    GithubRepository,
    GithubRepositorySync,
    Integration,
    Issue,
    IssueAssignee,
    IssueLink,
    Project,
    ProjectMember,
    State,
    StateGroup,
    User,
    WorkspaceIntegration,
)


@pytest.mark.unit
class TestGitHubIntegration:
    def test_verify_webhook_signature(self):
        body = b'{"action":"created"}'
        secret = "github-secret"
        signature = "sha256=81280352dcf9977dce5c1ae3ca22ec770f9905af1e59ee5f4908c79df4ca8707"

        assert verify_github_webhook_signature(secret, body, signature) is True
        assert verify_github_webhook_signature(secret, body, "sha256=invalid") is False

    def test_create_workspace_integration(self, db, workspace):
        integration = Integration.objects.create(provider="github", title="GitHub")

        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=12345,
            installation={
                "account": {
                    "id": 10,
                    "login": "makeplane",
                    "type": "Organization",
                    "html_url": "https://github.com/makeplane",
                },
                "repository_selection": "selected",
                "permissions": {
                    "issues": "write",
                    "metadata": "read",
                },
                "events": ["issues"],
            },
        )

        assert workspace_integration.integration == integration
        assert workspace_integration.actor.is_bot is True
        assert workspace_integration.api_token.is_service is True
        assert workspace_integration.metadata["installation_id"] == 12345
        assert workspace_integration.metadata["account"]["login"] == "makeplane"

    def test_list_repositories_endpoint(self, db, monkeypatch, session_client, workspace):
        integration = Integration.objects.create(provider="github", title="GitHub")
        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=12345,
            installation={"account": {"login": "makeplane"}},
        )

        def list_repositories(installation_id, page=1, per_page=100):
            return {
                "repositories": [
                    {
                        "id": "100",
                        "full_name": "makeplane/plane",
                        "html_url": "https://github.com/makeplane/plane",
                        "url": "https://api.github.com/repos/makeplane/plane",
                    }
                ],
                "total_count": 1,
            }

        monkeypatch.setattr(
            "plane.app.views.integration.github.list_github_installation_repositories",
            list_repositories,
        )

        response = session_client.get(
            f"/api/workspaces/{workspace.slug}/workspace-integrations/{workspace_integration.id}/github-repositories/"
        )

        assert response.status_code == 200
        assert response.data["total_count"] == 1
        assert response.data["repositories"][0]["full_name"] == "makeplane/plane"

    def test_installation_webhook_completes_pending_workspace_integration(
        self, db, settings, session_client, workspace
    ):
        settings.GITHUB_WEBHOOK_SECRET = ""
        Integration.objects.create(provider="github", title="GitHub")

        pending_response = session_client.post(
            f"/api/workspaces/{workspace.slug}/workspace-integrations/github/",
            {},
            format="json",
        )

        assert pending_response.status_code == 202
        pending_workspace_integration = WorkspaceIntegration.objects.get(id=pending_response.data["id"])
        assert pending_workspace_integration.metadata["pending_install"] is True

        webhook_response = session_client.post(
            "/api/integrations/github/webhook",
            {
                "action": "created",
                "installation": {
                    "id": 12345,
                    "account": {
                        "id": 10,
                        "login": "makeplane",
                        "type": "Organization",
                        "html_url": "https://github.com/makeplane",
                    },
                    "repository_selection": "selected",
                    "permissions": {
                        "issues": "write",
                        "metadata": "read",
                    },
                    "events": ["issues"],
                },
            },
            format="json",
            HTTP_X_GITHUB_EVENT="installation",
        )

        assert webhook_response.status_code == 202
        pending_workspace_integration.refresh_from_db()
        assert pending_workspace_integration.metadata["pending_install"] is False
        assert pending_workspace_integration.metadata["installation_id"] == 12345
        assert pending_workspace_integration.config["installation_id"] == 12345

    def test_project_repository_sync_endpoint(self, db, session_client, create_user, workspace):
        integration = Integration.objects.create(provider="github", title="GitHub")
        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=12345,
            installation={"account": {"login": "makeplane"}},
        )
        project = Project.objects.create(name="Test Project", identifier="TP", workspace=workspace)
        ProjectMember.objects.create(project=project, member=create_user, role=20)

        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/workspace-integrations/"
            f"{workspace_integration.id}/github-repository-sync/",
            {
                "id": 100,
                "full_name": "makeplane/plane",
                "owner": {
                    "login": "makeplane",
                },
                "html_url": "https://github.com/makeplane/plane",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["repo_detail"]["full_name"] == "makeplane/plane"
        assert GithubRepositorySync.objects.filter(
            project=project, workspace_integration=workspace_integration
        ).exists()

        list_response = session_client.get(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/workspace-integrations/"
            f"{workspace_integration.id}/github-repository-sync/"
        )

        assert list_response.status_code == 200
        assert len(list_response.data) == 1
        assert list_response.data[0]["repo_detail"]["owner"] == "makeplane"

    def test_current_user_can_connect_github_account(self, db, session_client, create_user):
        response = session_client.post(
            "/api/users/me/accounts/github/",
            {
                "github_id": 501,
                "login": "jihyeok",
                "html_url": "https://github.com/jihyeok",
            },
            format="json",
        )

        assert response.status_code == 200
        account = Account.objects.get(user=create_user, provider="github")
        assert account.provider_account_id == "501"
        assert account.metadata["login"] == "jihyeok"

    def test_pull_request_webhook_links_issue_and_moves_state(
        self,
        db,
        settings,
        session_client,
        create_user,
        workspace,
        monkeypatch,
    ):
        settings.GITHUB_WEBHOOK_SECRET = ""
        settings.WEB_URL = "http://app.test"
        assignee_calls = []
        comment_calls = []

        def update_assignees(**kwargs):
            assignee_calls.append(kwargs)
            return {}

        def upsert_comment(**kwargs):
            comment_calls.append(kwargs)
            return {
                "id": 99,
                "html_url": "https://github.com/makeplane/plane/pull/7#issuecomment-99",
            }

        monkeypatch.setattr("plane.app.views.integration.github.upsert_github_issue_comment", upsert_comment)
        monkeypatch.setattr("plane.app.views.issue.base.issue_activity.delay", lambda **kwargs: None)
        monkeypatch.setattr("plane.app.views.issue.base.issue_description_version_task.delay", lambda **kwargs: None)
        monkeypatch.setattr("plane.app.views.issue.base.model_activity.delay", lambda **kwargs: None)
        monkeypatch.setattr("plane.app.views.issue.base.update_github_issue_assignees", update_assignees)

        integration = Integration.objects.create(provider="github", title="GitHub")
        Account.objects.create(
            user=create_user,
            provider="github",
            provider_account_id="501",
            access_token="",
            metadata={
                "login": "jihyeok",
            },
        )
        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=12345,
            installation={"account": {"login": "makeplane"}},
        )
        project = Project.objects.create(name="Test Project", identifier="TP", workspace=workspace)
        ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
        unstarted_state = State.objects.create(
            name="Todo",
            group=StateGroup.UNSTARTED.value,
            project=project,
            workspace=workspace,
            color="#60646C",
            sequence=25000,
            default=True,
        )
        started_state = State.objects.create(
            name="In Progress",
            group=StateGroup.STARTED.value,
            project=project,
            workspace=workspace,
            color="#F59E0B",
            sequence=35000,
        )
        completed_state = State.objects.create(
            name="Done",
            group=StateGroup.COMPLETED.value,
            project=project,
            workspace=workspace,
            color="#46A758",
            sequence=45000,
        )
        issue = Issue.objects.create(
            name="Fix GitHub sync",
            project=project,
            workspace=workspace,
            state=unstarted_state,
        )
        repository = GithubRepository.objects.create(
            name="plane",
            owner="makeplane",
            repository_id=100,
            url="https://github.com/makeplane/plane",
            project=project,
            workspace=workspace,
        )
        GithubRepositorySync.objects.create(
            repository=repository,
            actor=workspace_integration.actor,
            workspace_integration=workspace_integration,
            credentials={"installation_id": 12345},
            project=project,
            workspace=workspace,
        )

        opened_response = session_client.post(
            "/api/integrations/github/webhook",
            {
                "action": "opened",
                "installation": {"id": 12345},
                "repository": {"id": 100},
                "sender": {
                    "id": 501,
                    "login": "jihyeok",
                },
                "pull_request": {
                    "number": 7,
                    "title": "TP-1 fix GitHub sync",
                    "body": "",
                    "html_url": "https://github.com/makeplane/plane/pull/7",
                    "state": "open",
                    "draft": False,
                    "merged": False,
                    "assignees": [
                        {
                            "id": 501,
                            "login": "jihyeok",
                        }
                    ],
                    "head": {
                        "ref": "jihyeok/tp-1-github-sync",
                    },
                },
            },
            format="json",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert opened_response.status_code == 202
        assert IssueLink.objects.filter(
            issue=issue,
            url="https://github.com/makeplane/plane/pull/7",
            metadata__type="pull_request",
        ).exists()
        issue_link = IssueLink.objects.get(issue=issue, url="https://github.com/makeplane/plane/pull/7")
        assert issue_link.created_by == create_user
        assert issue_link.metadata["github_comment_id"] == 99
        assert issue_link.metadata["github_actor"]["login"] == "jihyeok"
        assert issue_link.metadata["github_assignees"][0]["login"] == "jihyeok"
        assert IssueAssignee.objects.filter(issue=issue, assignee=create_user, created_by=create_user).exists()
        assert len(comment_calls) == 1
        assert comment_calls[0]["installation_id"] == 12345
        assert comment_calls[0]["owner"] == "makeplane"
        assert comment_calls[0]["repository"] == "plane"
        assert comment_calls[0]["issue_number"] == 7
        assert "http://app.test/test-workspace/browse/TP-1" in comment_calls[0]["body"]
        issue.refresh_from_db()
        assert issue.state == started_state

        plane_assignee_response = session_client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/",
            {
                "assignee_ids": [str(create_user.id)],
            },
            format="json",
        )

        assert plane_assignee_response.status_code == 204
        assert assignee_calls[-1]["installation_id"] == 12345
        assert assignee_calls[-1]["owner"] == "makeplane"
        assert assignee_calls[-1]["repository"] == "plane"
        assert assignee_calls[-1]["issue_number"] == 7
        assert assignee_calls[-1]["assignees"] == ["jihyeok"]

        plane_unassign_response = session_client.patch(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/",
            {
                "assignee_ids": [],
            },
            format="json",
        )

        assert plane_unassign_response.status_code == 204
        assert assignee_calls[-1]["assignees"] == []

        IssueAssignee.objects.create(issue=issue, assignee=create_user, project=project, workspace=workspace)
        github_unassign_response = session_client.post(
            "/api/integrations/github/webhook",
            {
                "action": "edited",
                "installation": {"id": 12345},
                "repository": {"id": 100},
                "sender": {
                    "id": 501,
                    "login": "jihyeok",
                },
                "pull_request": {
                    "number": 7,
                    "title": "TP-1 fix GitHub sync",
                    "body": "",
                    "html_url": "https://github.com/makeplane/plane/pull/7",
                    "state": "open",
                    "draft": False,
                    "merged": False,
                    "assignees": [],
                    "head": {
                        "ref": "jihyeok/tp-1-github-sync",
                    },
                },
            },
            format="json",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert github_unassign_response.status_code == 202
        assert not IssueAssignee.objects.filter(issue=issue, assignee=create_user).exists()

        merged_response = session_client.post(
            "/api/integrations/github/webhook",
            {
                "action": "closed",
                "installation": {"id": 12345},
                "repository": {"id": 100},
                "pull_request": {
                    "number": 7,
                    "title": "TP-1 fix GitHub sync",
                    "body": "",
                    "html_url": "https://github.com/makeplane/plane/pull/7",
                    "state": "closed",
                    "draft": False,
                    "merged": True,
                    "head": {
                        "ref": "jihyeok/tp-1-github-sync",
                    },
                },
            },
            format="json",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert merged_response.status_code == 202
        issue.refresh_from_db()
        assert issue.state == completed_state

    def test_pull_request_webhook_links_pr_commits_to_issues(
        self,
        db,
        settings,
        session_client,
        create_user,
        workspace,
        monkeypatch,
    ):
        settings.GITHUB_WEBHOOK_SECRET = ""

        def list_pull_request_commits(**kwargs):
            return [
                {
                    "sha": "aaa111",
                    "html_url": "https://github.com/makeplane/plane/commit/aaa111",
                    "commit": {
                        "message": "prepare github sync",
                        "author": {
                            "date": "2026-06-01T00:00:00Z",
                        },
                    },
                    "author": {
                        "login": "jihyeok",
                    },
                },
                {
                    "sha": "bbb222",
                    "html_url": "https://github.com/makeplane/plane/commit/bbb222",
                    "commit": {
                        "message": "connect TP-2 from a PR commit\n\nwith a longer body",
                        "committer": {
                            "date": "2026-06-01T01:00:00Z",
                        },
                    },
                    "author": {
                        "login": "jihyeok",
                    },
                },
            ]

        monkeypatch.setattr(
            "plane.app.views.integration.github.list_github_pull_request_commits",
            list_pull_request_commits,
        )
        monkeypatch.setattr(
            "plane.app.views.integration.github.upsert_github_issue_comment",
            lambda **kwargs: {
                "id": 99,
                "html_url": "https://github.com/makeplane/plane/pull/7#issuecomment-99",
            },
        )

        integration = Integration.objects.create(provider="github", title="GitHub")
        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=12345,
            installation={"account": {"login": "makeplane"}},
        )
        project = Project.objects.create(name="Test Project", identifier="TP", workspace=workspace)
        ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
        Account.objects.create(
            user=create_user,
            provider="github",
            provider_account_id="github-jihyeok",
            access_token="",
            metadata={"login": "jihyeok"},
        )
        state = State.objects.create(
            name="Todo",
            group=StateGroup.UNSTARTED.value,
            project=project,
            workspace=workspace,
            color="#60646C",
            sequence=25000,
            default=True,
        )
        first_issue = Issue.objects.create(
            name="Issue from PR title",
            project=project,
            workspace=workspace,
            state=state,
        )
        second_issue = Issue.objects.create(
            name="Issue from PR commit",
            project=project,
            workspace=workspace,
            state=state,
        )
        repository = GithubRepository.objects.create(
            name="plane",
            owner="makeplane",
            repository_id=100,
            url="https://github.com/makeplane/plane",
            project=project,
            workspace=workspace,
        )
        GithubRepositorySync.objects.create(
            repository=repository,
            actor=workspace_integration.actor,
            workspace_integration=workspace_integration,
            credentials={"installation_id": 12345},
            project=project,
            workspace=workspace,
        )
        payload = {
            "action": "opened",
            "installation": {"id": 12345},
            "repository": {"id": 100},
            "pull_request": {
                "number": 7,
                "title": "TP-1 improve GitHub sync",
                "body": "",
                "html_url": "https://github.com/makeplane/plane/pull/7",
                "state": "open",
                "draft": False,
                "merged": False,
                "head": {
                    "ref": "feature/github-sync",
                },
                "assignees": [
                    {
                        "login": "jihyeok",
                    }
                ],
            },
            "sender": {
                "login": "jihyeok",
            },
        }

        opened_response = session_client.post(
            "/api/integrations/github/webhook",
            payload,
            format="json",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert opened_response.status_code == 202
        assert IssueLink.objects.filter(
            issue=first_issue,
            metadata__type="pull_request",
        ).count() == 1
        assert IssueLink.objects.filter(
            issue=first_issue,
            metadata__type="commit",
        ).count() == 2
        assert IssueLink.objects.filter(
            issue=second_issue,
            metadata__type="pull_request",
        ).count() == 1
        assert IssueLink.objects.filter(
            issue=second_issue,
            metadata__type="commit",
            metadata__sha="bbb222",
        ).count() == 1
        second_issue_commit_link = IssueLink.objects.get(
            issue=second_issue,
            metadata__type="commit",
            metadata__sha="bbb222",
        )
        assert second_issue_commit_link.title == "bbb222: connect TP-2 from a PR commit"
        assert second_issue_commit_link.metadata["pull_request_number"] == 7
        assert second_issue_commit_link.metadata["pull_request_url"] == "https://github.com/makeplane/plane/pull/7"
        assert not IssueLink.objects.filter(
            issue=second_issue,
            metadata__type="commit",
            metadata__sha="aaa111",
        ).exists()

        development_response = session_client.get(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{first_issue.id}/"
            "issue-links/development/"
        )

        assert development_response.status_code == 200
        assert len(development_response.data["pull_requests"]) == 1
        assert development_response.data["pull_requests"][0]["number"] == 7
        assert development_response.data["pull_requests"][0]["actor"]["login"] == "jihyeok"
        assert str(development_response.data["pull_requests"][0]["actor"]["plane_user"]["id"]) == str(create_user.id)
        assert development_response.data["pull_requests"][0]["assignees"][0]["login"] == "jihyeok"
        assert str(development_response.data["pull_requests"][0]["assignees"][0]["plane_user"]["id"]) == str(
            create_user.id
        )
        assert len(development_response.data["pull_requests"][0]["commits"]) == 2
        assert development_response.data["pull_requests"][0]["commits"][0]["pull_request_number"] == 7
        assert str(development_response.data["pull_requests"][0]["commits"][0]["author"]["plane_user"]["id"]) == str(
            create_user.id
        )
        assert development_response.data["commits"] == []

        duplicate_response = session_client.post(
            "/api/integrations/github/webhook",
            payload,
            format="json",
            HTTP_X_GITHUB_EVENT="pull_request",
        )

        assert duplicate_response.status_code == 202
        assert IssueLink.objects.filter(issue=first_issue).count() == 3
        assert IssueLink.objects.filter(issue=second_issue).count() == 2

    def test_repository_sync_backfills_existing_pull_request_commits(
        self,
        db,
        session_client,
        create_user,
        workspace,
        monkeypatch,
    ):
        def list_pull_request_commits(**kwargs):
            return [
                {
                    "sha": "aaa111",
                    "html_url": "https://github.com/makeplane/plane/commit/aaa111",
                    "commit": {
                        "message": "prepare github sync",
                    },
                    "author": {
                        "login": "jihyeok",
                    },
                },
                {
                    "sha": "bbb222",
                    "html_url": "https://github.com/makeplane/plane/commit/bbb222",
                    "commit": {
                        "message": "connect TP-2 from existing PR commit",
                    },
                    "author": {
                        "login": "jihyeok",
                    },
                },
            ]

        monkeypatch.setattr(
            "plane.app.views.integration.github.list_github_pull_request_commits",
            list_pull_request_commits,
        )

        integration = Integration.objects.create(provider="github", title="GitHub")
        workspace_integration = create_or_update_github_workspace_integration(
            workspace=workspace,
            integration=integration,
            installation_id=12345,
            installation={"account": {"login": "makeplane"}},
        )
        project = Project.objects.create(name="Test Project", identifier="TP", workspace=workspace)
        ProjectMember.objects.create(project=project, workspace=workspace, member=create_user, role=20)
        state = State.objects.create(
            name="Todo",
            group=StateGroup.UNSTARTED.value,
            project=project,
            workspace=workspace,
            color="#60646C",
            sequence=25000,
            default=True,
        )
        first_issue = Issue.objects.create(
            name="Issue with existing PR link",
            project=project,
            workspace=workspace,
            state=state,
        )
        second_issue = Issue.objects.create(
            name="Issue referenced by PR commit",
            project=project,
            workspace=workspace,
            state=state,
        )
        repository = GithubRepository.objects.create(
            name="plane",
            owner="makeplane",
            repository_id=100,
            url="https://github.com/makeplane/plane",
            project=project,
            workspace=workspace,
        )
        GithubRepositorySync.objects.create(
            repository=repository,
            actor=workspace_integration.actor,
            workspace_integration=workspace_integration,
            credentials={"installation_id": 12345},
            project=project,
            workspace=workspace,
        )
        IssueLink.objects.create(
            issue=first_issue,
            title="GitHub PR #7: TP-1 improve GitHub sync",
            url="https://github.com/makeplane/plane/pull/7",
            metadata={
                "source": "github",
                "type": "pull_request",
                "repository_id": 100,
                "repository": "makeplane/plane",
                "number": 7,
            },
            project=project,
            workspace=workspace,
            created_by=workspace_integration.actor,
        )
        IssueLink.objects.create(
            issue=first_issue,
            title="aaa111: prepare github sync",
            url="https://github.com/makeplane/plane/commit/aaa111",
            metadata={
                "source": "github",
                "type": "commit",
                "link_source": "pull_request_backfill",
                "repository_id": 100,
                "repository": "makeplane/plane",
                "sha": "aaa111",
            },
            project=project,
            workspace=workspace,
            created_by=workspace_integration.actor,
        )

        response = session_client.get(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/workspace-integrations/"
            f"{workspace_integration.id}/github-repository-sync/"
        )

        assert response.status_code == 200
        assert IssueLink.objects.filter(
            issue=first_issue,
            metadata__type="commit",
        ).count() == 2
        assert IssueLink.objects.get(
            issue=first_issue,
            metadata__type="commit",
            metadata__sha="aaa111",
        ).title == "aaa111: prepare github sync"
        assert (
            IssueLink.objects.get(
                issue=first_issue,
                metadata__type="commit",
                metadata__sha="aaa111",
            ).metadata["pull_request_number"]
            == 7
        )
        assert IssueLink.objects.filter(
            issue=second_issue,
            metadata__type="pull_request",
            metadata__number=7,
        ).exists()
        assert IssueLink.objects.filter(
            issue=second_issue,
            metadata__type="commit",
            metadata__sha="bbb222",
        ).count() == 1
        assert not IssueLink.objects.filter(
            issue=second_issue,
            metadata__type="commit",
            metadata__sha="aaa111",
        ).exists()

    def test_install_callback_requires_workspace_admin(self, db, api_client, workspace):
        user = User.objects.create(
            email="non-admin@plane.so",
            username="non_admin",
            first_name="Non",
            last_name="Admin",
        )
        api_client.force_authenticate(user=user)

        response = api_client.get(
            "/api/integrations/github/callback/",
            {
                "state": workspace.slug,
                "installation_id": 12345,
            },
        )

        assert response.status_code == 403
        assert WorkspaceIntegration.objects.count() == 0
