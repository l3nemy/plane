/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

type TIssueLinkEditableFields = {
  title: string;
  url: string;
};

type TIssueLink = TIssueLinkEditableFields & {
  created_by_id: string;
  id: string;
  metadata: any;
  issue_id: string;

  //need
  created_at: Date;
};

type TIssueLinkMap = {
  [issue_id: string]: TIssueLink;
};

type TIssueLinkIdMap = {
  [issue_id: string]: string[];
};

type TGitHubDevelopmentActor = {
  avatar_url?: string;
  html_url?: string;
  login?: string;
};

type TIssueGitHubCommitDevelopmentLink = {
  author_login?: string;
  committed_at?: string;
  created_at?: string;
  id: string;
  link_source?: string;
  message: string;
  pull_request_number?: number | string;
  pull_request_title?: string;
  pull_request_url?: string;
  repository?: string;
  repository_id?: number | string;
  sha?: string;
  short_sha?: string;
  title: string;
  url: string;
};

type TIssueGitHubPullRequestDevelopmentLink = {
  actor?: TGitHubDevelopmentActor;
  assignees: TGitHubDevelopmentActor[];
  commits: TIssueGitHubCommitDevelopmentLink[];
  created_at?: string;
  draft?: boolean;
  id: string;
  merged?: boolean;
  number?: number | string;
  repository?: string;
  repository_id?: number | string;
  state?: string;
  title: string;
  updated_at?: string;
  url: string;
};

type TIssueGitHubDevelopmentLinks = {
  commits: TIssueGitHubCommitDevelopmentLink[];
  pull_requests: TIssueGitHubPullRequestDevelopmentLink[];
};

export type {
  TGitHubDevelopmentActor,
  TIssueGitHubCommitDevelopmentLink,
  TIssueGitHubDevelopmentLinks,
  TIssueGitHubPullRequestDevelopmentLink,
  TIssueLink,
  TIssueLinkEditableFields,
  TIssueLinkIdMap,
  TIssueLinkMap,
};
