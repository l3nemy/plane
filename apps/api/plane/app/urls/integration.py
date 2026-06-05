# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views import (
    GitHubInstallationCallbackEndpoint,
    GitHubRepositoriesEndpoint,
    GitHubRepositorySyncEndpoint,
    GitHubWebhookEndpoint,
    IntegrationEndpoint,
    WorkspaceIntegrationEndpoint,
    WorkspaceIntegrationProviderEndpoint,
)


urlpatterns = [
    path("integrations/", IntegrationEndpoint.as_view(), name="integrations"),
    path(
        "integrations/github/callback/",
        GitHubInstallationCallbackEndpoint.as_view(),
        name="github-integration-callback",
    ),
    path(
        "integrations/github/callback",
        GitHubInstallationCallbackEndpoint.as_view(),
        name="github-integration-callback",
    ),
    path(
        "integrations/github/webhook/",
        GitHubWebhookEndpoint.as_view(),
        name="github-integration-webhook",
    ),
    path(
        "integrations/github/webhook",
        GitHubWebhookEndpoint.as_view(),
        name="github-integration-webhook",
    ),
    path(
        "workspaces/<str:slug>/workspace-integrations/",
        WorkspaceIntegrationEndpoint.as_view(),
        name="workspace-integrations",
    ),
    path(
        "workspaces/<str:slug>/workspace-integrations/<uuid:workspace_integration_id>/github-repositories/",
        GitHubRepositoriesEndpoint.as_view(),
        name="github-repositories",
    ),
    path(
        "workspaces/<str:slug>/workspace-integrations/<uuid:pk>/provider/",
        WorkspaceIntegrationEndpoint.as_view(),
        name="workspace-integrations",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/workspace-integrations/"
        "<uuid:workspace_integration_id>/github-repository-sync/",
        GitHubRepositorySyncEndpoint.as_view(),
        name="github-repository-sync",
    ),
    path(
        "workspaces/<str:slug>/workspace-integrations/<str:provider>/",
        WorkspaceIntegrationProviderEndpoint.as_view(),
        name="workspace-integration-provider",
    ),
]
