/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import GithubLogo from "@/app/assets/services/github.png?url";
import GithubSquareLogo from "@/app/assets/logos/github-square.png?url";
import SlackLogo from "@/app/assets/services/slack.png?url";

import type { IAppIntegration, IAppIntegrationMetadata } from "@plane/types";

type TIntegrationProviderMetadata = {
  authProvider?: string;
  installedDescription: string;
  installUrl?: string | null;
  logo?: string | null;
  notInstalledDescription: string;
  projectDescription: string;
  projectLogo?: string | null;
  supportsProjectSync: boolean;
};

const DEFAULT_INSTALLED_DESCRIPTION = "This integration is installed for this workspace.";
const DEFAULT_NOT_INSTALLED_DESCRIPTION =
  "Install this community integration to connect Plane with an external service.";
const DEFAULT_PROJECT_DESCRIPTION = "Project-level setup is managed by this integration.";

const providerMetadata: Record<string, TIntegrationProviderMetadata> = {
  github: {
    authProvider: "github",
    installedDescription: "Activate GitHub on individual projects to sync with specific repositories.",
    logo: GithubLogo,
    notInstalledDescription: "Connect with GitHub with your Plane workspace to sync project work items.",
    projectDescription: "Select GitHub repository to enable sync.",
    projectLogo: GithubSquareLogo,
    supportsProjectSync: true,
  },
  slack: {
    authProvider: "slack",
    installedDescription: "Activate Slack on individual projects to sync with specific channels.",
    logo: SlackLogo,
    notInstalledDescription: "Connect with Slack with your Plane workspace to sync project work items.",
    projectDescription: "Get regular updates and control which notification you want to receive.",
    projectLogo: SlackLogo,
    supportsProjectSync: true,
  },
};

const getIntegrationMetadata = (integration: IAppIntegration): TIntegrationProviderMetadata => {
  const backendMetadata = (integration.metadata ?? {}) as IAppIntegrationMetadata;
  const defaults = providerMetadata[integration.provider];

  return {
    authProvider: backendMetadata.auth_provider ?? defaults?.authProvider ?? integration.provider,
    installedDescription:
      backendMetadata.installed_description ?? defaults?.installedDescription ?? DEFAULT_INSTALLED_DESCRIPTION,
    installUrl: backendMetadata.install_url ?? integration.redirect_url ?? defaults?.installUrl ?? null,
    logo: integration.avatar_url ?? defaults?.logo ?? null,
    notInstalledDescription:
      backendMetadata.not_installed_description ??
      defaults?.notInstalledDescription ??
      DEFAULT_NOT_INSTALLED_DESCRIPTION,
    projectDescription:
      backendMetadata.project_description ?? defaults?.projectDescription ?? DEFAULT_PROJECT_DESCRIPTION,
    projectLogo:
      backendMetadata.project_logo_url ?? integration.avatar_url ?? defaults?.projectLogo ?? defaults?.logo ?? null,
    supportsProjectSync: backendMetadata.supports_project_sync ?? defaults?.supportsProjectSync ?? false,
  };
};

export { getIntegrationMetadata };
export type { TIntegrationProviderMetadata };
