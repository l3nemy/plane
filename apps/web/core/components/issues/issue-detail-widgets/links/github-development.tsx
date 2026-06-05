/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ExternalLink, GitCommit, GitPullRequest } from "lucide-react";
// plane imports
import type { TIssueLink } from "@plane/types";
// ui
import { Tooltip } from "@plane/propel/tooltip";
// hooks
import { usePlatformOS } from "@/hooks/use-platform-os";

type TGitHubLinkType = "commit" | "pull_request";

type TGitHubLinkMetadata = {
  author_login?: string;
  committed_at?: string;
  draft?: boolean;
  merged?: boolean;
  message?: string;
  number?: number | string;
  repository?: string;
  sha?: string;
  short_sha?: string;
  source?: string;
  state?: string;
  type?: TGitHubLinkType;
};

type TGitHubDevelopmentModel = {
  commits: TIssueLink[];
  pullRequests: TIssueLink[];
};

type TGitHubDevelopmentLinks = {
  links: TIssueLink[];
};

const getGitHubMetadata = (link: TIssueLink): TGitHubLinkMetadata => link.metadata ?? {};

const isGitHubDevelopmentLink = (link: TIssueLink): boolean => {
  const metadata = getGitHubMetadata(link);
  return metadata.source === "github" && (metadata.type === "pull_request" || metadata.type === "commit");
};

const buildGitHubDevelopmentModel = (links: TIssueLink[]): TGitHubDevelopmentModel => {
  const githubLinks = links.filter(isGitHubDevelopmentLink);

  return {
    commits: githubLinks.filter((link) => getGitHubMetadata(link).type === "commit"),
    pullRequests: githubLinks.filter((link) => getGitHubMetadata(link).type === "pull_request"),
  };
};

const getPullRequestStatus = (metadata: TGitHubLinkMetadata): string => {
  if (metadata.merged) return "Merged";
  if (metadata.draft) return "Draft";
  if (metadata.state === "closed") return "Closed";
  if (metadata.state === "open") return "Open";
  return "PR";
};

const getCommitTitleParts = (link: TIssueLink) => {
  const metadata = getGitHubMetadata(link);
  const shortSha = metadata.short_sha || metadata.sha?.slice(0, 7) || link.title.split(":")[0];
  const message =
    metadata.message
      ?.split("\n")
      .find((line) => line.trim())
      ?.trim() || link.title;

  return {
    message,
    shortSha,
  };
};

const GitHubDevelopmentLinks = (props: TGitHubDevelopmentLinks) => {
  const { links } = props;
  const { isMobile } = usePlatformOS();
  const model = buildGitHubDevelopmentModel(links);

  if (model.pullRequests.length === 0 && model.commits.length === 0) return null;

  return (
    <div className="flex flex-col gap-3 pt-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitPullRequest className="size-3.5 text-tertiary" />
          <span className="text-body-xs-medium text-secondary">Development</span>
        </div>
        <span className="text-caption-sm-regular text-tertiary">
          {model.pullRequests.length} PR{model.pullRequests.length === 1 ? "" : "s"} / {model.commits.length} commit
          {model.commits.length === 1 ? "" : "s"}
        </span>
      </div>

      {model.pullRequests.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-caption-sm-medium text-tertiary uppercase">Pull requests</span>
          {model.pullRequests.map((link) => {
            const metadata = getGitHubMetadata(link);

            return (
              <a
                key={link.id}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-h-9 items-center justify-between gap-3 rounded-sm border border-subtle bg-surface-2 px-3 py-2 hover:bg-layer-1"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <GitPullRequest className="size-3.5 flex-shrink-0 text-tertiary" />
                  <div className="min-w-0">
                    <Tooltip tooltipContent={link.title || link.url} isMobile={isMobile}>
                      <p className="truncate text-body-xs-regular text-primary">{link.title || link.url}</p>
                    </Tooltip>
                    {metadata.repository && (
                      <p className="truncate text-caption-sm-regular text-tertiary">{metadata.repository}</p>
                    )}
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-2">
                  <span className="rounded-sm bg-surface-1 px-1.5 py-0.5 text-caption-sm-medium text-secondary">
                    {getPullRequestStatus(metadata)}
                  </span>
                  <ExternalLink className="size-3 text-tertiary" />
                </div>
              </a>
            );
          })}
        </div>
      )}

      {model.commits.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-caption-sm-medium text-tertiary uppercase">Commits</span>
          {model.commits.map((link) => {
            const metadata = getGitHubMetadata(link);
            const { message, shortSha } = getCommitTitleParts(link);

            return (
              <a
                key={link.id}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-h-8 items-center justify-between gap-3 rounded-sm px-2 py-1.5 hover:bg-layer-1"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <GitCommit className="size-3.5 flex-shrink-0 text-tertiary" />
                  <code className="flex-shrink-0 text-caption-sm-medium text-secondary">{shortSha}</code>
                  <Tooltip tooltipContent={message} isMobile={isMobile}>
                    <span className="truncate text-body-xs-regular text-primary">{message}</span>
                  </Tooltip>
                </div>
                {metadata.author_login && (
                  <span className="flex-shrink-0 text-caption-sm-regular text-tertiary">{metadata.author_login}</span>
                )}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
};

export { GitHubDevelopmentLinks, buildGitHubDevelopmentModel, isGitHubDevelopmentLink };
export type { TGitHubDevelopmentModel, TGitHubLinkMetadata };
