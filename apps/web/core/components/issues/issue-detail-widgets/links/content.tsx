/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useEffect } from "react";
import { observer } from "mobx-react";
import type { TIssueLink, TIssueServiceType } from "@plane/types";
// components
import { LinkList } from "../../issue-detail/links";
// helper
import { useLinkOperations } from "./helper";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { GitHubDevelopmentLinks, isGitHubDevelopmentLink } from "./github-development";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
  issueServiceType: TIssueServiceType;
};

const IssueLinksCollapsibleContent = observer(function IssueLinksCollapsibleContent(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled, issueServiceType } = props;
  // store hooks
  const {
    fetchDevelopmentLinks,
    link: { getDevelopmentLinksByIssueId, getLinkById, getLinksByIssueId },
  } = useIssueDetail(issueServiceType);

  // helper
  const handleLinkOperations = useLinkOperations(workspaceSlug, projectId, issueId, issueServiceType);
  // derived values
  const links = (getLinksByIssueId(issueId) ?? [])
    .map((linkId) => getLinkById(linkId))
    .filter((link): link is TIssueLink => !!link);
  const githubLinkIds = links.filter(isGitHubDevelopmentLink).map((link) => link.id);
  const developmentLinks = getDevelopmentLinksByIssueId(issueId);

  useEffect(() => {
    fetchDevelopmentLinks(workspaceSlug, projectId, issueId).catch((error) => {
      console.error("Failed to fetch development links", error);
    });
  }, [fetchDevelopmentLinks, issueId, projectId, workspaceSlug]);

  return (
    <>
      <GitHubDevelopmentLinks developmentLinks={developmentLinks} />
      <LinkList
        issueId={issueId}
        linkOperations={handleLinkOperations}
        disabled={disabled}
        hiddenLinkIds={githubLinkIds}
        issueServiceType={issueServiceType}
      />
    </>
  );
});

export { IssueLinksCollapsibleContent };
