# Fork CI/CD

This fork uses `.github/workflows/fork-ci-cd.yml` for private CI/CD.

## What Runs

- Pull requests into `main` run web checks and API checks.
- Pushes to `main` run the same checks, build Docker images, push them to GHCR,
  then deploy to the private server.
- Manual runs can deploy any selected ref when the `deploy` input is set to `true`.

Images are tagged with two lightweight tags:

- `sha-<12-char-sha>`: immutable deploy tag used by the private server.
- `<branch-name>`: movable convenience tag, usually `main`.

The deploy job updates the server checkout to the deployed commit, logs into GHCR,
pulls the immutable SHA tag, and starts `docker-compose.ghcr.yml`. It does not
push images to Docker Hub and does not depend on Plane-owned deployment secrets.

## Required GitHub Secrets

Set these in GitHub repository settings under `Secrets and variables` -> `Actions`.

- `DEPLOY_HOST`: Server hostname or IP address.
- `DEPLOY_USER`: SSH user on the server.
- `DEPLOY_SSH_KEY`: Private key that can SSH into the server.
- `DEPLOY_PATH`: Absolute path to the checked-out fork on the server.
- `GHCR_USERNAME`: GitHub username or bot account used by the server for GHCR pulls.
- `GHCR_TOKEN`: GitHub token with `read:packages` access for GHCR pulls.

Optional:

- `DEPLOY_PORT`: SSH port. Defaults to `22`.
- `DEPLOY_COMPOSE_FILE`: Compose file to run from `DEPLOY_PATH`. Defaults to
  `docker-compose.ghcr.yml`.

## Server Setup

Clone the fork once on the server and configure the production environment files
before enabling deployment.

```bash
git clone git@github.com:<owner>/<repo>.git /opt/plane
cd /opt/plane
git checkout main
cp .env.example .env
cp apps/api/.env.example apps/api/.env
```

Install Docker with the Compose plugin, then test GHCR access and the image-based
compose file once:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin
APP_RELEASE=sha-<12-char-sha> GHCR_OWNER=l3nemy docker compose -f docker-compose.ghcr.yml pull
APP_RELEASE=sha-<12-char-sha> GHCR_OWNER=l3nemy docker compose -f docker-compose.ghcr.yml up -d --remove-orphans
APP_RELEASE=sha-<12-char-sha> GHCR_OWNER=l3nemy docker compose -f docker-compose.ghcr.yml ps
```

After that, GitHub Actions can update the same checkout to the deployed commit,
set `APP_RELEASE` to the SHA tag, and run the same compose commands.

## Deploying A Branch

For a one-off deploy from a branch, open the `Fork CI/CD` workflow in GitHub
Actions, choose `Run workflow`, select the branch, and set `deploy` to `true`.

Automatic deploys only happen on pushes to `main`. To deploy another branch
automatically, add it under the workflow's `push.branches`.

## Rollback

On the server:

```bash
cd /opt/plane
git reset --hard <previous-good-sha>
APP_RELEASE=sha-<previous-good-short-sha> GHCR_OWNER=l3nemy docker compose -f docker-compose.ghcr.yml pull
APP_RELEASE=sha-<previous-good-short-sha> GHCR_OWNER=l3nemy docker compose -f docker-compose.ghcr.yml up -d --remove-orphans
```
