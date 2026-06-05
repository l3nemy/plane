/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// editor
import type { TEmbedConfig } from "@plane/editor";
// plane types
import type { TSearchEntityRequestPayload, TSearchResponse } from "@plane/types";

export type TIssueEmbedHookProps = {
  fetchEmbedSuggestions?: (payload: TSearchEntityRequestPayload) => Promise<TSearchResponse>;
  projectId?: string;
  workspaceSlug?: string;
};

export const useIssueEmbed = (_props: TIssueEmbedHookProps) => {
  const issueEmbedProps: TEmbedConfig["issue"] = {
    widgetCallback: () => null,
  };

  return {
    issueEmbedProps,
  };
};
