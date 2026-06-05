# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from dataclasses import dataclass, field
from importlib import import_module
import logging
from typing import Any, Callable

# Django imports
from django.conf import settings

logger = logging.getLogger("plane.integrations")


def _default_community_integration_providers() -> list["CommunityIntegrationProvider"]:
    return [
        CommunityIntegrationProvider(
            provider="github",
            title="GitHub",
            author="Plane",
            description={
                "short": "Sync Plane work items with GitHub issues.",
            },
            metadata={
                "installed_description": "Activate GitHub on individual projects to sync with specific repositories.",
                "not_installed_description": "Connect GitHub with your Plane workspace to sync project work items.",
                "project_description": "Select GitHub repository to enable sync.",
                "supports_project_sync": True,
            },
            verified=True,
            install_handler="plane.app.views.integration.github.install_github_workspace_integration",
        ),
        CommunityIntegrationProvider(
            provider="slack",
            title="Slack",
            author="Plane",
            description={
                "short": "Send Plane project updates to Slack channels.",
            },
            metadata={
                "installed_description": "Activate Slack on individual projects to sync with specific channels.",
                "not_installed_description": "Connect Slack with your Plane workspace to sync project work items.",
                "project_description": "Get regular updates and control which notification you want to receive.",
                "supports_project_sync": True,
            },
            verified=True,
        ),
    ]


@dataclass(frozen=True)
class CommunityIntegrationProvider:
    provider: str
    title: str
    description: dict[str, Any] = field(default_factory=dict)
    author: str = "Plane community"
    network: int = 2
    webhook_url: str = ""
    webhook_secret: str = ""
    redirect_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    avatar_url: str | None = None
    install_handler: str | None = None

    def as_model_defaults(self) -> dict[str, Any]:
        metadata = {
            **self.metadata,
            "community": True,
        }
        if self.install_handler:
            metadata["install_handler"] = self.install_handler

        return {
            "title": self.title,
            "network": self.network,
            "description": self.description,
            "author": self.author,
            "webhook_url": self.webhook_url,
            "webhook_secret": self.webhook_secret,
            "redirect_url": self.redirect_url,
            "metadata": metadata,
            "verified": self.verified,
            "avatar_url": self.avatar_url,
        }


class IntegrationProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, CommunityIntegrationProvider] = {}
        self._loaded_configured_providers = False
        for provider in _default_community_integration_providers():
            self.register(provider)

    def register(self, provider: CommunityIntegrationProvider) -> None:
        if not provider.provider:
            raise ValueError("Integration provider key is required.")

        self._providers[provider.provider] = provider

    def get(self, provider_key: str) -> CommunityIntegrationProvider | None:
        self.load_configured_providers()
        return self._providers.get(provider_key)

    def all(self) -> list[CommunityIntegrationProvider]:
        self.load_configured_providers()
        return list(self._providers.values())

    def load_configured_providers(self) -> None:
        if self._loaded_configured_providers:
            return

        for provider_path in getattr(settings, "COMMUNITY_INTEGRATION_PROVIDERS", []):
            try:
                provider = _load_provider(provider_path)
                if isinstance(provider, list):
                    for item in provider:
                        self.register(item)
                else:
                    self.register(provider)
            except Exception as exc:
                logger.exception("Failed to load community integration provider %s: %s", provider_path, exc)

        self._loaded_configured_providers = True

    def sync_to_database(self) -> None:
        from plane.db.models import Integration

        for provider in self.all():
            defaults = provider.as_model_defaults()
            integration, created = Integration.objects.get_or_create(provider=provider.provider, defaults=defaults)

            if created:
                continue

            changed_fields = []
            for field_name, value in defaults.items():
                if getattr(integration, field_name) == value:
                    continue

                setattr(integration, field_name, value)
                changed_fields.append(field_name)

            if changed_fields:
                integration.save(update_fields=changed_fields)


def _load_provider(provider_path: str) -> CommunityIntegrationProvider | list[CommunityIntegrationProvider]:
    module_path, attribute_name = provider_path.rsplit(".", 1)
    module = import_module(module_path)
    provider = getattr(module, attribute_name)

    if callable(provider):
        provider = provider()

    return provider


def _load_handler(handler_path: str) -> Callable[..., Any]:
    module_path, attribute_name = handler_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, attribute_name)


community_integration_registry = IntegrationProviderRegistry()


def register_integration_provider(provider: CommunityIntegrationProvider) -> None:
    community_integration_registry.register(provider)


def get_integration_provider(provider_key: str) -> CommunityIntegrationProvider | None:
    return community_integration_registry.get(provider_key)


def sync_registered_integration_providers() -> None:
    community_integration_registry.sync_to_database()


def run_integration_install_handler(provider_key: str, *, request: Any, workspace: Any, integration: Any) -> Any:
    provider = get_integration_provider(provider_key)
    handler_path = provider.install_handler if provider else None
    handler_path = handler_path or (integration.metadata or {}).get("install_handler")

    if not handler_path:
        return None

    handler = _load_handler(handler_path)
    return handler(request=request, workspace=workspace, integration=integration)
