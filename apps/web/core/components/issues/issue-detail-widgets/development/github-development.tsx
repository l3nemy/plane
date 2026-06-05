/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ExternalLink, GitCommit, GitPullRequest } from "lucide-react";
import { useTranslation } from "@plane/i18n";
// plane imports
import type {
  TGitHubDevelopmentActor,
  TIssueGitHubCommitDevelopmentLink,
  TIssueGitHubDevelopmentLinks,
  TIssueGitHubPullRequestDevelopmentLink,
  TIssueLink,
} from "@plane/types";
// ui
import { Tooltip } from "@plane/propel/tooltip";
// hooks
import { usePlatformOS } from "@/hooks/use-platform-os";

type TGitHubLinkType = "commit" | "pull_request";

type TGitHubLinkMetadata = {
  source?: string;
  type?: TGitHubLinkType;
};

type TGitHubDevelopmentLinks = {
  developmentLinks: TIssueGitHubDevelopmentLinks | undefined;
};

const getGitHubMetadata = (link: TIssueLink): TGitHubLinkMetadata => link.metadata ?? {};

const isGitHubDevelopmentLink = (link: TIssueLink): boolean => {
  const metadata = getGitHubMetadata(link);
  return metadata.source === "github" && (metadata.type === "pull_request" || metadata.type === "commit");
};

const getPullRequestStatusKey = (pullRequest: TIssueGitHubPullRequestDevelopmentLink): string => {
  if (pullRequest.merged) return "issue.development.status.merged";
  if (pullRequest.draft) return "issue.development.status.draft";
  if (pullRequest.state === "closed") return "issue.development.status.closed";
  if (pullRequest.state === "open") return "issue.development.status.open";
  return "issue.development.status.pr";
};

const getCommitMessage = (commit: TIssueGitHubCommitDevelopmentLink) =>
  commit.message
    ?.split("\n")
    .find((line) => line.trim())
    ?.trim() || commit.title;

const getCommitShortSha = (commit: TIssueGitHubCommitDevelopmentLink) =>
  commit.short_sha || commit.sha?.slice(0, 7) || commit.title.split(":")[0];

const getShortDate = (value: string | undefined) => {
  if (!value) return undefined;
  return value.split("T")[0];
};

const getActorLogin = (actor: TGitHubDevelopmentActor | undefined) => actor?.login;

const getAssigneeSummary = (assignees: TGitHubDevelopmentActor[]) => {
  const assigneeLogins = assignees.map((assignee) => assignee.login).filter((login): login is string => !!login);

  if (assigneeLogins.length === 0) return undefined;
  if (assigneeLogins.length <= 2) return assigneeLogins.map((login) => `@${login}`).join(", ");

  return `${assigneeLogins
    .slice(0, 2)
    .map((login) => `@${login}`)
    .join(", ")} +${assigneeLogins.length - 2}`;
};

const CommitRow = (props: { commit: TIssueGitHubCommitDevelopmentLink; isMobile: boolean }) => {
  const { commit, isMobile } = props;
  const committedDate = getShortDate(commit.committed_at);
  const message = getCommitMessage(commit);
  const shortSha = getCommitShortSha(commit);

  return (
    <a
      href={commit.url}
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
      <div className="flex flex-shrink-0 items-center gap-2 text-caption-sm-regular text-tertiary">
        {commit.author_login && <span>@{commit.author_login}</span>}
        {committedDate && <span>{committedDate}</span>}
      </div>
    </a>
  );
};

const PullRequestRow = (props: { isMobile: boolean; pullRequest: TIssueGitHubPullRequestDevelopmentLink }) => {
  const { isMobile, pullRequest } = props;
  const { t } = useTranslation();
  const actorLogin = getActorLogin(pullRequest.actor);
  const assigneeSummary = getAssigneeSummary(pullRequest.assignees);

  return (
    <div className="rounded-sm border border-subtle bg-surface-2">
      <a
        href={pullRequest.url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex min-h-9 items-center justify-between gap-3 px-3 py-2 hover:bg-layer-1"
      >
        <div className="flex min-w-0 items-center gap-2">
          <GitPullRequest className="size-3.5 flex-shrink-0 text-tertiary" />
          <div className="min-w-0">
            <Tooltip tooltipContent={pullRequest.title || pullRequest.url} isMobile={isMobile}>
              <p className="truncate text-body-xs-regular text-primary">{pullRequest.title || pullRequest.url}</p>
            </Tooltip>
            <p className="truncate text-caption-sm-regular text-tertiary">
              {pullRequest.repository}
              {pullRequest.number ? ` #${pullRequest.number}` : ""}
              {actorLogin ? ` ${t("issue.development.by")} @${actorLogin}` : ""}
              {assigneeSummary ? ` ${t("issue.development.assigned")} ${assigneeSummary}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <span className="rounded-sm bg-surface-1 px-1.5 py-0.5 text-caption-sm-medium text-secondary">
            {t(getPullRequestStatusKey(pullRequest))}
          </span>
          <span className="text-caption-sm-regular text-tertiary">
            {t("issue.development.count.commit", { count: pullRequest.commits.length })}
          </span>
          <ExternalLink className="size-3 text-tertiary" />
        </div>
      </a>

      {pullRequest.commits.length > 0 && (
        <div className="border-t border-subtle px-1.5 py-1">
          {pullRequest.commits.map((commit) => (
            <CommitRow key={commit.id} commit={commit} isMobile={isMobile} />
          ))}
        </div>
      )}
    </div>
  );
};

const GitHubDevelopmentLinks = (props: TGitHubDevelopmentLinks) => {
  const { developmentLinks } = props;
  const { t } = useTranslation();
  const { isMobile } = usePlatformOS();
  const pullRequests = developmentLinks?.pull_requests ?? [];
  const commits = developmentLinks?.commits ?? [];
  const commitCount = pullRequests.reduce((count, pullRequest) => count + pullRequest.commits.length, commits.length);

  if (pullRequests.length === 0 && commits.length === 0) return null;

  return (
    <div className="flex flex-col gap-3 pt-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitPullRequest className="size-3.5 text-tertiary" />
          <span className="text-body-xs-medium text-secondary">{t("issue.development.title")}</span>
        </div>
        <span className="text-caption-sm-regular text-tertiary">
          {t("issue.development.count.pr", { count: pullRequests.length })} /{" "}
          {t("issue.development.count.commit", { count: commitCount })}
        </span>
      </div>

      {pullRequests.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-caption-sm-medium text-tertiary uppercase">{t("issue.development.pull_requests")}</span>
          {pullRequests.map((pullRequest) => (
            <PullRequestRow key={pullRequest.id} pullRequest={pullRequest} isMobile={isMobile} />
          ))}
        </div>
      )}

      {commits.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-caption-sm-medium text-tertiary uppercase">{t("issue.development.commits")}</span>
          {commits.map((commit) => (
            <CommitRow key={commit.id} commit={commit} isMobile={isMobile} />
          ))}
        </div>
      )}
    </div>
  );
};

export { GitHubDevelopmentLinks, isGitHubDevelopmentLink };
