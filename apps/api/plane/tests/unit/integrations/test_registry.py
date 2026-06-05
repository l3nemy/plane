# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.app.integrations.registry import (
    CommunityIntegrationProvider,
    IntegrationProviderRegistry,
    community_integration_registry,
    register_integration_provider,
    run_integration_install_handler,
)
from plane.db.models import Integration


def install_handler(*, request, workspace, integration):
    return {
        "provider": integration.provider,
        "workspace": workspace,
    }


@pytest.mark.unit
class TestIntegrationProviderRegistry:
    def setup_method(self):
        self.previous_providers = dict(community_integration_registry._providers)
        self.previous_loaded_state = community_integration_registry._loaded_configured_providers
        community_integration_registry._providers = {}
        community_integration_registry._loaded_configured_providers = True

    def teardown_method(self):
        community_integration_registry._providers = self.previous_providers
        community_integration_registry._loaded_configured_providers = self.previous_loaded_state

    def test_register_provider(self):
        provider = CommunityIntegrationProvider(provider="linear", title="Linear")

        register_integration_provider(provider)

        assert community_integration_registry.get("linear") == provider

    def test_registry_includes_default_ce_providers(self):
        registry = IntegrationProviderRegistry()

        provider_keys = {provider.provider for provider in registry.all()}

        assert "github" in provider_keys
        assert "slack" in provider_keys

    def test_sync_provider_to_database_without_churn(self, db):
        registry = IntegrationProviderRegistry()
        registry._loaded_configured_providers = True
        registry.register(
            CommunityIntegrationProvider(
                provider="linear",
                title="Linear",
                metadata={"install_url": "https://linear.app/oauth"},
            )
        )

        registry.sync_to_database()
        integration = Integration.objects.get(provider="linear")
        updated_at = integration.updated_at

        registry.sync_to_database()
        integration.refresh_from_db()

        assert integration.title == "Linear"
        assert integration.metadata["community"] is True
        assert integration.metadata["install_url"] == "https://linear.app/oauth"
        assert integration.updated_at == updated_at

    def test_run_install_handler(self, db):
        provider = CommunityIntegrationProvider(
            provider="linear",
            title="Linear",
            install_handler="plane.tests.unit.integrations.test_registry.install_handler",
        )
        register_integration_provider(provider)
        integration = Integration.objects.create(provider="linear", title="Linear")

        response = run_integration_install_handler(
            "linear",
            request=None,
            workspace="test-workspace",
            integration=integration,
        )

        assert response == {
            "provider": "linear",
            "workspace": "test-workspace",
        }
