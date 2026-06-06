# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import json

# Django imports
from django.db.models import Q
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder

# Third Party imports
from rest_framework.response import Response
from rest_framework import status

# Module imports
from .. import BaseViewSet
from plane.app.serializers import IssueLinkSerializer, UserLiteSerializer
from plane.app.permissions import ProjectEntityPermission
from plane.db.models import Account, IssueLink
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.work_item_link_task import crawl_work_item_link_title
from plane.utils.host import base_host


def serialize_datetime(value):
    if not value:
        return None

    return value.isoformat()


def resolve_github_development_user(github_user, project_id):
    github_user = github_user or {}
    github_id = github_user.get("id")
    github_login = github_user.get("login")

    if not github_id and not github_login:
        return None

    filters = Q()
    if github_id:
        filters |= Q(provider_account_id=str(github_id))
    if github_login:
        filters |= Q(metadata__login__iexact=str(github_login))

    account = (
        Account.objects.filter(provider="github")
        .filter(filters)
        .filter(
            user__member_project__project_id=project_id,
            user__member_project__is_active=True,
        )
        .select_related("user")
        .first()
    )

    return account.user if account else None


def serialize_plane_user(user):
    if not user:
        return None

    return UserLiteSerializer(user).data


def serialize_github_development_actor(github_user, project_id):
    github_user = github_user or {}

    return {
        **github_user,
        "plane_user": serialize_plane_user(resolve_github_development_user(github_user, project_id)),
    }


def serialize_github_commit_development_link(issue_link, project_id):
    metadata = issue_link.metadata or {}
    author_login = metadata.get("author_login")

    return {
        "id": str(issue_link.id),
        "title": issue_link.title,
        "url": issue_link.url,
        "repository_id": metadata.get("repository_id"),
        "repository": metadata.get("repository"),
        "sha": metadata.get("sha"),
        "short_sha": metadata.get("short_sha") or str(metadata.get("sha") or "")[:7],
        "message": metadata.get("message") or issue_link.title,
        "author": serialize_github_development_actor({"login": author_login}, project_id) if author_login else None,
        "author_login": author_login,
        "committed_at": metadata.get("committed_at"),
        "link_source": metadata.get("link_source"),
        "pull_request_number": metadata.get("pull_request_number"),
        "pull_request_title": metadata.get("pull_request_title"),
        "pull_request_url": metadata.get("pull_request_url"),
        "created_at": serialize_datetime(issue_link.created_at),
    }


def serialize_github_pull_request_development_link(issue_link, project_id):
    metadata = issue_link.metadata or {}

    return {
        "id": str(issue_link.id),
        "title": issue_link.title,
        "url": issue_link.url,
        "repository_id": metadata.get("repository_id"),
        "repository": metadata.get("repository"),
        "number": metadata.get("number"),
        "state": metadata.get("state"),
        "draft": metadata.get("draft"),
        "merged": metadata.get("merged"),
        "actor": serialize_github_development_actor(metadata.get("github_actor"), project_id),
        "assignees": [
            serialize_github_development_actor(assignee, project_id)
            for assignee in metadata.get("github_assignees") or []
        ],
        "created_at": serialize_datetime(issue_link.created_at),
        "updated_at": serialize_datetime(issue_link.updated_at),
        "commits": [],
    }


def get_pull_request_group_key(metadata):
    repository_id = metadata.get("repository_id")
    pull_request_number = metadata.get("number")

    if repository_id is None or pull_request_number is None:
        return None

    return (str(repository_id), str(pull_request_number))


def get_commit_pull_request_group_key(metadata):
    repository_id = metadata.get("repository_id")
    pull_request_number = metadata.get("pull_request_number")

    if repository_id is None or pull_request_number is None:
        return None

    return (str(repository_id), str(pull_request_number))


def get_fallback_pull_request_group_key(metadata, pull_request_links):
    if metadata.get("link_source") not in ["pull_request", "pull_request_backfill"]:
        return None

    repository_id = metadata.get("repository_id")
    if repository_id is None:
        return None

    matching_pull_request_keys = [
        group_key
        for group_key, pull_request_link in pull_request_links.items()
        if group_key[0] == str(repository_id) and pull_request_link is not None
    ]

    if len(matching_pull_request_keys) != 1:
        return None

    return matching_pull_request_keys[0]


class IssueLinkViewSet(BaseViewSet):
    permission_classes = [ProjectEntityPermission]

    model = IssueLink
    serializer_class = IssueLinkSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(workspace__slug=self.kwargs.get("slug"))
            .filter(project_id=self.kwargs.get("project_id"))
            .filter(issue_id=self.kwargs.get("issue_id"))
            .filter(
                project__project_projectmember__member=self.request.user,
                project__project_projectmember__is_active=True,
                project__archived_at__isnull=True,
            )
            .order_by("-created_at")
            .distinct()
        )

    def development(self, request, slug, project_id, issue_id):
        github_links = self.get_queryset().filter(
            metadata__source="github",
            metadata__type__in=["pull_request", "commit"],
        )
        pull_requests = []
        pull_request_links_by_key = {}
        orphan_commits = []

        for issue_link in github_links:
            metadata = issue_link.metadata or {}
            if metadata.get("type") != "pull_request":
                continue

            pull_request = serialize_github_pull_request_development_link(issue_link, project_id)
            pull_requests.append(pull_request)

            group_key = get_pull_request_group_key(metadata)
            if group_key:
                pull_request_links_by_key[group_key] = pull_request

        for issue_link in github_links:
            metadata = issue_link.metadata or {}
            if metadata.get("type") != "commit":
                continue

            commit = serialize_github_commit_development_link(issue_link, project_id)
            group_key = get_commit_pull_request_group_key(metadata) or get_fallback_pull_request_group_key(
                metadata,
                pull_request_links_by_key,
            )

            if group_key and group_key in pull_request_links_by_key:
                pull_request_links_by_key[group_key]["commits"].append(commit)
                continue

            orphan_commits.append(commit)

        for pull_request in pull_requests:
            pull_request["commits"] = sorted(
                pull_request["commits"],
                key=lambda commit: commit.get("committed_at") or commit.get("created_at") or "",
                reverse=True,
            )

        orphan_commits = sorted(
            orphan_commits,
            key=lambda commit: commit.get("committed_at") or commit.get("created_at") or "",
            reverse=True,
        )

        return Response(
            {
                "pull_requests": pull_requests,
                "commits": orphan_commits,
            },
            status=status.HTTP_200_OK,
        )

    def create(self, request, slug, project_id, issue_id):
        serializer = IssueLinkSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(project_id=project_id, issue_id=issue_id)
            crawl_work_item_link_title.delay(serializer.data.get("id"), serializer.data.get("url"))
            issue_activity.delay(
                type="link.activity.created",
                requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
                actor_id=str(self.request.user.id),
                issue_id=str(self.kwargs.get("issue_id")),
                project_id=str(self.kwargs.get("project_id")),
                current_instance=None,
                epoch=int(timezone.now().timestamp()),
                notification=True,
                origin=base_host(request=request, is_app=True),
            )

            issue_link = self.get_queryset().get(id=serializer.data.get("id"))
            serializer = IssueLinkSerializer(issue_link)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, slug, project_id, issue_id, pk):
        issue_link = IssueLink.objects.get(workspace__slug=slug, project_id=project_id, issue_id=issue_id, pk=pk)
        requested_data = json.dumps(request.data, cls=DjangoJSONEncoder)
        current_instance = json.dumps(IssueLinkSerializer(issue_link).data, cls=DjangoJSONEncoder)

        serializer = IssueLinkSerializer(issue_link, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            crawl_work_item_link_title.delay(serializer.data.get("id"), serializer.data.get("url"))

            issue_activity.delay(
                type="link.activity.updated",
                requested_data=requested_data,
                actor_id=str(request.user.id),
                issue_id=str(issue_id),
                project_id=str(project_id),
                current_instance=current_instance,
                epoch=int(timezone.now().timestamp()),
                notification=True,
                origin=base_host(request=request, is_app=True),
            )
            issue_link = self.get_queryset().get(id=serializer.data.get("id"))
            serializer = IssueLinkSerializer(issue_link)

            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, slug, project_id, issue_id, pk):
        issue_link = IssueLink.objects.get(workspace__slug=slug, project_id=project_id, issue_id=issue_id, pk=pk)
        current_instance = json.dumps(IssueLinkSerializer(issue_link).data, cls=DjangoJSONEncoder)
        issue_activity.delay(
            type="link.activity.deleted",
            requested_data=json.dumps({"link_id": str(pk)}),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=base_host(request=request, is_app=True),
        )
        issue_link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
