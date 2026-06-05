# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from .base import DynamicBaseSerializer
from plane.db.models import GithubRepository, GithubRepositorySync, Integration, WorkspaceIntegration


class IntegrationSerializer(DynamicBaseSerializer):
    metadata = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = "__all__"
        read_only_fields = [
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    def get_metadata(self, obj):
        metadata = dict(obj.metadata or {})

        if obj.redirect_url and "install_url" not in metadata:
            metadata["install_url"] = obj.redirect_url

        return metadata


class WorkspaceIntegrationSerializer(DynamicBaseSerializer):
    integration_detail = IntegrationSerializer(source="integration", read_only=True)

    class Meta:
        model = WorkspaceIntegration
        fields = "__all__"
        read_only_fields = [
            "workspace",
            "actor",
            "integration",
            "api_token",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class GithubRepositorySerializer(DynamicBaseSerializer):
    full_name = serializers.SerializerMethodField()
    html_url = serializers.CharField(source="url", read_only=True)

    class Meta:
        model = GithubRepository
        fields = [
            "id",
            "repository_id",
            "name",
            "owner",
            "url",
            "html_url",
            "full_name",
            "config",
            "project",
            "workspace",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]

    def get_full_name(self, obj):
        return f"{obj.owner}/{obj.name}"


class GithubRepositorySyncSerializer(DynamicBaseSerializer):
    repo_detail = GithubRepositorySerializer(source="repository", read_only=True)

    class Meta:
        model = GithubRepositorySync
        fields = [
            "id",
            "repository",
            "repo_detail",
            "credentials",
            "actor",
            "workspace_integration",
            "label",
            "project",
            "workspace",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "repository",
            "repo_detail",
            "credentials",
            "actor",
            "workspace_integration",
            "label",
            "project",
            "workspace",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
