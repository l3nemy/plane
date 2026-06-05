/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useEffect } from "react";
import { observer } from "mobx-react";
// plane imports
import type { TIssueServiceType, TWorkItemWidgets } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// Plane-web
import { WorkItemAdditionalWidgetCollapsibles } from "@/plane-web/components/issues/issue-detail-widgets/collapsibles";
import { useTimeLineRelationOptions } from "@/plane-web/components/relations";
// local imports
import { AttachmentsCollapsible } from "./attachments";
import { DevelopmentCollapsible, isGitHubDevelopmentLink } from "./development";
import { LinksCollapsible } from "./links";
import { RelationsCollapsible } from "./relations";
import { SubIssuesCollapsible } from "./sub-issues";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
  issueServiceType: TIssueServiceType;
  hideWidgets?: TWorkItemWidgets[];
};

export const IssueDetailWidgetCollapsibles = observer(function IssueDetailWidgetCollapsibles(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled, issueServiceType, hideWidgets } = props;
  // store hooks
  const {
    issue: { getIssueById },
    subIssues: { subIssuesByIssueId },
    attachment: { getAttachmentsCountByIssueId, getAttachmentsUploadStatusByIssueId },
    fetchDevelopmentLinks,
    link: { getDevelopmentLinksByIssueId, getLinkById, getLinksByIssueId },
    relation: { getRelationCountByIssueId },
  } = useIssueDetail(issueServiceType);
  // derived values
  const issue = getIssueById(issueId);
  const subIssues = subIssuesByIssueId(issueId);
  const ISSUE_RELATION_OPTIONS = useTimeLineRelationOptions();
  const issueRelationsCount = getRelationCountByIssueId(issueId, ISSUE_RELATION_OPTIONS);
  const developmentLinks = getDevelopmentLinksByIssueId(issueId);
  const hasDevelopmentLinks =
    !!developmentLinks &&
    (developmentLinks.pull_requests.length > 0 ||
      developmentLinks.commits.length > 0 ||
      developmentLinks.pull_requests.some((pullRequest) => pullRequest.commits.length > 0));
  const issueLinkIds = getLinksByIssueId(issueId);
  const visibleIssueLinksCount =
    issueLinkIds?.map((linkId) => getLinkById(linkId)).filter((link) => link && !isGitHubDevelopmentLink(link))
      .length ?? 0;
  const shouldPollDevelopmentLinks = !hideWidgets?.includes("development");
  // render conditions
  const shouldRenderSubIssues = !!subIssues && subIssues.length > 0 && !hideWidgets?.includes("sub-work-items");
  const shouldRenderRelations = issueRelationsCount > 0 && !hideWidgets?.includes("relations");
  const shouldRenderDevelopment = hasDevelopmentLinks && !hideWidgets?.includes("development");
  const shouldRenderLinks =
    (issueLinkIds ? visibleIssueLinksCount > 0 : !!issue?.link_count && issue?.link_count > 0) &&
    !hideWidgets?.includes("links");
  const attachmentUploads = getAttachmentsUploadStatusByIssueId(issueId);
  const attachmentsCount = getAttachmentsCountByIssueId(issueId);
  const shouldRenderAttachments =
    attachmentsCount > 0 ||
    (!!attachmentUploads && attachmentUploads.length > 0 && !hideWidgets?.includes("attachments"));

  useEffect(() => {
    if (!shouldPollDevelopmentLinks) return undefined;

    fetchDevelopmentLinks(workspaceSlug, projectId, issueId).catch((error) => {
      console.error("Failed to fetch development links", error);
    });

    const intervalId = window.setInterval(() => {
      fetchDevelopmentLinks(workspaceSlug, projectId, issueId).catch((error) => {
        console.error("Failed to refresh development links", error);
      });
    }, 15000);

    return () => window.clearInterval(intervalId);
  }, [fetchDevelopmentLinks, issueId, projectId, shouldPollDevelopmentLinks, workspaceSlug]);

  return (
    <div className="flex flex-col">
      {shouldRenderSubIssues && (
        <SubIssuesCollapsible
          workspaceSlug={workspaceSlug}
          projectId={projectId}
          issueId={issueId}
          disabled={disabled}
          issueServiceType={issueServiceType}
        />
      )}
      {shouldRenderRelations && (
        <RelationsCollapsible
          workspaceSlug={workspaceSlug}
          issueId={issueId}
          disabled={disabled}
          issueServiceType={issueServiceType}
        />
      )}
      {shouldRenderDevelopment && <DevelopmentCollapsible issueId={issueId} issueServiceType={issueServiceType} />}
      {shouldRenderLinks && (
        <LinksCollapsible
          workspaceSlug={workspaceSlug}
          projectId={projectId}
          issueId={issueId}
          disabled={disabled}
          issueServiceType={issueServiceType}
        />
      )}
      {shouldRenderAttachments && (
        <AttachmentsCollapsible
          workspaceSlug={workspaceSlug}
          projectId={projectId}
          issueId={issueId}
          disabled={disabled}
          issueServiceType={issueServiceType}
        />
      )}
      <WorkItemAdditionalWidgetCollapsibles
        disabled={disabled}
        hideWidgets={hideWidgets ?? []}
        issueServiceType={issueServiceType}
        projectId={projectId}
        workItemId={issueId}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
});
