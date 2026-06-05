/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import type { TIssueServiceType } from "@plane/types";
import { Collapsible } from "@plane/ui";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { DevelopmentCollapsibleContent } from "./content";
import { DevelopmentCollapsibleTitle } from "./title";

type Props = {
  issueId: string;
  issueServiceType: TIssueServiceType;
};

const DevelopmentCollapsible = observer(function DevelopmentCollapsible(props: Props) {
  const { issueId, issueServiceType } = props;
  // store hooks
  const { openWidgets, toggleOpenWidget } = useIssueDetail(issueServiceType);
  // derived values
  const isCollapsibleOpen = openWidgets.includes("development");

  return (
    <Collapsible
      isOpen={isCollapsibleOpen}
      onToggle={() => toggleOpenWidget("development")}
      title={
        <DevelopmentCollapsibleTitle isOpen={isCollapsibleOpen} issueId={issueId} issueServiceType={issueServiceType} />
      }
      buttonClassName="w-full"
    >
      <DevelopmentCollapsibleContent issueId={issueId} issueServiceType={issueServiceType} />
    </Collapsible>
  );
});

export { DevelopmentCollapsible };
