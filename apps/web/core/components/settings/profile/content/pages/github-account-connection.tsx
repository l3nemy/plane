/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Github, Link, RefreshCw } from "lucide-react";
import useSWR, { mutate } from "swr";
// plane imports
import { API_BASE_URL } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Input } from "@plane/ui";
// constants
import { USER_GITHUB_ACCOUNT } from "@/constants/fetch-keys";
// hooks
import { useInstance } from "@/hooks/store/use-instance";
// services
import { UserService } from "@/services/user.service";

type TGitHubAccount = {
  id: string;
  metadata?: {
    avatar_url?: string;
    html_url?: string;
    login?: string;
  };
  provider_account_id: string;
};

type TGitHubPublicUser = {
  avatar_url?: string;
  html_url?: string;
  id: number;
  login: string;
};

const userService = new UserService();

function GitHubAccountConnection() {
  const { t } = useTranslation();
  const { config } = useInstance();
  const [isManualOpen, setIsManualOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [isConnectingManually, setIsConnectingManually] = useState(false);

  const { data: githubAccount, isLoading } = useSWR<TGitHubAccount | undefined>(USER_GITHUB_ACCOUNT, () =>
    userService.getCurrentUserGitHubAccount()
  );

  const githubLogin = githubAccount?.metadata?.login;
  const githubProfileUrl =
    githubAccount?.metadata?.html_url ?? (githubLogin ? `https://github.com/${githubLogin}` : "");
  const isConnected = !!githubAccount?.provider_account_id;
  const isGitHubOAuthEnabled = !!config?.is_github_enabled;

  const connectWithOAuth = () => {
    const nextPath = encodeURIComponent("/settings/profile/security");
    window.location.assign(`${API_BASE_URL}/auth/github/?next_path=${nextPath}`);
  };

  const connectManually = async () => {
    const login = username.trim().replace(/^@/, "");
    if (!login) return;

    setIsConnectingManually(true);
    try {
      const response = await fetch(`https://api.github.com/users/${encodeURIComponent(login)}`);
      if (!response.ok) throw new Error("GitHub user not found");

      const githubUser = (await response.json()) as TGitHubPublicUser;
      await userService.connectCurrentUserGitHubAccount({
        avatar_url: githubUser.avatar_url,
        github_id: githubUser.id,
        html_url: githubUser.html_url,
        login: githubUser.login,
      });
      await mutate(USER_GITHUB_ACCOUNT);
      setUsername("");
      setIsManualOpen(false);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("account_settings.security.github_account.toast.connected.title"),
        message: t("account_settings.security.github_account.toast.connected.message"),
      });
    } catch {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("account_settings.security.github_account.toast.error.title"),
        message: t("account_settings.security.github_account.toast.error.message"),
      });
    } finally {
      setIsConnectingManually(false);
    }
  };

  return (
    <section className="mt-10 border-t border-subtle pt-8">
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h4 className="text-15 font-medium text-primary">{t("account_settings.security.github_account.heading")}</h4>
          <p className="text-13 text-secondary">{t("account_settings.security.github_account.description")}</p>
        </div>

        <div className="flex flex-col gap-4 rounded-md border border-subtle bg-surface-2 p-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-subtle bg-surface-1 text-primary">
                <Github className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-13 font-medium text-primary">GitHub</span>
                  {isConnected && (
                    <span className="bg-green-500/10 text-green-600 rounded px-1.5 py-0.5 text-11 font-medium">
                      {t("common.connected")}
                    </span>
                  )}
                </div>
                <p className="truncate text-12 text-secondary">
                  {isLoading
                    ? t("common.loading")
                    : isConnected
                      ? githubLogin
                        ? `@${githubLogin}`
                        : githubAccount.provider_account_id
                      : t("account_settings.security.github_account.not_connected")}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {isConnected && githubProfileUrl && (
                <Button variant="secondary" size="lg" onClick={() => window.open(githubProfileUrl, "_blank")}>
                  {t("account_settings.security.github_account.view_profile")}
                </Button>
              )}
              <Button
                variant={isConnected ? "secondary" : "primary"}
                size="lg"
                onClick={connectWithOAuth}
                disabled={!isGitHubOAuthEnabled}
                prependIcon={isConnected ? <RefreshCw className="h-3.5 w-3.5" /> : <Link className="h-3.5 w-3.5" />}
              >
                {isConnected
                  ? t("account_settings.security.github_account.reconnect")
                  : t("account_settings.security.github_account.connect")}
              </Button>
            </div>
          </div>

          {!isGitHubOAuthEnabled && (
            <p className="text-12 text-tertiary">{t("account_settings.security.github_account.oauth_disabled")}</p>
          )}

          <div className="flex flex-col gap-3 border-t border-subtle pt-4">
            <button
              type="button"
              className="text-custom-primary-100 w-fit text-left text-12 font-medium hover:underline"
              onClick={() => setIsManualOpen((current) => !current)}
            >
              {isManualOpen
                ? t("account_settings.security.github_account.manual.hide")
                : t("account_settings.security.github_account.manual.show")}
            </button>

            {isManualOpen && (
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <Input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder={t("account_settings.security.github_account.manual.placeholder")}
                  className="w-full"
                />
                <Button
                  variant="secondary"
                  size="lg"
                  onClick={connectManually}
                  loading={isConnectingManually}
                  disabled={!username.trim()}
                >
                  {t("account_settings.security.github_account.manual.save")}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export { GitHubAccountConnection };
