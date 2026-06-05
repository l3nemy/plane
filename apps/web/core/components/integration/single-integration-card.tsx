/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import useSWR, { mutate } from "swr";
import { CheckCircle } from "lucide-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import type { IAppIntegration, IWorkspaceIntegration } from "@plane/types";
// ui
import { Loader } from "@plane/ui";
// constants
import { WORKSPACE_INTEGRATIONS } from "@/constants/fetch-keys";
// hooks
import { useInstance } from "@/hooks/store/use-instance";
import { useUserPermissions } from "@/hooks/store/user";
import useIntegrationPopup from "@/hooks/use-integration-popup";
import { usePlatformOS } from "@/hooks/use-platform-os";
// lib
import { getIntegrationMetadata } from "@/lib/integrations/metadata";
// services
import { IntegrationService } from "@/services/integrations";

type Props = {
  integration: IAppIntegration;
};

// services
const integrationService = new IntegrationService();

export const SingleIntegrationCard = observer(function SingleIntegrationCard({ integration }: Props) {
  // states
  const [deletingIntegration, setDeletingIntegration] = useState(false);
  // router
  const { workspaceSlug } = useParams();
  // store hooks
  const { config } = useInstance();
  const { allowPermissions } = useUserPermissions();
  const metadata = getIntegrationMetadata(integration);
  const isKnownPopupProvider = metadata.authProvider === "github" || metadata.authProvider === "slack";
  const canInstall = Boolean(metadata.installUrl || isKnownPopupProvider);

  const isUserAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const { isMobile } = usePlatformOS();
  const { startAuth, isConnecting: isInstalling } = useIntegrationPopup({
    provider: metadata.authProvider,
    github_app_name: config?.github_app_name || "",
    slack_client_id: config?.slack_client_id || "",
    authUrl: metadata.installUrl,
    onBeforeOpen: async () => {
      if (!workspaceSlug || integration.provider !== "github") return;

      await integrationService.installWorkspaceIntegration(workspaceSlug.toString(), "github");
    },
    onComplete: () => {
      if (!workspaceSlug) return;

      void mutate(WORKSPACE_INTEGRATIONS(workspaceSlug.toString()));
    },
  });

  const { data: workspaceIntegrations } = useSWR(workspaceSlug ? WORKSPACE_INTEGRATIONS(workspaceSlug) : null, () =>
    workspaceSlug ? integrationService.getWorkspaceIntegrationsList(workspaceSlug) : null
  );

  const handleRemoveIntegration = async () => {
    if (!workspaceSlug || !integration || !workspaceIntegrations) return;

    const workspaceIntegrationId = workspaceIntegrations?.find((i) => i.integration === integration.id)?.id;

    setDeletingIntegration(true);

    await integrationService
      .deleteWorkspaceIntegration(workspaceSlug, workspaceIntegrationId ?? "")
      .then(() => {
        mutate<IWorkspaceIntegration[]>(
          WORKSPACE_INTEGRATIONS(workspaceSlug),
          (prevData) => prevData?.filter((i) => i.id !== workspaceIntegrationId),
          false
        );
        setDeletingIntegration(false);

        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: "Deleted successfully!",
          message: `${integration.title} integration deleted successfully.`,
        });
        return null;
      })
      .catch(() => {
        setDeletingIntegration(false);

        setToast({
          type: TOAST_TYPE.ERROR,
          title: "Error!",
          message: `${integration.title} integration could not be deleted. Please try again.`,
        });
      });
  };

  const isInstalled = workspaceIntegrations?.find((i: IWorkspaceIntegration) => {
    if (i.integration_detail.id !== integration.id) return false;

    if (integration.provider !== "github") return true;

    const integrationMetadata = i.metadata as Record<string, unknown> | undefined;
    const integrationConfig = i.config as Record<string, unknown> | undefined;

    return Boolean(integrationMetadata?.installation_id || integrationConfig?.installation_id);
  });

  return (
    <div className="flex items-center justify-between gap-2 border-b border-subtle bg-surface-1 px-4 py-6">
      <div className="flex items-start gap-4">
        <div className="h-10 w-10 flex-shrink-0">
          {metadata.logo ? (
            <img src={metadata.logo} className="h-full w-full object-cover" alt={`${integration.title} Logo`} />
          ) : (
            <div className="flex h-full w-full items-center justify-center rounded bg-surface-2 text-body-xs-medium text-secondary uppercase">
              {integration.title.slice(0, 1)}
            </div>
          )}
        </div>
        <div>
          <h3 className="flex items-center gap-2 text-body-xs-medium">
            {integration.title}
            {workspaceIntegrations
              ? isInstalled && <CheckCircle className="h-3.5 w-3.5 fill-transparent text-success-primary" />
              : null}
          </h3>
          <p className="text-body-xs-regular text-secondary">
            {workspaceIntegrations
              ? isInstalled
                ? metadata.installedDescription
                : metadata.notInstalledDescription
              : "Loading..."}
          </p>
        </div>
      </div>

      {workspaceIntegrations ? (
        isInstalled ? (
          <Tooltip
            isMobile={isMobile}
            disabled={isUserAdmin}
            tooltipContent={!isUserAdmin ? "You don't have permission to perform this" : null}
          >
            <Button
              className={`${!isUserAdmin ? "hover:cursor-not-allowed" : ""}`}
              variant="error-fill"
              onClick={() => {
                if (!isUserAdmin) return;
                handleRemoveIntegration();
              }}
              disabled={!isUserAdmin}
              loading={deletingIntegration}
            >
              {deletingIntegration ? "Uninstalling..." : "Uninstall"}
            </Button>
          </Tooltip>
        ) : (
          <Tooltip
            isMobile={isMobile}
            disabled={isUserAdmin && canInstall}
            tooltipContent={
              !isUserAdmin
                ? "You don't have permission to perform this"
                : !canInstall
                  ? "This integration does not provide an install URL yet."
                  : null
            }
          >
            <Button
              className={`${!isUserAdmin || !canInstall ? "hover:cursor-not-allowed" : ""}`}
              variant="primary"
              onClick={() => {
                if (!isUserAdmin || !canInstall) return;
                startAuth();
              }}
              disabled={!isUserAdmin || !canInstall}
              loading={isInstalling && canInstall}
            >
              {canInstall ? (isInstalling ? "Installing..." : "Install") : "Manual setup"}
            </Button>
          </Tooltip>
        )
      ) : (
        <Loader>
          <Loader.Item height="32px" width="64px" />
        </Loader>
      )}
    </div>
  );
});
