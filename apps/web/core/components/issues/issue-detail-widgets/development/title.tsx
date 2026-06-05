/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useMemo } from "react";
import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import type { TIssueServiceType } from "@plane/types";
import { CollapsibleButton } from "@plane/ui";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";

type Props = {
  isOpen: boolean;
  issueId: string;
  issueServiceType: TIssueServiceType;
};

const DevelopmentCollapsibleTitle = observer(function DevelopmentCollapsibleTitle(props: Props) {
  const { isOpen, issueId, issueServiceType } = props;
  const { t } = useTranslation();
  // store hooks
  const {
    link: { getDevelopmentLinksByIssueId },
  } = useIssueDetail(issueServiceType);
  // derived values
  const developmentLinks = getDevelopmentLinksByIssueId(issueId);
  const pullRequestCount = developmentLinks?.pull_requests.length ?? 0;
  const commitCount =
    developmentLinks?.pull_requests.reduce((count, pullRequest) => count + pullRequest.commits.length, 0) ?? 0;
  const orphanCommitCount = developmentLinks?.commits.length ?? 0;

  // indicator element
  const indicatorElement = useMemo(
    () => (
      <span className="flex items-center justify-center">
        <p className="text-14 !leading-3 text-tertiary">
          {pullRequestCount}/{commitCount + orphanCommitCount}
        </p>
      </span>
    ),
    [commitCount, orphanCommitCount, pullRequestCount]
  );

  return <CollapsibleButton isOpen={isOpen} title={t("issue.development.title")} indicatorElement={indicatorElement} />;
});

export { DevelopmentCollapsibleTitle };
