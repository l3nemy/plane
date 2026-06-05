/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import type { TIssueLink, TIssueServiceType } from "@plane/types";
// components
import { LinkList } from "../../issue-detail/links";
// development
import { isGitHubDevelopmentLink } from "../development";
// helper
import { useLinkOperations } from "./helper";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";

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
    link: { getLinkById, getLinksByIssueId },
  } = useIssueDetail(issueServiceType);

  // helper
  const handleLinkOperations = useLinkOperations(workspaceSlug, projectId, issueId, issueServiceType);
  // derived values
  const links = (getLinksByIssueId(issueId) ?? [])
    .map((linkId) => getLinkById(linkId))
    .filter((link): link is TIssueLink => !!link);
  const githubLinkIds = links.filter(isGitHubDevelopmentLink).map((link) => link.id);

  return (
    <LinkList
      issueId={issueId}
      linkOperations={handleLinkOperations}
      disabled={disabled}
      hiddenLinkIds={githubLinkIds}
      issueServiceType={issueServiceType}
    />
  );
});

export { IssueLinksCollapsibleContent };
