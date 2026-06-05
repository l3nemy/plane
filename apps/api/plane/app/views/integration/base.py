# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.integrations import run_integration_install_handler, sync_registered_integration_providers
from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IntegrationSerializer, WorkspaceIntegrationSerializer
from plane.db.models import Integration, Workspace, WorkspaceIntegration
from ..base import BaseAPIView


class IntegrationEndpoint(BaseAPIView):
    def get(self, request):
        sync_registered_integration_providers()

        integrations = Integration.objects.all()
        serializer = IntegrationSerializer(integrations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WorkspaceIntegrationEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug, pk=None):
        if pk is None:
            workspace_integrations = WorkspaceIntegration.objects.filter(workspace__slug=slug).select_related(
                "integration"
            )
            serializer = WorkspaceIntegrationSerializer(workspace_integrations, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        workspace_integration = WorkspaceIntegration.objects.select_related("integration").get(
            workspace__slug=slug,
            pk=pk,
        )
        serializer = WorkspaceIntegrationSerializer(workspace_integration)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def delete(self, request, slug, pk):
        workspace_integration = WorkspaceIntegration.objects.get(workspace__slug=slug, pk=pk)
        workspace_integration.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceIntegrationProviderEndpoint(BaseAPIView):
    @allow_permission(allowed_roles=[ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug, provider):
        sync_registered_integration_providers()

        workspace = Workspace.objects.get(slug=slug)
        integration = Integration.objects.get(provider=provider)
        response = run_integration_install_handler(
            provider,
            request=request,
            workspace=workspace,
            integration=integration,
        )

        if response is None:
            return Response(
                {"error": "No install handler is configured for this integration provider."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        if isinstance(response, Response):
            return response

        return Response(response, status=status.HTTP_201_CREATED)
