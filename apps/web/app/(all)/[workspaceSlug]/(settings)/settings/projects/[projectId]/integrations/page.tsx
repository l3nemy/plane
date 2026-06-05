/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { IntegrationCard } from "@/components/project/integration-card";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
// constants
import { WORKSPACE_INTEGRATIONS } from "@/constants/fetch-keys";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
// lib
import { getIntegrationMetadata } from "@/lib/integrations/metadata";
// services
import { IntegrationService } from "@/services/integrations";
// local imports
import type { Route } from "./+types/page";
import { IntegrationsProjectSettingsHeader } from "./header";

const integrationService = new IntegrationService();

const ProjectIntegrationsSettingsPage = observer(function ProjectIntegrationsSettingsPage({
  params,
}: Route.ComponentProps) {
  // router
  const { workspaceSlug } = params;
  // store hooks
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentProjectDetails: projectDetails } = useProject();
  // translation
  const { t } = useTranslation();

  const canPerformProjectAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const pageTitle = projectDetails?.name ? `${projectDetails.name} - Integrations` : undefined;

  const { data: workspaceIntegrations } = useSWR(
    canPerformProjectAdminActions ? WORKSPACE_INTEGRATIONS(workspaceSlug) : null,
    () => (canPerformProjectAdminActions ? integrationService.getWorkspaceIntegrationsList(workspaceSlug) : null)
  );

  const projectIntegrations =
    workspaceIntegrations?.filter((integration) => {
      const metadata = getIntegrationMetadata(integration.integration_detail);
      if (!metadata.supportsProjectSync) return false;

      if (integration.integration_detail.provider !== "github") return true;

      const workspaceIntegrationMetadata = integration.metadata as Record<string, unknown> | undefined;
      const workspaceIntegrationConfig = integration.config as Record<string, unknown> | undefined;
      return Boolean(workspaceIntegrationMetadata?.installation_id || workspaceIntegrationConfig?.installation_id);
    }) ?? [];

  if (workspaceUserInfo && !canPerformProjectAdminActions) {
    return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<IntegrationsProjectSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <section className="w-full">
        <SettingsHeading
          title={t("project_settings.integrations.heading")}
          description={t("project_settings.integrations.description")}
        />
        <div className="mt-6">
          {workspaceIntegrations ? (
            projectIntegrations.length > 0 ? (
              projectIntegrations.map((integration) => (
                <IntegrationCard key={integration.id} integration={integration} />
              ))
            ) : (
              <div className="border-b border-subtle bg-surface-1 px-4 py-6 text-body-xs-regular text-secondary">
                {t("project_settings.integrations.empty_state")}
              </div>
            )
          ) : (
            <div className="border-b border-subtle bg-surface-1 px-4 py-6 text-body-xs-regular text-secondary">
              {t("common.loading")}
            </div>
          )}
        </div>
      </section>
    </SettingsContentWrapper>
  );
});

export default ProjectIntegrationsSettingsPage;
