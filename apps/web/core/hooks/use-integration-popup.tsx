/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { useParams } from "next/navigation";

const useIntegrationPopup = ({
  provider,
  stateParams,
  github_app_name,
  slack_client_id,
  authUrl,
  onBeforeOpen,
  onComplete,
}: {
  provider: string | undefined;
  stateParams?: string;
  github_app_name?: string;
  slack_client_id?: string;
  authUrl?: string | null;
  onBeforeOpen?: () => void | Promise<void>;
  onComplete?: () => void | Promise<void>;
}) => {
  const [authLoader, setAuthLoader] = useState(false);

  const { workspaceSlug, projectId } = useParams();

  const providerUrls: { [key: string]: string } = {
    github: `https://github.com/apps/${github_app_name}/installations/new?state=${workspaceSlug?.toString()}`,
    slack: `https://slack.com/oauth/v2/authorize?scope=chat:write,im:history,im:write,links:read,links:write,users:read,users:read.email&amp;user_scope=&amp;&client_id=${slack_client_id}&state=${workspaceSlug?.toString()}`,
    slackChannel: `https://slack.com/oauth/v2/authorize?scope=incoming-webhook&client_id=${slack_client_id}&state=${workspaceSlug?.toString()},${projectId?.toString()}${
      stateParams ? "," + stateParams : ""
    }`,
  };

  const formatAuthUrl = (url: string) =>
    url
      .replaceAll("{workspaceSlug}", encodeURIComponent(workspaceSlug?.toString() ?? ""))
      .replaceAll("{projectId}", encodeURIComponent(projectId?.toString() ?? ""))
      .replaceAll("{stateParams}", encodeURIComponent(stateParams ?? ""));

  const popup = useRef<any>();
  const authCompleted = useRef(false);
  const messageListener = useRef<((event: MessageEvent) => void) | null>(null);

  const removeMessageListener = () => {
    if (!messageListener.current) return;

    window.removeEventListener("message", messageListener.current);
    messageListener.current = null;
  };

  const completeAuth = () => {
    if (authCompleted.current) return;

    authCompleted.current = true;
    setAuthLoader(false);
    removeMessageListener();
    void onComplete?.();
  };

  const listenForAuthMessage = () => {
    removeMessageListener();

    messageListener.current = (event: MessageEvent) => {
      if (event.data?.type !== "plane:integration:github") return;

      completeAuth();
    };
    window.addEventListener("message", messageListener.current);
  };

  const checkPopup = () => {
    const check = setInterval(() => {
      if (!popup || popup.current.closed || popup.current.closed === undefined) {
        clearInterval(check);
        completeAuth();
      }
    }, 1000);
  };

  const openPopup = () => {
    if (!provider) return;

    const width = 600,
      height = 600;
    const left = window.innerWidth / 2 - width / 2;
    const top = window.innerHeight / 2 - height / 2;
    const url = authUrl ? formatAuthUrl(authUrl) : providerUrls[provider];

    if (!url) return;

    return window.open(url, "", `width=${width}, height=${height}, top=${top}, left=${left}`);
  };

  const startAuth = async () => {
    authCompleted.current = false;
    await onBeforeOpen?.();
    listenForAuthMessage();
    popup.current = openPopup();
    if (!popup.current) {
      removeMessageListener();
      return;
    }

    checkPopup();
    setAuthLoader(true);
  };

  return {
    startAuth,
    isConnecting: authLoader,
  };
};

export default useIntegrationPopup;
