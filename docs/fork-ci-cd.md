# Fork CI/CD

This fork uses `.github/workflows/fork-ci-cd.yml` for private CI/CD.

## What Runs

- Pull requests into `main` run web checks and API checks.
- Pushes to `main` run the same checks, then deploy to the private server.
- Manual runs can deploy any selected ref when the `deploy` input is set to `true`.

The deploy job builds from source on the server with the root `docker-compose.yml`.
It does not push images to Docker Hub and does not depend on Plane-owned deployment
secrets.

## Required GitHub Secrets

Set these in GitHub repository settings under `Secrets and variables` -> `Actions`.

- `DEPLOY_HOST`: Server hostname or IP address.
- `DEPLOY_USER`: SSH user on the server.
- `DEPLOY_SSH_KEY`: Private key that can SSH into the server.
- `DEPLOY_PATH`: Absolute path to the checked-out fork on the server.

Optional:

- `DEPLOY_PORT`: SSH port. Defaults to `22`.
- `DEPLOY_COMPOSE_FILE`: Compose file to run from `DEPLOY_PATH`. Defaults to
  `docker-compose.yml`.

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

Install Docker with the Compose plugin, then test the source build once:

```bash
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d --remove-orphans
docker compose -f docker-compose.yml ps
```

After that, GitHub Actions can update the same checkout to the deployed commit and
run the same compose commands.

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
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d --remove-orphans
```
