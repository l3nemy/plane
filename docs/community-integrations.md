# Community integrations

Plane Community Edition includes a small integration framework so contributors can ship provider definitions without hardcoding every service into the web app. The framework is intentionally split into three layers:

- Provider metadata in the `Integration` model, exposed through `GET /api/integrations/`.
- Workspace installation records in `WorkspaceIntegration`, exposed through `GET /api/workspaces/<slug>/workspace-integrations/`.
- Provider-specific install and sync code, registered only when an integration needs OAuth, API keys, webhooks, or project-level sync.

## Backend provider contract

Create a Python module that returns a `CommunityIntegrationProvider`:

```python
from plane.app.integrations import CommunityIntegrationProvider


def linear_provider():
    return CommunityIntegrationProvider(
        provider="linear",
        title="Linear",
        author="Plane community",
        description={
            "short": "Sync Plane work items with Linear issues.",
        },
        redirect_url="https://linear.app/oauth/authorize?state={workspaceSlug}",
        metadata={
            "install_url": "https://linear.app/oauth/authorize?state={workspaceSlug}",
            "installed_description": "Activate Linear on individual projects to sync issues.",
            "not_installed_description": "Connect Linear with your Plane workspace.",
            "project_description": "Configure Linear project sync for this Plane project.",
            "supports_project_sync": False,
        },
        install_handler="plane.integrations.linear.install.install_linear_workspace",
    )
```

Register providers with the `COMMUNITY_INTEGRATION_PROVIDERS` environment variable:

```bash
COMMUNITY_INTEGRATION_PROVIDERS=plane.integrations.linear.provider.linear_provider
```

On `GET /api/integrations/`, Plane loads the built-in CE providers, loads any configured community providers, and syncs them into the `integrations` table with `metadata.community = true`.

## Install handlers

If `install_handler` is set, `POST /api/workspaces/<slug>/workspace-integrations/<provider>/` dispatches to it. The handler can return a DRF `Response` or plain JSON-like data:

```python
from rest_framework import status
from rest_framework.response import Response


def install_linear_workspace(*, request, workspace, integration):
    # Exchange OAuth code or validate an API key here.
    # Create the integration bot user, APIToken, and WorkspaceIntegration.
    return Response({"installed": True}, status=status.HTTP_201_CREATED)
```

If an integration does not register a handler, Plane returns `501` for that endpoint. This keeps manifest-only integrations visible without pretending they are installable.

## Frontend metadata fields

The web app reads these optional `Integration.metadata` fields:

- `install_url`: custom popup URL. Supports `{workspaceSlug}`, `{projectId}`, and `{stateParams}` placeholders.
- `auth_provider`: existing popup provider key, currently `github` or `slack`.
- `installed_description`: workspace settings copy after install.
- `not_installed_description`: workspace settings copy before install.
- `project_description`: project settings copy.
- `project_logo_url`: logo for project settings.
- `supports_project_sync`: whether project settings should expect provider-specific sync UI.

If a community provider is missing logo/copy metadata, Plane renders a safe fallback instead of failing.

## Building a GitHub-style sync

Use the existing GitHub implementation as a reference, but keep new providers isolated:

1. Add provider-specific models under `apps/api/plane/db/models/integration/` only when the provider needs durable sync state.
2. Add serializers/views/URLs for provider-specific install callbacks and project sync actions.
3. Create or reuse a project settings component under `apps/web/core/components/integration/<provider>/`.
4. Extend `apps/web/core/lib/integrations/metadata.ts` only for first-party UI defaults. Community providers should prefer backend metadata.
5. Add tests for install, uninstall, and project sync behavior.

The generic framework handles discovery and safe rendering. Provider code owns credentials, external API calls, webhook validation, and entity mapping.

## Configuring the built-in GitHub App integration

The GitHub integration is backed by a GitHub App, not by the GitHub OAuth login provider. Configure these variables in `apps/api/.env` for local Docker development:

```bash
GITHUB_APP_NAME=your-github-app-slug
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
# Or mount the key file and use:
GITHUB_APP_PRIVATE_KEY_FILE=/path/to/github-app.private-key.pem
GITHUB_WEBHOOK_SECRET=your-webhook-secret
```

Create the GitHub App with:

- Setup URL: `<API_BASE_URL>/api/integrations/github/callback/`
- Webhook URL: `<API_BASE_URL>/api/integrations/github/webhook/`
- Repository permissions needed for repository selection and future issue sync: Metadata read-only, Issues read/write, Pull requests read-only.
- Subscribe to installation events. Subscribe to issue and issue comment events when implementing two-way issue sync.

After changing env values, restart the API and worker containers. The workspace settings install button opens GitHub's app installation page using `GITHUB_APP_NAME`; GitHub redirects back to the setup URL with `installation_id` and `state=<workspaceSlug>`. Plane verifies the current Plane session is a workspace admin, stores the installation on `WorkspaceIntegration`, and uses installation tokens to list repositories.
