/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useParams } from "next/navigation";
import useSWR, { mutate } from "swr";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IGithubRepository, IWorkspaceIntegration } from "@plane/types";
// components
import { SelectChannel } from "@/components/integration/slack/select-channel";
import { SelectRepository } from "@/components/integration/github/select-repository";
// constants
import { PROJECT_GITHUB_REPOSITORY } from "@/constants/fetch-keys";
// lib
import { getIntegrationMetadata } from "@/lib/integrations/metadata";
// services
import { ProjectService } from "@/services/project";

type Props = {
  integration: IWorkspaceIntegration;
};

// services
const projectService = new ProjectService();

export function IntegrationCard({ integration }: Props) {
  const { workspaceSlug, projectId } = useParams();
  const provider = integration.integration_detail.provider;
  const metadata = getIntegrationMetadata(integration.integration_detail);

  const { data: syncedGithubRepository } = useSWR(
    provider === "github" && projectId ? PROJECT_GITHUB_REPOSITORY(projectId) : null,
    () =>
      workspaceSlug && projectId && integration && provider === "github"
        ? projectService.getProjectGithubRepository(workspaceSlug, projectId, integration.id)
        : null
  );

  const handleChange = (repo?: IGithubRepository | null) => {
    if (!workspaceSlug || !projectId || !integration || !repo) return;

    const owner = typeof repo.owner === "string" ? repo.owner : repo.owner?.login;
    const repositoryName = repo.name ?? repo.full_name?.split("/").pop();
    const repositoryUrl = repo.html_url ?? repo.url;

    if (!repo.id || !repositoryName || !owner || !repositoryUrl) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Error!",
        message: "Repository details are incomplete. Please refresh and try again.",
      });
      return;
    }

    projectService
      .syncGithubRepository(workspaceSlug, projectId, integration.id, {
        name: repositoryName,
        owner,
        repository_id: repo.id,
        url: repositoryUrl,
      })
      .then(() => {
        mutate(PROJECT_GITHUB_REPOSITORY(projectId));

        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: "Success!",
          message: `${owner}/${repositoryName} repository synced with the project successfully.`,
        });
        return null;
      })
      .catch((err) => {
        console.error(err);
        setToast({
          type: TOAST_TYPE.ERROR,
          title: "Error!",
          message: "Repository could not be synced with the project. Please try again.",
        });
      });
  };

  return (
    <>
      {integration && (
        <div className="flex items-center justify-between gap-2 border-b border-subtle bg-surface-1 px-4 py-6">
          <div className="flex items-start gap-4">
            <div className="h-10 w-10 flex-shrink-0">
              {metadata.projectLogo ? (
                <img
                  src={metadata.projectLogo}
                  className="h-full w-full object-cover"
                  alt={`${integration.integration_detail.title} Logo`}
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center rounded bg-surface-2 text-body-xs-medium text-secondary uppercase">
                  {integration.integration_detail.title.slice(0, 1)}
                </div>
              )}
            </div>
            <div>
              <h3 className="flex items-center gap-4 text-13 font-medium">{integration.integration_detail.title}</h3>
              <p className="text-13 tracking-tight text-secondary">{metadata.projectDescription}</p>
            </div>
          </div>
          {provider === "github" && (
            <SelectRepository
              integration={integration}
              value={
                syncedGithubRepository && syncedGithubRepository.length > 0
                  ? `${syncedGithubRepository[0].repo_detail.owner}/${syncedGithubRepository[0].repo_detail.name}`
                  : null
              }
              label={
                syncedGithubRepository && syncedGithubRepository.length > 0
                  ? `${syncedGithubRepository[0].repo_detail.owner}/${syncedGithubRepository[0].repo_detail.name}`
                  : "Select Repository"
              }
              onChange={handleChange}
            />
          )}
          {provider === "slack" && <SelectChannel integration={integration} />}
        </div>
      )}
    </>
  );
}
