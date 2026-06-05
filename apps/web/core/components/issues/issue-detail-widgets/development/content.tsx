/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import type { TIssueServiceType } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { GitHubDevelopmentLinks } from "./github-development";

type Props = {
  issueId: string;
  issueServiceType: TIssueServiceType;
};

const DevelopmentCollapsibleContent = observer(function DevelopmentCollapsibleContent(props: Props) {
  const { issueId, issueServiceType } = props;
  // store hooks
  const {
    link: { getDevelopmentLinksByIssueId },
  } = useIssueDetail(issueServiceType);
  // derived values
  const developmentLinks = getDevelopmentLinksByIssueId(issueId);

  return <GitHubDevelopmentLinks developmentLinks={developmentLinks} />;
});

export { DevelopmentCollapsibleContent };
